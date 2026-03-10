"""
Voice Recognition - Backend con FastAPI + TensorFlow + Librosa
Todo se almacena SOLO EN MEMORIA. Al reiniciar el servidor los datos desaparecen.

Endpoints:
  POST   /audio/upload   â€” recibe audio PCM (float32) en base64, extrae MFCCs y guarda
  POST   /audio/train    â€” entrena modelo de reconocimiento de voz
  POST   /audio/predict  â€” predice a quiÃ©n pertenece un audio
  DELETE /audio/reset    â€” limpia datos de audio de la memoria
  GET    /audio/status   â€” estado del modelo y usuarios registrados
"""

from __future__ import annotations

import base64
import numpy as np
from collections import defaultdict
from typing import Optional

import tensorflow as tf
import librosa

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 
AUDIO_SR = 22050          # Sample-rate estÃ¡ndar para MFCCs
N_MFCC   = 40             # NÂº de coeficientes MFCC
# Features: MFCCs(40) mean+std + delta-MFCCs(40) mean+std + chroma(12) mean+std
#          + spectral_contrast(7) mean+std + ZCR(1) mean+std  = 200 features
N_FEAT   = (N_MFCC * 2) + (N_MFCC * 2) + (12 * 2) + (7 * 2) + (1 * 2)  # = 200
EPOCHS   = 80
BATCH    = 16

app = FastAPI(title="Voice Recognition Classifier")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class AudioState:
    model: Optional[tf.keras.Model] = None
    user_names: list = []
    audio_features: dict = None      # { nombre: [array(80,), â€¦] }
    label_map: dict = None           # { 0: "Juan", 1: "Ana", â€¦ }
    norm_mean: Optional[np.ndarray] = None
    norm_std:  Optional[np.ndarray] = None

    def __init__(self):
        self.audio_features = defaultdict(list)
        self.label_map = {}

state = AudioState()

#  Modelos Pydantic 

class AudioPayload(BaseModel):
    label: str
    audio_b64: str              # PCM float32 codificado en base64
    sample_rate: int = 48000    # SR del navegador (se resamplea internamente)

class AudioTrainRequest(BaseModel):
    epochs: int = EPOCHS

class AudioPredictPayload(BaseModel):
    audio_b64: str
    sample_rate: int = 48000

#  Utilidades de procesamiento 

def process_audio(audio_data: np.ndarray, sample_rate: int = 48000) -> np.ndarray:
    """
    Convierte audio crudo PCM â†’ vector de 200 features:
      - 40 MFCCs (mean + std = 80)
      - 40 delta-MFCCs (mean + std = 80)
      - 12 chroma (mean + std = 24)
      - 7 spectral contrast (mean + std = 14)
      - 1 ZCR (mean + std = 2)
    Hace resample a 22 050 Hz para que los features sean comparables.
    """
    if len(audio_data) == 0:
        raise ValueError("Audio vacÃ­o.")

    # Asegurar float64 para librosa
    audio_data = audio_data.astype(np.float64)

    # Resample al estÃ¡ndar de librosa
    if sample_rate != AUDIO_SR:
        audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=AUDIO_SR)

    #  MFCCs 
    mfccs = librosa.feature.mfcc(y=audio_data, sr=AUDIO_SR, n_mfcc=N_MFCC)
    mfcc_mean = np.mean(mfccs.T, axis=0)
    mfcc_std  = np.std(mfccs.T, axis=0)

    #  Delta MFCCs (velocidad de cambio temporal)  
    delta_mfccs = librosa.feature.delta(mfccs)
    delta_mean  = np.mean(delta_mfccs.T, axis=0)
    delta_std   = np.std(delta_mfccs.T, axis=0)

    #  Chroma (distribuciÃ³n tonal â€” 12 semitonos)  
    chroma = librosa.feature.chroma_stft(y=audio_data, sr=AUDIO_SR)
    chroma_mean = np.mean(chroma.T, axis=0)
    chroma_std  = np.std(chroma.T, axis=0)

    #  Spectral Contrast (7 sub-bandas)  
    contrast = librosa.feature.spectral_contrast(y=audio_data, sr=AUDIO_SR)
    contrast_mean = np.mean(contrast.T, axis=0)
    contrast_std  = np.std(contrast.T, axis=0)

    #  Zero Crossing Rate  
    zcr = librosa.feature.zero_crossing_rate(y=audio_data)
    zcr_mean = np.mean(zcr)
    zcr_std  = np.std(zcr)

    return np.concatenate([
        mfcc_mean, mfcc_std,
        delta_mean, delta_std,
        chroma_mean, chroma_std,
        contrast_mean, contrast_std,
        [zcr_mean, zcr_std],
    ]).astype(np.float32)


def build_audio_model(num_classes: int) -> tf.keras.Model:
    """Red neuronal densa con BatchNorm para clasificaciÃ³n de voz (200 features)."""
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(N_FEAT,)),
        tf.keras.layers.Dense(256, activation="relu"),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.Dropout(0.4),
        tf.keras.layers.Dense(128, activation="relu"),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(64, activation="relu"),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(num_classes, activation="softmax"),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def augment_features(X: np.ndarray, y: np.ndarray, factor: int = 3) -> tuple:
    """
    Data augmentation: genera copias con ruido gaussiano ligero para
    aumentar el dataset Ã— factor, mejorando generalizaciÃ³n con pocos audios.
    """
    X_aug, y_aug = [X], [y]
    for _ in range(factor - 1):
        noise = np.random.normal(0, 0.02, X.shape).astype(np.float32)
        X_aug.append(X + noise)
        y_aug.append(y)
    return np.concatenate(X_aug), np.concatenate(y_aug)

#  Endpoints 

@app.get("/")
def root():
    return {
        "status": "ok",
        "users": list(state.audio_features.keys()),
        "audio_counts": {k: len(v) for k, v in state.audio_features.items()},
    }


@app.post("/audio/upload")
def upload_audio(payload: AudioPayload):
    """Recibe audio PCM float32 en base64, extrae MFCCs y guarda en memoria."""
    label = payload.label.strip().replace(" ", "_")
    if not label:
        raise HTTPException(400, "El nombre no puede estar vacÃ­o.")

    try:
        audio_bytes = base64.b64decode(payload.audio_b64)
    except Exception:
        raise HTTPException(400, "audio_b64 no es base64 vÃ¡lido.")

    audio_array = np.frombuffer(audio_bytes, dtype=np.float32)

    if len(audio_array) < 1000:
        raise HTTPException(400, "Audio demasiado corto. Habla al menos 1 segundo.")

    try:
        features = process_audio(audio_array, payload.sample_rate)
    except Exception as e:
        raise HTTPException(500, f"Error procesando audio: {e}")

    state.audio_features[label].append(features)

    return {
        "label": label,
        "count": len(state.audio_features[label]),
        "user_counts": {k: len(v) for k, v in state.audio_features.items()},
    }


@app.get("/audio/status")
def audio_status():
    return {
        "model_trained": state.model is not None,
        "users": list(state.audio_features.keys()),
        "user_counts": {k: len(v) for k, v in state.audio_features.items()},
    }


@app.post("/audio/train")
def train_audio(req: AudioTrainRequest):
    """Entrena el modelo de reconocimiento de voz con los audios en memoria."""
    users = sorted(k for k, v in state.audio_features.items() if len(v) > 0)
    if len(users) < 2:
        raise HTTPException(400, "Se necesitan al menos 2 usuarios para entrenar.")

    X, y = [], []
    label_map = {}
    for idx, user in enumerate(users):
        label_map[idx] = user
        for features in state.audio_features[user]:
            X.append(features)
            y.append(idx)

    X = np.array(X, dtype=np.float32)
    y = np.array(y)

    # NormalizaciÃ³n (z-score) guardamos media y std para la predicciÃ³n
    norm_mean = X.mean(axis=0)
    norm_std  = X.std(axis=0) + 1e-8
    X = (X - norm_mean) / norm_std

    # Data augmentation: genera copias con ruido para mejorar generalizaciÃ³n
    X, y = augment_features(X, y, factor=4)

    # Shuffle
    perm = np.random.permutation(len(X))
    X, y = X[perm], y[perm]

    print(f"[Audio Train] Usuarios: {users} | Muestras: {len(X)}")

    model = build_audio_model(len(users))

    # Solo usar validation_split si hay suficientes muestras
    use_validation = len(X) >= 15
    monitor_metric = "val_accuracy" if use_validation else "accuracy"

    history = model.fit(
        X, y,
        epochs=req.epochs,
        batch_size=BATCH,
        validation_split=0.2 if use_validation else 0.0,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                patience=8, restore_best_weights=True, monitor=monitor_metric
            ),
            tf.keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=4),
        ],
        verbose=1,
    )

    # Guardar estado
    state.model      = model
    state.user_names = users
    state.label_map  = label_map
    state.norm_mean  = norm_mean
    state.norm_std   = norm_std

    final_acc = history.history[monitor_metric][-1]
    return {
        "message":      "Modelo de audio entrenado.",
        "users":        users,
        "val_accuracy": round(float(final_acc), 4),
        "epochs_run":   len(history.history["loss"]),
    }


@app.post("/audio/predict")
def predict_audio(payload: AudioPredictPayload):
    """Predice a quiÃ©n pertenece un audio."""
    if state.model is None:
        raise HTTPException(400, "No hay modelo de audio entrenado. Llama /audio/train primero.")

    try:
        audio_bytes = base64.b64decode(payload.audio_b64)
    except Exception:
        raise HTTPException(400, "audio_b64 no es base64 vÃ¡lido.")

    audio_array = np.frombuffer(audio_bytes, dtype=np.float32)

    if len(audio_array) < 1000:
        raise HTTPException(400, "Audio demasiado corto.")

    try:
        features = process_audio(audio_array, payload.sample_rate)
    except Exception as e:
        raise HTTPException(500, f"Error procesando audio: {e}")

    # Normalizar con las mismas estadÃ­sticas del entrenamiento
    features = (features - state.norm_mean) / state.norm_std

    input_data = np.array([features], dtype=np.float32)
    probs = state.model.predict(input_data, verbose=0)[0]
    idx   = int(np.argmax(probs))

    return {
        "label":         state.label_map[idx],
        "confidence":    round(float(probs[idx]), 4),
        "probabilities": {
            state.label_map[i]: round(float(p), 4)
            for i, p in enumerate(probs)
        },
    }


@app.delete("/audio/reset")
def reset_audio():
    """Limpia todos los datos de audio de la memoria."""
    state.model      = None
    state.user_names = []
    state.audio_features = defaultdict(list)
    state.label_map  = {}
    state.norm_mean  = None
    state.norm_std   = None
    return {"message": "Datos de audio limpiados."}

# Main 
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("modeloAudio:app", host="0.0.0.0", port=8001, reload=False)

