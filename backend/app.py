"""
Transfer Learning Classifier - Backend con FastAPI + TensorFlow
Todo se almacena SOLO EN MEMORIA. Al reiniciar el servidor los datos desaparecen.

Endpoints:
  POST /upload   — recibe imágenes de entrenamiento (en memoria, nunca en disco)
  POST /train    — entrena el modelo con Transfer Learning (MobileNetV2)
  POST /predict  — devuelve la clase predicha para un frame de webcam
  DELETE /reset  — limpia imágenes y modelo de la memoria
"""

from __future__ import annotations

import io
import base64
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

# ─── Configuración ───────────────────────────────────────────────────────────
IMG_SIZE   = (224, 224)
EPOCHS     = 20
BATCH_SIZE = 16

app = FastAPI(title="Transfer Learning Webcam Classifier")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Estado global (solo en RAM, desaparece al reiniciar) ─────────────────────
class AppState:
    model: Optional[tf.keras.Model] = None
    class_names: list = []
    image_data: dict = None

    def __init__(self):
        self.image_data = defaultdict(list)

state = AppState()

# ─── Modelos Pydantic ─────────────────────────────────────────────────────────

class ImagePayload(BaseModel):
    label: str
    image_b64: str

class TrainRequest(BaseModel):
    epochs: int = EPOCHS
    fine_tune: bool = True

class PredictPayload(BaseModel):
    image_b64: str

# ─── Utilidades ──────────────────────────────────────────────────────────────

def b64_to_pil(b64_string: str) -> Image.Image:
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(b64_string))).convert("RGB")

def pil_to_uint8(img: Image.Image) -> np.ndarray:
    """PIL Image → uint8 numpy (H,W,3). Sin TF, instantáneo."""
    return np.array(img.resize(IMG_SIZE), dtype=np.uint8)

def uint8_to_tensor(arr: np.ndarray) -> np.ndarray:
    """uint8 (H,W,3) → float32 listo para MobileNetV2 [-1,1]."""
    return preprocess_input(arr.astype(np.float32))

def build_dataset_from_memory() -> tuple[np.ndarray, np.ndarray, list[str]]:
    classes = sorted(k for k, v in state.image_data.items() if len(v) > 0)
    if len(classes) < 2:
        raise ValueError("Se necesitan al menos 2 clases para entrenar.")

    X, y = [], []
    for idx, cls in enumerate(classes):
        for raw in state.image_data[cls]:
            X.append(uint8_to_tensor(raw))   # conversión TF solo aquí
            y.append(idx)

    idx_perm = np.random.permutation(len(X))
    return np.array(X)[idx_perm], np.array(y)[idx_perm], classes

def build_model(num_classes: int, fine_tune: bool = True) -> tf.keras.Model:
    base = MobileNetV2(
        input_shape=(*IMG_SIZE, 3),
        include_top=False,
        weights="imagenet",
    )
    base.trainable = False

    inputs = tf.keras.Input(shape=(*IMG_SIZE, 3))
    x = base(inputs, training=False)
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(128, activation="relu")(x)
    x = layers.Dropout(0.2)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)
    model = models.Model(inputs, outputs)

    if fine_tune:
        base.trainable = True
        for layer in base.layers[:-30]:
            layer.trainable = False

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model

# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status": "ok",
        "classes": state.class_names,
        "image_counts": {k: len(v) for k, v in state.image_data.items()},
    }

@app.post("/upload")
def upload_image(payload: ImagePayload):
    """Guarda la imagen en memoria como uint8 puro — sin llamar a TensorFlow."""
    label = payload.label.strip().replace(" ", "_")
    if not label:
        raise HTTPException(400, "La etiqueta no puede estar vacía.")

    raw = pil_to_uint8(b64_to_pil(payload.image_b64))   # sólo PIL + numpy
    state.image_data[label].append(raw)

    return {
        "label": label,
        "count": len(state.image_data[label]),
        "class_counts": {k: len(v) for k, v in state.image_data.items()},
    }

@app.get("/status")
def status():
    return {
        "model_trained": state.model is not None,
        "classes": state.class_names,
        "class_counts": {k: len(v) for k, v in state.image_data.items()},
    }

@app.post("/train")
def train(req: TrainRequest):
    """Entrena el modelo con las imágenes en memoria."""
    try:
        X, y, class_names = build_dataset_from_memory()
    except ValueError as e:
        raise HTTPException(400, str(e))

    print(f"[Train] Clases: {class_names} | Muestras: {len(X)}")

    model = build_model(len(class_names), fine_tune=req.fine_tune)

    history = model.fit(
        X, y,
        epochs=req.epochs,
        batch_size=BATCH_SIZE,
        validation_split=0.2,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                patience=5, restore_best_weights=True, monitor="val_accuracy"
            ),
            tf.keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=3),
        ],
        verbose=1,
    )

    state.model       = model
    state.class_names = class_names

    final_acc = history.history["val_accuracy"][-1]
    return {
        "message":      "Entrenamiento completado.",
        "classes":      class_names,
        "val_accuracy": round(float(final_acc), 4),
        "epochs_run":   len(history.history["loss"]),
    }

@app.post("/predict")
def predict(payload: PredictPayload):
    if state.model is None:
        raise HTTPException(400, "No hay modelo entrenado. Llama /train primero.")

    tensor = uint8_to_tensor(pil_to_uint8(b64_to_pil(payload.image_b64)))
    tensor = np.expand_dims(tensor, 0)
    probs  = state.model.predict(tensor, verbose=0)[0]
    idx    = int(np.argmax(probs))

    return {
        "label":         state.class_names[idx],
        "confidence":    round(float(probs[idx]), 4),
        "probabilities": {
            cls: round(float(p), 4)
            for cls, p in zip(state.class_names, probs)
        },
    }

@app.delete("/reset")
def reset():
    """Limpia todo de la memoria."""
    state.model       = None
    state.class_names = []
    state.image_data  = defaultdict(list)
    return {"message": "Memoria limpiada."}

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)

