"""
Voice Recognition - Backend con FastAPI + TensorFlow + Librosa
Todo se almacena SOLO EN MEMORIA. Al reiniciar el servidor los datos desaparecen.

Endpoints:
  POST   /audio/upload   — recibe audio PCM (float32) en base64, extrae MFCCs y guarda
  POST   /audio/train    — entrena modelo de reconocimiento de voz
  POST   /audio/predict  — predice a quién pertenece un audio
  DELETE /audio/reset    — limpia datos de audio de la memoria
  GET    /audio/status   — estado del modelo y usuarios registrados
"""

from __future__ import annotations

import base64
import numpy as np
from collections import defaultdict
from typing import Optional

import tensorflow as tf
import librosa

import json
import textwrap

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

# ─── Configuración ───────────────────────────────────────────────────────────
AUDIO_SR = 22050          # Sample-rate estándar para MFCCs
N_MFCC   = 40             # Nº de coeficientes MFCC
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

# ─── Estado global (solo en RAM, desaparece al reiniciar) ─────────────────────
class AudioState:
    model: Optional[tf.keras.Model] = None
    user_names: list = []
    audio_features: dict = None      # { nombre: [array(80,), …] }
    label_map: dict = None           # { 0: "Juan", 1: "Ana", … }
    norm_mean: Optional[np.ndarray] = None
    norm_std:  Optional[np.ndarray] = None

    def __init__(self):
        self.audio_features = defaultdict(list)
        self.label_map = {}

state = AudioState()

# ─── Modelos Pydantic ─────────────────────────────────────────────────────────

class AudioPayload(BaseModel):
    label: str
    audio_b64: str              # PCM float32 codificado en base64
    sample_rate: int = 48000    # SR del navegador (se resamplea internamente)

class AudioTrainRequest(BaseModel):
    epochs: int = EPOCHS

class AudioPredictPayload(BaseModel):
    audio_b64: str
    sample_rate: int = 48000

# ─── Utilidades de procesamiento ─────────────────────────────────────────────

def process_audio(audio_data: np.ndarray, sample_rate: int = 48000) -> np.ndarray:
    """
    Convierte audio crudo PCM → vector de 200 features:
      - 40 MFCCs (mean + std = 80)
      - 40 delta-MFCCs (mean + std = 80)
      - 12 chroma (mean + std = 24)
      - 7 spectral contrast (mean + std = 14)
      - 1 ZCR (mean + std = 2)
    Hace resample a 22 050 Hz para que los features sean comparables.
    """
    if len(audio_data) == 0:
        raise ValueError("Audio vacío.")

    # Asegurar float64 para librosa
    audio_data = audio_data.astype(np.float64)

    # Resample al estándar de librosa
    if sample_rate != AUDIO_SR:
        audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=AUDIO_SR)

    # ── MFCCs ──
    mfccs = librosa.feature.mfcc(y=audio_data, sr=AUDIO_SR, n_mfcc=N_MFCC)
    mfcc_mean = np.mean(mfccs.T, axis=0)
    mfcc_std  = np.std(mfccs.T, axis=0)

    # ── Delta MFCCs (velocidad de cambio temporal) ──
    delta_mfccs = librosa.feature.delta(mfccs)
    delta_mean  = np.mean(delta_mfccs.T, axis=0)
    delta_std   = np.std(delta_mfccs.T, axis=0)

    # ── Chroma (distribución tonal — 12 semitonos) ──
    chroma = librosa.feature.chroma_stft(y=audio_data, sr=AUDIO_SR)
    chroma_mean = np.mean(chroma.T, axis=0)
    chroma_std  = np.std(chroma.T, axis=0)

    # ── Spectral Contrast (7 sub-bandas) ──
    contrast = librosa.feature.spectral_contrast(y=audio_data, sr=AUDIO_SR)
    contrast_mean = np.mean(contrast.T, axis=0)
    contrast_std  = np.std(contrast.T, axis=0)

    # ── Zero Crossing Rate ──
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
    """Red neuronal densa con BatchNorm para clasificación de voz (200 features)."""
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
    aumentar el dataset × factor, mejorando generalización con pocos audios.
    """
    X_aug, y_aug = [X], [y]
    for _ in range(factor - 1):
        noise = np.random.normal(0, 0.02, X.shape).astype(np.float32)
        X_aug.append(X + noise)
        y_aug.append(y)
    return np.concatenate(X_aug), np.concatenate(y_aug)

# ─── Endpoints ───────────────────────────────────────────────────────────────

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
        raise HTTPException(400, "El nombre no puede estar vacío.")

    try:
        audio_bytes = base64.b64decode(payload.audio_b64)
    except Exception:
        raise HTTPException(400, "audio_b64 no es base64 válido.")

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

    # Normalización (z-score) — guardamos media y std para la predicción
    norm_mean = X.mean(axis=0)
    norm_std  = X.std(axis=0) + 1e-8
    X = (X - norm_mean) / norm_std

    # Data augmentation: genera copias con ruido para mejorar generalización
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
    """Predice a quién pertenece un audio."""
    if state.model is None:
        raise HTTPException(400, "No hay modelo de audio entrenado. Llama /audio/train primero.")

    try:
        audio_bytes = base64.b64decode(payload.audio_b64)
    except Exception:
        raise HTTPException(400, "audio_b64 no es base64 válido.")

    audio_array = np.frombuffer(audio_bytes, dtype=np.float32)

    if len(audio_array) < 1000:
        raise HTTPException(400, "Audio demasiado corto.")

    try:
        features = process_audio(audio_array, payload.sample_rate)
    except Exception as e:
        raise HTTPException(500, f"Error procesando audio: {e}")

    # Normalizar con las mismas estadísticas del entrenamiento
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


@app.get("/audio/export/python")
def export_python():
    """Genera y devuelve voice_recognizer.py listo para descargar."""
    if state.model is None:
        raise HTTPException(400, "No hay modelo entrenado.")

    label_map  = {str(k): v for k, v in state.label_map.items()}
    norm_mean  = state.norm_mean.tolist()
    norm_std   = state.norm_std.tolist()
    weights    = [w.tolist() for w in state.model.get_weights()]
    users_list = list(state.label_map.values())

    code = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"
        voice_recognizer.py — Generado por BloontAI Voice Recognition
        Usuarios: {', '.join(users_list)}

        Dependencias:
          pip install numpy librosa fastapi uvicorn

        Uso:
          python voice_recognizer.py
          # POST http://localhost:8001/audio/predict
          # Body: {{ "audio_b64": "<pcm-float32-base64>", "sample_rate": 48000 }}
        \"\"\"

        from __future__ import annotations
        import base64
        import numpy as np
        import librosa
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel

        LABEL_MAP  = {json.dumps(label_map)}
        NORM_MEAN  = np.array({json.dumps(norm_mean)}, dtype=np.float32)
        NORM_STD   = np.array({json.dumps(norm_std)},  dtype=np.float32)
        WEIGHTS    = [np.array(w, dtype=np.float32) for w in {json.dumps(weights)}]

        AUDIO_SR = 22050
        N_MFCC   = 40

        def _relu(x):        return np.maximum(0, x)
        def _softmax(x):     e = np.exp(x - x.max()); return e / e.sum()
        def _dense(x, W, b): return x @ W + b
        def _bn(x, g, b, m, v, eps=1e-3): return g * (x - m) / np.sqrt(v + eps) + b

        def _forward(x):
            W = WEIGHTS
            x = _relu(_bn(_dense(x, W[0], W[1]),  W[2],  W[3],  W[4],  W[5]))
            x = _relu(_bn(_dense(x, W[6], W[7]),  W[8],  W[9],  W[10], W[11]))
            x = _relu(_dense(x, W[12], W[13]))
            return _softmax(_dense(x, W[14], W[15]))

        def extract_features(audio: np.ndarray, sr: int = 48000) -> np.ndarray:
            audio = audio.astype(np.float64)
            if sr != AUDIO_SR:
                audio = librosa.resample(audio, orig_sr=sr, target_sr=AUDIO_SR)
            mfccs    = librosa.feature.mfcc(y=audio, sr=AUDIO_SR, n_mfcc=N_MFCC)
            deltas   = librosa.feature.delta(mfccs)
            chroma   = librosa.feature.chroma_stft(y=audio, sr=AUDIO_SR)
            contrast = librosa.feature.spectral_contrast(y=audio, sr=AUDIO_SR)
            zcr      = librosa.feature.zero_crossing_rate(y=audio)
            return np.concatenate([
                np.mean(mfccs.T,    0), np.std(mfccs.T,    0),
                np.mean(deltas.T,   0), np.std(deltas.T,   0),
                np.mean(chroma.T,   0), np.std(chroma.T,   0),
                np.mean(contrast.T, 0), np.std(contrast.T, 0),
                [np.mean(zcr),          np.std(zcr)],
            ]).astype(np.float32)

        app = FastAPI(title="BloontAI Voice Recognizer")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
        )

        class Payload(BaseModel):
            audio_b64:   str
            sample_rate: int = 48000

        @app.post("/audio/predict")
        def predict(payload: Payload):
            raw   = base64.b64decode(payload.audio_b64)
            audio = np.frombuffer(raw, dtype=np.float32)
            if len(audio) < 1000:
                raise HTTPException(400, "Audio demasiado corto.")
            feat  = extract_features(audio, payload.sample_rate)
            feat  = (feat - NORM_MEAN) / NORM_STD
            probs = _forward(feat)
            idx   = int(np.argmax(probs))
            return {{
                "label":         LABEL_MAP[str(idx)],
                "confidence":    round(float(probs[idx]), 4),
                "probabilities": {{LABEL_MAP[str(i)]: round(float(p), 4) for i, p in enumerate(probs)}},
            }}

        @app.get("/")
        def root():
            return {{"status": "ok", "users": list(LABEL_MAP.values())}}

        if __name__ == "__main__":
            import uvicorn
            uvicorn.run("voice_recognizer:app", host="0.0.0.0", port=8001, reload=False)
        """)

    return Response(
        content=code,
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="voice_recognizer.py"'},
    )


@app.get("/audio/export/js")
def export_js():
    """Genera y devuelve voice_recognizer.js listo para descargar."""
    if state.model is None:
        raise HTTPException(400, "No hay modelo entrenado.")

    users_list = list(state.label_map.values())

    code = textwrap.dedent(f"""\
        /**
         * voice_recognizer.js — Generado por BloontAI Voice Recognition
         * Usuarios: {', '.join(users_list)}
         *
         * Requiere el servidor Python en ejecucion:
         *   python voice_recognizer.py   (escucha en http://localhost:8001)
         *
         * Uso:
         *   <script src="voice_recognizer.js"></script>
         *
         *   VoiceRecognizer.predict()
         *     .then(r => console.log(r.label, r.confidence));
         *
         *   VoiceRecognizer.startListening(
         *     result => console.log(result.label, result.probabilities),
         *     error  => console.error(error)
         *   );
         *   VoiceRecognizer.stopListening();
         */
        const VoiceRecognizer = (function () {{
          'use strict';

          var SERVER   = 'http://localhost:8001';
          var SR       = 48000;
          var SECONDS  = 3;

          function float32ToBase64(arr) {{
            var b = new Uint8Array(arr.buffer), s = '';
            for (var i = 0; i < b.byteLength; i++) s += String.fromCharCode(b[i]);
            return btoa(s);
          }}

          function sleep(ms) {{ return new Promise(function(r){{ setTimeout(r, ms); }}); }}

          function record() {{
            return navigator.mediaDevices.getUserMedia({{
              audio: {{ sampleRate: SR, channelCount: 1, echoCancellation: false, noiseSuppression: false }},
            }}).then(function(stream) {{
              return new Promise(function(resolve) {{
                var ctx  = new AudioContext({{ sampleRate: SR }});
                var src  = ctx.createMediaStreamSource(stream);
                var proc = ctx.createScriptProcessor(4096, 1, 1);
                var buf  = [];
                proc.onaudioprocess = function(e) {{
                  buf.push(new Float32Array(e.inputBuffer.getChannelData(0)));
                }};
                src.connect(proc); proc.connect(ctx.destination);
                sleep(SECONDS * 1000).then(function() {{
                  proc.disconnect(); src.disconnect();
                  stream.getTracks().forEach(function(t){{ t.stop(); }});
                  ctx.close().then(function() {{
                    var len = buf.reduce(function(a,c){{ return a+c.length; }}, 0);
                    var pcm = new Float32Array(len), off = 0;
                    buf.forEach(function(c){{ pcm.set(c, off); off += c.length; }});
                    resolve(pcm);
                  }});
                }});
              }});
            }});
          }}

          function sendAudio(pcm) {{
            return fetch(SERVER + '/audio/predict', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ audio_b64: float32ToBase64(pcm), sample_rate: SR }}),
            }}).then(function(r) {{
              if (!r.ok) return r.json().then(function(e){{ throw new Error(e.detail || r.status); }});
              return r.json();
            }});
          }}

          var _active = false, _stop = false;

          return {{
            setServer: function(url) {{ SERVER = url; }},
            setSeconds: function(s)  {{ SECONDS = s;  }},
            isListening: function()  {{ return _active; }},

            predict: function() {{
              return record().then(sendAudio);
            }},

            startListening: function(onResult, onError) {{
              if (_active) return;
              _active = true; _stop = false;
              (function loop() {{
                if (_stop) {{ _active = false; return; }}
                record().then(sendAudio)
                  .then(function(r)  {{ if (!_stop && onResult) onResult(r); return sleep(300); }})
                  .catch(function(e) {{ if (onError) onError(e); return sleep(500); }})
                  .then(loop);
              }})();
            }},

            stopListening: function() {{ _stop = true; }},
          }};
        }}());
        """)

    return Response(
        content=code,
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="voice_recognizer.js"'},
    )

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("modeloAudio:app", host="0.0.0.0", port=8001, reload=False)
