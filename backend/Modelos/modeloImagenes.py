"""
Transfer Learning Classifier — Backend con FastAPI + TensorFlow

Todo se almacena SOLO EN MEMORIA (RAM). Al reiniciar el servidor los datos desaparecen.

Endpoints disponibles:
  GET  /        — estado general: clases registradas y conteo de imágenes
  GET  /status  — indica si el modelo está entrenado y cuántas imágenes hay por clase
  POST /upload  — recibe imágenes de entrenamiento codificadas en Base64 y las guarda en RAM
  POST /train   — entrena el modelo con Transfer Learning (MobileNetV2 + cabeza personalizada)
  POST /predict — clasifica un frame de webcam con el modelo entrenado
  DELETE /reset — elimina todas las imágenes y el modelo de la memoria
"""

from __future__ import annotations

import io
import base64
import json
import os
import shutil
import tempfile
import zipfile
import numpy as np
from collections import defaultdict
from typing import Optional

import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image

# Detección opcional de tensorflowjs (puede no estar instalado por sus deps pesadas: jax, flax)
try:
    import tensorflowjs as tfjs
    _HAS_TFJS = True
except ImportError:
    _HAS_TFJS = False

# ─── Configuración por defecto ────────────────────────────────────────────────
IMG_SIZE      = (224, 224)   # Tamaño de entrada requerido por MobileNetV2
EPOCHS        = 20           # Épocas de entrenamiento por defecto
BATCH_SIZE    = 16           # Imágenes procesadas por paso de gradiente por defecto
LEARNING_RATE = 1e-4         # Tasa de aprendizaje inicial del optimizador Adam por defecto

app = FastAPI(title="Transfer Learning Webcam Classifier")

# Permitir peticiones CORS desde cualquier origen (necesario para el frontend en desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Estado global (solo en RAM, desaparece al reiniciar el servidor) ─────────
class AppState:
    """
    Contenedor del estado mutable del servidor.
    Almacena el modelo entrenado y las imágenes de entrenamiento de cada clase.
    """
    model: Optional[tf.keras.Model] = None   # Modelo Keras entrenado (None hasta /train)
    class_names: list = []                   # Nombres de las clases en orden de índice numérico
    training_images: dict = None             # { nombre_clase: [array_uint8, ...] }

    def __init__(self):
        self.training_images = defaultdict(list)

state = AppState()

# ─── Modelos Pydantic (esquemas de validación de peticiones) ──────────────────

class ImagePayload(BaseModel):
    """Cuerpo de la petición POST /upload."""
    label: str        # Nombre de la clase a la que pertenece la imagen
    image_b64: str    # Imagen codificada en Base64 (con o sin prefijo data:image/...)

class TrainRequest(BaseModel):
    """Hiperparámetros configurables para el entrenamiento del modelo."""
    epochs:        int   = EPOCHS          # Número máximo de épocas (el early stopping puede detener antes)
    batch_size:    int   = BATCH_SIZE      # Imágenes procesadas por paso de gradiente
    learning_rate: float = LEARNING_RATE   # Tasa de aprendizaje inicial para el optimizador Adam
    fine_tune:     bool  = True            # Si True, desbloquea las últimas 30 capas de MobileNetV2

class PredictPayload(BaseModel):
    """Cuerpo de la petición POST /predict."""
    image_b64: str    # Frame de webcam codificado en Base64

# ─── Utilidades de imagen ─────────────────────────────────────────────────────

def b64_to_pil(b64_string: str) -> Image.Image:
    """
    Convierte una cadena Base64 a una imagen PIL en modo RGB.
    Acepta tanto el formato puro como el formato con prefijo 'data:image/...;base64,'.
    """
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(b64_string))).convert("RGB")

def pil_to_uint8(img: Image.Image) -> np.ndarray:
    """
    Redimensiona una imagen PIL a IMG_SIZE y la convierte a array numpy uint8 (H, W, 3).
    No invoca TensorFlow, por lo que es muy rápido y no consume memoria de GPU.
    """
    return np.array(img.resize(IMG_SIZE), dtype=np.uint8)

def uint8_to_tensor(arr: np.ndarray) -> np.ndarray:
    """
    Preprocesa un array uint8 (H, W, 3) al formato float32 esperado por MobileNetV2.
    La función preprocess_input normaliza los valores al rango [-1, 1].
    """
    return preprocess_input(arr.astype(np.float32))

# ─── Construcción del dataset desde memoria ───────────────────────────────────

def build_dataset_from_memory() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """
    Construye los arrays de entrenamiento X (imágenes) e y (etiquetas) a partir
    de las imágenes almacenadas en RAM. Baraja aleatoriamente los datos.

    Retorna:
        X:            Array float32 de forma (N, 224, 224, 3) listo para MobileNetV2.
        y:            Array de índices enteros de clase correspondientes a cada imagen.
        class_names:  Lista ordenada alfabéticamente con los nombres de las clases.

    Lanza:
        ValueError: Si hay menos de 2 clases con imágenes almacenadas.
    """
    # Usar solo las clases que tengan al menos una imagen
    class_names = sorted(k for k, v in state.training_images.items() if len(v) > 0)
    if len(class_names) < 2:
        raise ValueError("Se necesitan al menos 2 clases para entrenar.")

    X, y = [], []
    for class_index, class_name in enumerate(class_names):
        for raw_image in state.training_images[class_name]:
            X.append(uint8_to_tensor(raw_image))   # Preprocesar al rango [-1, 1]
            y.append(class_index)

    # Barajar para que el modelo no aprenda por orden de clase
    shuffle_indices = np.random.permutation(len(X))
    return np.array(X)[shuffle_indices], np.array(y)[shuffle_indices], class_names

# ─── Construcción del modelo ──────────────────────────────────────────────────

def build_model(
    num_classes: int,
    fine_tune: bool = True,
    learning_rate: float = LEARNING_RATE,
) -> tf.keras.Model:
    """
    Construye un clasificador de imágenes usando Transfer Learning con MobileNetV2.

    Arquitectura (de entrada a salida):
      1. MobileNetV2 preentrenado en ImageNet — extrae características visuales ricas.
         Con fine_tune=True se descongelan las últimas 30 capas para ajuste fino.
      2. GlobalAveragePooling2D — comprime el mapa (7×7×1280) a un vector (1280,).
      3. Dropout(0.3) — apaga el 30% de neuronas aleatoriamente para reducir sobreajuste.
      4. Dense(128, relu) — capa oculta que combina las características extraídas.
      5. Dropout(0.2) — segunda capa de regularización.
      6. Dense(num_classes, softmax) — salida: probabilidad de pertenencia a cada clase.

    Args:
        num_classes:    Número de clases a clasificar.
        fine_tune:      Si True, desbloquea las últimas 30 capas de MobileNetV2 para ajuste.
        learning_rate:  Tasa de aprendizaje inicial del optimizador Adam.
    """
    # Cargar MobileNetV2 sin la cabeza de clasificación original
    # 'weights="imagenet"' descarga pesos preentrenados en ~1.4M imágenes de ImageNet
    base_model = MobileNetV2(
        input_shape=(*IMG_SIZE, 3),
        include_top=False,       # Excluir la capa Dense final de clasificación de ImageNet
        weights="imagenet",
    )
    base_model.trainable = False   # Congelar todos los pesos de la base inicialmente

    # Construir la cabeza personalizada sobre los features de MobileNetV2
    inputs = tf.keras.Input(shape=(*IMG_SIZE, 3))
    x = base_model(inputs, training=False)          # training=False → BatchNorm en modo inferencia
    x = layers.GlobalAveragePooling2D()(x)          # (batch, 7, 7, 1280) → (batch, 1280)
    x = layers.Dropout(0.3)(x)                     # Regularización: descarta el 30% de activaciones
    x = layers.Dense(128, activation="relu")(x)    # Capa densa con activación ReLU
    x = layers.Dropout(0.2)(x)                     # Segunda regularización
    outputs = layers.Dense(num_classes, activation="softmax")(x)   # Probabilidades por clase

    model = models.Model(inputs, outputs)

    if fine_tune:
        # Descongelar las últimas 30 capas de MobileNetV2 para ajuste fino.
        # Las capas más profundas aprenden características específicas del dominio (p.ej. formas
        # concretas), mientras que las primeras aprenden bordes y texturas genéricas — esas se dejan
        # congeladas para aprovechar el conocimiento de ImageNet sin sobreescribirlo.
        base_model.trainable = True
        for layer in base_model.layers[:-30]:
            layer.trainable = False

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="sparse_categorical_crossentropy",   # Pérdida para etiquetas enteras (no one-hot)
        metrics=["accuracy"],
    )
    return model

# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Estado general: nombres de clases registradas y número de imágenes por clase."""
    return {
        "status": "ok",
        "classes": state.class_names,
        "image_counts": {k: len(v) for k, v in state.training_images.items()},
    }

@app.post("/upload")
def upload_image(payload: ImagePayload):
    """
    Recibe una imagen en Base64 con su etiqueta de clase y la almacena en RAM como
    array numpy uint8. Este endpoint no invoca TensorFlow, por lo que es muy rápido.
    Los espacios en la etiqueta se reemplazan por guiones bajos para uniformidad.
    """
    # Normalizar etiqueta: eliminar espacios al inicio/fin y reemplazar internos por '_'
    label = payload.label.strip().replace(" ", "_")
    if not label:
        raise HTTPException(400, "La etiqueta no puede estar vacía.")

    # Convertir Base64 → PIL → array uint8 (sin TensorFlow)
    raw_image = pil_to_uint8(b64_to_pil(payload.image_b64))
    state.training_images[label].append(raw_image)

    return {
        "label": label,
        "count": len(state.training_images[label]),
        "class_counts": {k: len(v) for k, v in state.training_images.items()},
    }

@app.get("/status")
def status():
    """Devuelve si existe un modelo entrenado, los nombres de clase y el conteo de imágenes."""
    return {
        "model_trained": state.model is not None,
        "classes": state.class_names,
        "class_counts": {k: len(v) for k, v in state.training_images.items()},
    }

@app.post("/train")
def train(req: TrainRequest):
    """
    Entrena el modelo de Transfer Learning con las imágenes almacenadas en RAM.

    Proceso:
      1. Construye el dataset (X, y) a partir de las imágenes en memoria.
      2. Crea un nuevo modelo MobileNetV2 con la cabeza personalizada.
      3. Entrena usando los hiperparámetros recibidos (epochs, batch_size, learning_rate).
      4. Usa EarlyStopping (paciencia=5) para evitar sobreajuste y ahorrar tiempo.
      5. Usa ReduceLROnPlateau para reducir la tasa de aprendizaje cuando el entrenamiento se estanca.
      6. Guarda el modelo y los nombres de clase en el estado global para predicciones futuras.
    """
    try:
        X, y, class_names = build_dataset_from_memory()
    except ValueError as e:
        raise HTTPException(400, str(e))

    print(
        f"[Train] Clases: {class_names} | Muestras: {len(X)} | "
        f"Épocas: {req.epochs} | Lote: {req.batch_size} | LR: {req.learning_rate}"
    )

    model = build_model(
        len(class_names),
        fine_tune=req.fine_tune,
        learning_rate=req.learning_rate,
    )

    history = model.fit(
        X, y,
        epochs=req.epochs,
        batch_size=req.batch_size,      # Tamaño de lote configurable desde el frontend
        validation_split=0.2,           # 20% de los datos para evaluar la generalización
        callbacks=[
            # Detiene el entrenamiento si val_accuracy no mejora durante 5 épocas consecutivas
            # y restaura los pesos del mejor epoch encontrado
            tf.keras.callbacks.EarlyStopping(
                patience=5, restore_best_weights=True, monitor="val_accuracy"
            ),
            # Reduce la LR a la mitad si val_loss no mejora en 3 épocas (evita estancamientos)
            tf.keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=3),
        ],
        verbose=1,
    )

    # Guardar el modelo entrenado y los nombres de clase para inferencia posterior
    state.model       = model
    state.class_names = class_names

    final_accuracy = history.history["val_accuracy"][-1]
    return {
        "message":      "Entrenamiento completado.",
        "classes":      class_names,
        "val_accuracy": round(float(final_accuracy), 4),
        "epochs_run":   len(history.history["loss"]),
    }

@app.post("/predict")
def predict(payload: PredictPayload):
    """
    Clasifica un frame de webcam con el modelo entrenado.
    Devuelve la clase predicha, su nivel de confianza y las probabilidades de todas las clases.
    El preprocesado aplica exactamente la misma transformación que durante el entrenamiento.
    """
    if state.model is None:
        raise HTTPException(400, "No hay modelo entrenado. Llama /train primero.")

    # Preprocesar igual que en el entrenamiento: Base64 → PIL → uint8 → float32 normalizado
    tensor = uint8_to_tensor(pil_to_uint8(b64_to_pil(payload.image_b64)))
    tensor = np.expand_dims(tensor, 0)          # Añadir dimensión de batch: (1, 224, 224, 3)

    probabilities   = state.model.predict(tensor, verbose=0)[0]
    predicted_index = int(np.argmax(probabilities))

    return {
        "label":         state.class_names[predicted_index],
        "confidence":    round(float(probabilities[predicted_index]), 4),
        "probabilities": {
            cls: round(float(p), 4)
            for cls, p in zip(state.class_names, probabilities)
        },
    }

@app.delete("/reset")
def reset():
    """Elimina el modelo entrenado y todas las imágenes de la memoria RAM."""
    state.model           = None
    state.class_names     = []
    state.training_images = defaultdict(list)
    return {"message": "Memoria limpiada."}

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("modeloImagenes:app", host="0.0.0.0", port=8000, reload=False)
