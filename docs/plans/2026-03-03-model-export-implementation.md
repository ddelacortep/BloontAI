# Model Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Agregar un endpoint `GET /export` al backend y un botón "Exportar modelo" al frontend, que descarga un ZIP con el modelo entrenado en formato Keras H5 y TensorFlow.js (con fallback gracioso si tensorflowjs no está instalado), más archivos de ejemplo de uso en JavaScript y Python.

**Architecture:** El backend genera un ZIP en memoria con `io.BytesIO` + `zipfile.ZipFile`. Siempre incluye `keras/model.h5`. Si `tensorflowjs` está importable, también incluye `tfjs/model.json` + pesos. Si no, incluye `COMO_CONVERTIR.md` con instrucciones. El frontend añade `isExporting` como estado reactivo y una función `exportModel()` que hace fetch del blob y lo descarga via `<a>` temporal.

**Tech Stack:** FastAPI, TensorFlow/Keras, zipfile (stdlib), io (stdlib), tempfile (stdlib), shutil (stdlib), Vue 3 Composition API

---

## Resumen de archivos a tocar

- Modify: `backend/Modelos/modeloImagenes.py` — agregar imports + endpoint `GET /export`
- Modify: `frontend/src/views/ModeloImagenes.vue` — agregar `isExporting`, `exportModel()`, botón en template

---

## Task 1: Backend — detección de tensorflowjs y helper de conversión TF.js

**Archivos:**
- Modify: `backend/Modelos/modeloImagenes.py` (al inicio, zona de imports)

**Contexto:** El paquete `tensorflowjs` puede no estar instalado (deps pesadas: jax, flax). Hacemos import opcional. Si está disponible, la conversión se hace con `tensorflowjs.converters.save_keras_model()`. Si no, se incluye un archivo Markdown con instrucciones.

**Step 1: Agregar imports necesarios al inicio del archivo**

En `backend/Modelos/modeloImagenes.py`, justo después del bloque de imports existentes (línea 13, antes de `from __future__`), agregar:

```python
import io
import json
import shutil
import tempfile
import zipfile
```

**Nota:** `io` ya está importado. Agregar solo `json`, `shutil`, `tempfile`, `zipfile`.

**Step 2: Agregar detección de tensorflowjs**

Justo después de todos los imports (después de `from PIL import Image`), agregar:

```python
# Detección opcional de tensorflowjs (puede no estar instalado)
try:
    import tensorflowjs as tfjs
    _HAS_TFJS = True
except ImportError:
    _HAS_TFJS = False
```

**Step 3: Verificar manualmente en la terminal que el archivo parsea sin errores**

```bash
cd /Users/daniel/Desktop/BloontAI/backend
python3 -c "import ast; ast.parse(open('Modelos/modeloImagenes.py').read()); print('OK')"
```

Resultado esperado: `OK`

**Step 4: Commit**

```bash
git add backend/Modelos/modeloImagenes.py
git commit -m "feat(backend): add optional tensorflowjs import detection"
```

---

## Task 2: Backend — helper que genera el contenido del ZIP en memoria

**Archivos:**
- Modify: `backend/Modelos/modeloImagenes.py` — agregar función `_build_export_zip()`

**Contexto:** Esta función encapsula toda la lógica de generación del ZIP para mantener el endpoint limpio. Usa un directorio temporal para la conversión TF.js (tensorflowjs necesita disco), luego empaqueta todo en `io.BytesIO`.

**Step 1: Agregar la función helper después de la función `build_model` (aprox línea 195)**

```python
# ─── Helper de exportación ────────────────────────────────────────────────────

_INSTRUCTIONS_MD = """\
# Cómo convertir el modelo a TensorFlow.js

El paquete `tensorflowjs` no estaba instalado al momento de exportar.
Para convertir el modelo Keras a formato TF.js, ejecuta:

```bash
pip install tensorflowjs
tensorflowjs_converter --input_format=keras keras/model.h5 tfjs/
```

Esto generará `tfjs/model.json` y los archivos de pesos binarios.
"""

_JS_EXAMPLE = """\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Clasificador — TF.js</title>
  <script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.22.0/dist/tf.min.js"></script>
</head>
<body>
  <h2>Clasificador de imágenes</h2>
  <p><strong>Sirve esta carpeta con:</strong> <code>python -m http.server 8080</code><br>
  Luego abre <code>http://localhost:8080/uso_javascript.html</code></p>
  <video id="video" autoplay muted playsinline width="320" height="240"></video><br>
  <button id="start">▶ Iniciar cámara</button>
  <button id="stop" disabled>⏹ Detener</button>
  <p id="result">—</p>
  <script>
    // Nombres de clases en orden de índice (cargados desde class_names.json)
    let classNames = [];
    let model = null;
    let timer = null;

    async function init() {
      const resp = await fetch('class_names.json');
      classNames = await resp.json();

      // Cargar modelo TF.js desde la subcarpeta tfjs/
      model = await tf.loadLayersModel('tfjs/model.json');
      console.log('Modelo cargado:', model.inputs[0].shape);
    }

    async function predict(videoEl) {
      const canvas = document.createElement('canvas');
      canvas.width = 224; canvas.height = 224;
      const ctx = canvas.getContext('2d');
      const crop = Math.min(videoEl.videoWidth, videoEl.videoHeight);
      const ox = (videoEl.videoWidth  - crop) / 2;
      const oy = (videoEl.videoHeight - crop) / 2;
      ctx.drawImage(videoEl, ox, oy, crop, crop, 0, 0, 224, 224);

      // Preprocesado igual que MobileNetV2: normalizar a [-1, 1]
      const tensor = tf.browser.fromPixels(canvas)
        .toFloat()
        .div(127.5)
        .sub(1.0)
        .expandDims(0);  // [1, 224, 224, 3]

      const probs = model.predict(tensor);
      const values = await probs.data();
      const bestIdx = values.indexOf(Math.max(...values));
      const bestProb = (values[bestIdx] * 100).toFixed(0);
      document.getElementById('result').textContent =
        `${classNames[bestIdx]}  ${bestProb}%`;

      tensor.dispose(); probs.dispose();
    }

    document.getElementById('start').onclick = async () => {
      if (!model) await init();
      const stream = await navigator.mediaDevices.getUserMedia({video: true});
      const vid = document.getElementById('video');
      vid.srcObject = stream; await vid.play();
      document.getElementById('start').disabled = true;
      document.getElementById('stop').disabled = false;
      timer = setInterval(() => predict(vid), 600);
    };

    document.getElementById('stop').onclick = () => {
      clearInterval(timer);
      const vid = document.getElementById('video');
      vid.srcObject?.getTracks().forEach(t => t.stop());
      vid.srcObject = null;
      document.getElementById('start').disabled = false;
      document.getElementById('stop').disabled = true;
    };
  </script>
</body>
</html>
"""

_PY_EXAMPLE = """\
\"\"\"
Ejemplo de uso del modelo exportado en Python.
Requiere: tensorflow, Pillow

  pip install tensorflow Pillow
  python uso_python.py ruta/a/imagen.jpg
\"\"\"
import sys, json
import numpy as np
from PIL import Image
import tensorflow as tf
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

# Cargar nombres de clase
with open('class_names.json') as f:
    class_names = json.load(f)

# Cargar modelo
model = tf.keras.models.load_model('keras/model.h5')

def classify(image_path: str) -> tuple[str, float]:
    img = Image.open(image_path).convert('RGB').resize((224, 224))
    arr = np.array(img, dtype=np.float32)
    arr = preprocess_input(arr)              # Normalizar a [-1, 1]
    arr = np.expand_dims(arr, 0)             # [1, 224, 224, 3]
    probs = model.predict(arr, verbose=0)[0]
    idx = int(np.argmax(probs))
    return class_names[idx], float(probs[idx])

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Uso: python uso_python.py <ruta_imagen>")
        sys.exit(1)
    label, confidence = classify(path)
    print(f"Clase: {label}  |  Confianza: {confidence:.2%}")
"""


def _build_export_zip(model: tf.keras.Model, class_names: list[str]) -> io.BytesIO:
    """
    Construye un ZIP en memoria con el modelo exportado en múltiples formatos.

    Contenido garantizado:
      keras/model.h5       — modelo Keras completo
      class_names.json     — lista ordenada de nombres de clase
      uso_javascript.html  — demo standalone con TF.js
      uso_python.py        — script de inferencia en Python

    Contenido opcional (si tensorflowjs está instalado):
      tfjs/model.json      — topología del modelo en formato TF.js
      tfjs/*.bin           — pesos del modelo en binario

    Si tensorflowjs no está instalado:
      COMO_CONVERTIR.md    — instrucciones para convertir manualmente
    """
    buf = io.BytesIO()
    tmp_dir = tempfile.mkdtemp(prefix="bloont_export_")

    try:
        # 1. Guardar Keras H5
        keras_dir = f"{tmp_dir}/keras"
        import os
        os.makedirs(keras_dir, exist_ok=True)
        model.save(f"{keras_dir}/model.h5")

        # 2. Convertir a TF.js si el paquete está disponible
        tfjs_files: dict[str, bytes] = {}
        if _HAS_TFJS:
            tfjs_dir = f"{tmp_dir}/tfjs"
            os.makedirs(tfjs_dir, exist_ok=True)
            tfjs.converters.save_keras_model(model, tfjs_dir)
            # Leer todos los archivos generados
            for fname in os.listdir(tfjs_dir):
                with open(f"{tfjs_dir}/{fname}", 'rb') as fh:
                    tfjs_files[f"tfjs/{fname}"] = fh.read()

        # 3. Empaquetar en ZIP
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Keras H5
            with open(f"{keras_dir}/model.h5", 'rb') as fh:
                zf.writestr("keras/model.h5", fh.read())

            # TF.js (si disponible) o instrucciones de conversión
            if tfjs_files:
                for path, data in tfjs_files.items():
                    zf.writestr(path, data)
            else:
                zf.writestr("COMO_CONVERTIR.md", _INSTRUCTIONS_MD)

            # Nombres de clase
            zf.writestr("class_names.json", json.dumps(class_names, ensure_ascii=False, indent=2))

            # Ejemplos de uso
            zf.writestr("uso_javascript.html", _JS_EXAMPLE)
            zf.writestr("uso_python.py", _PY_EXAMPLE)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    buf.seek(0)
    return buf
```

**Step 2: Verificar sintaxis**

```bash
cd /Users/daniel/Desktop/BloontAI/backend
python3 -c "import ast; ast.parse(open('Modelos/modeloImagenes.py').read()); print('OK')"
```

Resultado esperado: `OK`

**Step 3: Commit**

```bash
git add backend/Modelos/modeloImagenes.py
git commit -m "feat(backend): add _build_export_zip helper with Keras H5 and optional TF.js"
```

---

## Task 3: Backend — endpoint `GET /export`

**Archivos:**
- Modify: `backend/Modelos/modeloImagenes.py` — agregar endpoint después del endpoint `/reset`

**Step 1: Agregar import de StreamingResponse en la zona de imports de FastAPI**

En la línea que dice:
```python
from fastapi import FastAPI, HTTPException
```

Cambiar a:
```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
```

**Step 2: Agregar el endpoint `GET /export` después del endpoint `/reset` (aprox línea 329)**

```python
@app.get("/export")
def export_model():
    """
    Exporta el modelo entrenado como un archivo ZIP con:
      - keras/model.h5          (siempre)
      - tfjs/model.json + .bin  (si tensorflowjs está instalado)
      - class_names.json
      - uso_javascript.html
      - uso_python.py

    Devuelve un StreamingResponse que el navegador descarga como
    'modelo_exportado.zip'.
    """
    if state.model is None:
        raise HTTPException(400, "No hay modelo entrenado. Llama /train primero.")

    zip_buf = _build_export_zip(state.model, state.class_names)

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=modelo_exportado.zip"},
    )
```

**Step 3: Verificar sintaxis**

```bash
cd /Users/daniel/Desktop/BloontAI/backend
python3 -c "import ast; ast.parse(open('Modelos/modeloImagenes.py').read()); print('OK')"
```

Resultado esperado: `OK`

**Step 4: Verificar que FastAPI puede cargar el módulo (sin iniciar el servidor)**

```bash
cd /Users/daniel/Desktop/BloontAI/backend
python3 -c "
import sys; sys.path.insert(0, 'Modelos')
from Modelos import modeloImagenes
routes = [r.path for r in modeloImagenes.app.routes]
print('Rutas:', routes)
assert '/export' in routes, 'Falta /export!'
print('OK — endpoint /export registrado')
"
```

Resultado esperado: muestra lista de rutas incluyendo `/export` y `OK — endpoint /export registrado`

**Step 5: Commit**

```bash
git add backend/Modelos/modeloImagenes.py
git commit -m "feat(backend): add GET /export endpoint returning ZIP with trained model"
```

---

## Task 4: Frontend — estado reactivo y función `exportModel()`

**Archivos:**
- Modify: `frontend/src/views/ModeloImagenes.vue` — sección `<script setup>`

**Contexto:** La función hace fetch a `/api/export`, recibe el blob ZIP y lo descarga creando un `<a>` temporal en el DOM. No necesita procesar el contenido, solo disparar la descarga del browser.

**Step 1: Agregar `isExporting` al bloque de estado del entrenamiento**

En la sección `// ─── Estado del entrenamiento ─────────────────────────────────────────────────`:

Después de `const trainingAccuracy   = ref(null)`, agregar:

```javascript
const isExporting        = ref(false)   // True mientras el ZIP se está generando/descargando
```

**Step 2: Agregar la función `exportModel()` después de `trainModel()` (aprox línea 250)**

```javascript
// ─── Exportación del modelo ───────────────────────────────────────────────────

/**
 * Solicita al backend el ZIP con el modelo exportado y lo descarga en el browser.
 * Usa un <a> temporal con URL.createObjectURL para disparar la descarga sin abrir
 * una nueva pestaña ni redirigir la página.
 */
async function exportModel() {
  if (isExporting.value) return
  isExporting.value = true
  try {
    const response = await fetch(`${API}/export`)
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }
    const blob = await response.blob()
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = 'modelo_exportado.zip'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (err) {
    alert('❌ Error al exportar: ' + err.message)
  } finally {
    isExporting.value = false
  }
}
```

**Step 3: Verificar que el archivo Vue no tiene errores de sintaxis**

```bash
cd /Users/daniel/Desktop/BloontAI/frontend
node -e "
const fs = require('fs');
const content = fs.readFileSync('src/views/ModeloImagenes.vue', 'utf8');
// Verificar que isExporting y exportModel están presentes
if (!content.includes('isExporting')) throw new Error('Falta isExporting');
if (!content.includes('exportModel')) throw new Error('Falta exportModel');
console.log('OK');
"
```

Resultado esperado: `OK`

**Step 4: Commit**

```bash
git add frontend/src/views/ModeloImagenes.vue
git commit -m "feat(frontend): add isExporting state and exportModel() function"
```

---

## Task 5: Frontend — botón "Exportar modelo" en el template

**Archivos:**
- Modify: `frontend/src/views/ModeloImagenes.vue` — sección `<template>` y `<style scoped>`

**Contexto:** El botón aparece solo cuando `isTrainingComplete === true`. Se coloca debajo del `accuracy-badge` en el panel central de entrenamiento. Muestra estado de carga mientras exporta.

**Step 1: Agregar el botón en el template**

Localizar en el template el bloque del `accuracy-badge`:

```html
          <!-- Insignia con la precisión de validación final -->
          <div v-if="isTrainingComplete" class="accuracy-badge">
            ✅ Precisión: <strong>{{ (trainingAccuracy * 100).toFixed(1) }}%</strong>
          </div>
```

Después de ese `</div>`, agregar:

```html
          <!-- Botón de exportación del modelo entrenado -->
          <button
            v-if="isTrainingComplete"
            class="btn btn-export"
            :disabled="isExporting"
            @click="exportModel"
            style="width:100%; margin-top:0.6rem; justify-content:center;"
          >
            {{ isExporting ? '⏳ Exportando…' : '📥 Exportar modelo' }}
          </button>
```

**Step 2: Agregar el estilo del botón al bloque `<style scoped>`**

Al final de la sección `/* ─── Botones ─────────────────────────────────────────────────────────────── */`, agregar:

```css
.btn-export {
  background: #1B512D;
  color: #fff;
}
.btn-export:hover:not(:disabled) { background: #2d6a4f; }
```

**Step 3: Verificar template y estilos**

```bash
cd /Users/daniel/Desktop/BloontAI/frontend
node -e "
const fs = require('fs');
const content = fs.readFileSync('src/views/ModeloImagenes.vue', 'utf8');
if (!content.includes('btn-export')) throw new Error('Falta clase btn-export');
if (!content.includes('exportModel')) throw new Error('Falta @click=exportModel en template');
if (!content.includes('isExporting')) throw new Error('Falta isExporting en template');
console.log('OK');
"
```

Resultado esperado: `OK`

**Step 4: Commit**

```bash
git add frontend/src/views/ModeloImagenes.vue
git commit -m "feat(frontend): add export model button to training panel"
```

---

## Task 6: Verificación de integración manual

**Contexto:** No hay test runner configurado en este proyecto. La verificación se hace iniciando el servidor y probando el flujo completo.

**Step 1: Iniciar el backend**

```bash
cd /Users/daniel/Desktop/BloontAI/backend
uvicorn Modelos.modeloImagenes:app --host 0.0.0.0 --port 8000 --reload
```

**Step 2: Verificar que el endpoint /export aparece en la documentación de FastAPI**

Abrir en el browser: `http://localhost:8000/docs`

Verificar que existe el endpoint `GET /export`.

**Step 3: Verificar respuesta cuando no hay modelo entrenado**

```bash
curl -s http://localhost:8000/export | python3 -m json.tool
```

Resultado esperado:
```json
{"detail": "No hay modelo entrenado. Llama /train primero."}
```

**Step 4: Iniciar el frontend**

En otra terminal:
```bash
cd /Users/daniel/Desktop/BloontAI/frontend
npm run dev
```

**Step 5: Verificar flujo completo en browser**

1. Abrir la app en `http://localhost:5173`
2. Navegar a ModeloImagenes
3. Capturar imágenes de 2 clases
4. Entrenar el modelo
5. Verificar que aparece el botón "📥 Exportar modelo" debajo del accuracy badge
6. Hacer clic — verificar que el botón cambia a "⏳ Exportando…" durante la descarga
7. Verificar que el browser descarga `modelo_exportado.zip`
8. Descomprimir el ZIP y verificar su contenido:
   - `keras/model.h5` existe y tiene tamaño > 0
   - `class_names.json` contiene los nombres de las clases entrenadas
   - `uso_javascript.html` existe
   - `uso_python.py` existe
   - `tfjs/model.json` o `COMO_CONVERTIR.md` existe

**Step 6: Verificar el script Python de ejemplo**

```bash
cd /ruta/donde/descomprimiste/el/zip
python3 uso_python.py
```

Resultado esperado: `Uso: python uso_python.py <ruta_imagen>`

**Step 7: Commit final**

```bash
git add -A
git commit -m "feat: model export — ZIP with Keras H5 + optional TF.js + usage examples"
```

---

## Checklist de incongruencias ya resueltas

| Riesgo | Resolución en el plan |
|---|---|
| `tensorflowjs` puede no estar instalado | Fallback gracioso: se incluye `COMO_CONVERTIR.md` |
| `io` ya estaba importado | Se agregan solo los imports faltantes |
| `StreamingResponse` no estaba importado | Se agrega explícitamente en Task 3 Step 1 |
| El directorio temporal de tfjs necesita `os.makedirs` | Se hace en `_build_export_zip` antes de escribir |
| Botón visible durante entrenamiento | `v-if="isTrainingComplete"` lo previene |
| El ZIP puede tardar (modelo ~14MB) | Estado `isExporting` desactiva el botón y cambia el texto |
| CORS al cargar model.json con `file://` | HTML de ejemplo incluye instrucción `python -m http.server` |
