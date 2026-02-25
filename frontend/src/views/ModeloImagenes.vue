<script setup>
/**
 * ModeloImagenes.vue — Script principal
 *
 * Gestiona el flujo completo de clasificación de imágenes con Transfer Learning:
 *   1. Captura de fotos desde la webcam, agrupadas por clase (etiqueta).
 *   2. Entrenamiento del modelo MobileNetV2 en el backend (FastAPI + TensorFlow).
 *   3. Predicción en tiempo real sobre el feed de la webcam.
 *
 * Endpoints del backend (modeloImagenes.py):
 *   POST   /upload  — guarda imagen etiquetada en RAM (uint8 numpy 224×224)
 *   POST   /train   — entrena el modelo con Transfer Learning (MobileNetV2)
 *   POST   /predict — clasifica un frame y devuelve clase + probabilidades
 *   DELETE /reset   — limpia imágenes y modelo de la memoria
 *
 * Comunicación: Vite reescribe las rutas /api/* al backend en localhost:8000.
 */
import { ref, reactive, computed, nextTick, onUnmounted } from 'vue'
import Header from './components/Header.vue'

// ════════════════════════════════════════════════════════════════════════════
// CONSTANTES
// ════════════════════════════════════════════════════════════════════════════

/** Prefijo de rutas API — Vite lo reescribe a http://localhost:8000 */
const API = '/api'

/** Paleta de colores para distinguir visualmente cada clase en la UI */
const PALETTE = ['#7c3aed', '#059669', '#0369a1', '#d97706', '#dc2626', '#0891b2', '#65a30d']

/** Tamaño en px al que se recorta/escala cada frame (debe coincidir con IMG_SIZE del backend) */
const FRAME_SIZE = 224

/** Número de fotos que se capturan por clase en cada ráfaga */
const CAPTURES_PER_BURST = 15

/** Pausa entre capturas consecutivas en ms (evita frames duplicados) */
const CAPTURE_DELAY_MS = 150

/** Intervalo de predicción en tiempo real en ms */
const PREDICT_INTERVAL_MS = 600

/** Número de clases al arrancar la app */
const INITIAL_CLASS_COUNT = 2

/** Mínimo de imágenes por clase para habilitar el entrenamiento */
const MIN_IMAGES_PER_CLASS = 5

/** Mínimo de clases con datos para habilitar el entrenamiento */
const MIN_CLASSES = 2

/** Máximo de líneas de log de predicción visibles */
const MAX_LOG_LINES = 25

// ════════════════════════════════════════════════════════════════════════════
// HELPERS PUROS (sin estado reactivo)
// ════════════════════════════════════════════════════════════════════════════

/** Promesa que se resuelve tras `ms` milisegundos */
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Fábrica de objetos de clase con valores por defecto.
 * Centraliza la estructura para evitar duplicación.
 * @param {number} id    — identificador único autoincremental
 * @param {string} color — color de acento visual (de PALETTE)
 */
function createClass(id, color) {
  return {
    id,
    name: '',
    imageCount: 0,
    color,
    cameraOn: false,
    capturing: false,
    capturePct: 0,
    captureMsg: '',
  }
}

/**
 * Captura el frame actual de un elemento <video> y lo devuelve como base64 JPEG.
 *
 * Pipeline:
 *   1. Calcula el cuadrado central del vídeo (recorte centrado, evita deformaciones).
 *   2. Lo dibuja en un <canvas> temporal de FRAME_SIZE × FRAME_SIZE px.
 *   3. Exporta como JPEG con calidad 0.85.
 *   4. Devuelve solo la cadena base64 (sin prefijo "data:image/jpeg;base64,").
 *
 * El backend espera exactamente este formato en los campos image_b64.
 *
 * @param {HTMLVideoElement} videoEl — elemento <video> con srcObject activo
 * @returns {string} cadena base64 del JPEG de 224×224
 */
function frameToBase64(videoEl) {
  const canvas = document.createElement('canvas')
  canvas.width = FRAME_SIZE
  canvas.height = FRAME_SIZE
  const ctx = canvas.getContext('2d')

  // Recorte cuadrado centrado: toma el lado menor del vídeo y centra el corte
  const side = Math.min(videoEl.videoWidth, videoEl.videoHeight)
  const sx = (videoEl.videoWidth - side) / 2
  const sy = (videoEl.videoHeight - side) / 2

  ctx.drawImage(videoEl, sx, sy, side, side, 0, 0, FRAME_SIZE, FRAME_SIZE)

  // toDataURL → "data:image/jpeg;base64,<datos>" → nos quedamos solo con <datos>
  return canvas.toDataURL('image/jpeg', 0.85).split(',')[1]
}

/**
 * Wrapper para llamadas HTTP al backend. Lanza Error si la respuesta no es 2xx.
 * Centraliza headers y manejo de errores para no repetir fetch + json + check
 * en cada función que llama al API.
 *
 * @param {string}  endpoint — ruta relativa (ej. '/upload', '/train')
 * @param {object}  options  — opciones de fetch (method, body, etc.)
 * @returns {Promise<any>} datos JSON parseados de la respuesta
 * @throws {Error} con el detalle del backend o el código HTTP
 */
async function apiFetch(endpoint, options = {}) {
  const res = await fetch(`${API}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data.detail || `HTTP ${res.status}`)
  }
  return data
}

// ════════════════════════════════════════════════════════════════════════════
// ESTADO REACTIVO — Clases y captura
// ════════════════════════════════════════════════════════════════════════════

/**
 * Array reactivo de clases. Cada objeto representa una categoría de objetos
 * que el usuario quiere enseñar al modelo (ej.: "gato", "perro").
 * Se inicia con INITIAL_CLASS_COUNT clases vacías.
 */
const classes = reactive(
  Array.from({ length: INITIAL_CLASS_COUNT }, (_, i) =>
    createClass(i + 1, PALETTE[i % PALETTE.length])
  )
)

/** Contador autoincremental para IDs únicos de clase */
let nextId = INITIAL_CLASS_COUNT + 1

/** Refs dinámicos: mapean cls.id → HTMLVideoElement del <video> de esa tarjeta */
const videoEls = reactive({})

/** Refs dinámicos: mapean cls.id → MediaStream activo de esa tarjeta */
const streams = reactive({})

// ════════════════════════════════════════════════════════════════════════════
// ESTADO REACTIVO — Fase de la aplicación
// ════════════════════════════════════════════════════════════════════════════

/**
 * Fase actual del flujo de trabajo:
 *   'capture'  — el usuario captura imágenes y etiqueta clases
 *   'training' — el modelo se está entrenando en el backend
 *   'predict'  — el modelo está listo, se puede predecir en tiempo real
 */
const phase = ref('capture')

// ════════════════════════════════════════════════════════════════════════════
// ESTADO REACTIVO — Entrenamiento
// ════════════════════════════════════════════════════════════════════════════

/** true mientras la petición POST /train está en vuelo */
const trainRunning = ref(false)

/** Mensaje de estado que se muestra bajo la barra de progreso */
const trainMsg = ref('')

/** Porcentaje visual de progreso de entrenamiento (0 – 100) */
const trainPct = ref(0)

/** Se pone a true cuando el entrenamiento terminó con éxito */
const trainDone = ref(false)

/** val_accuracy devuelta por el backend tras el entrenamiento */
const trainAccuracy = ref(null)

// ════════════════════════════════════════════════════════════════════════════
// ESTADO REACTIVO — Predicción en tiempo real
// ════════════════════════════════════════════════════════════════════════════

/** Ref al elemento <video> del panel de predicción (enlazado con ref="predictVideoEl") */
const predictVideoEl = ref(null)

/** MediaStream de la cámara abierta para predicción */
const predictStream = ref(null)

/** ID del setInterval que lanza predictFrame() cada PREDICT_INTERVAL_MS */
const predictInterval = ref(null)

/** true mientras el bucle de predicción está activo */
const predicting = ref(false)

/** Etiqueta predicha mostrada en el overlay del vídeo (ej.: "gato") */
const overlayLabel = ref('—')

/** Confianza en formato "94%" mostrada en el overlay */
const overlayConf = ref('')

/** Lista de nombres de clase devueltos por /train (ej.: ["gato", "perro"]) */
const probClasses = ref([])

/** Mapa reactivo { nombreClase: { pct: number } } para las barras de probabilidad */
const probData = reactive({})

/** Últimas MAX_LOG_LINES líneas de log de predicciones (las más recientes arriba) */
const logLines = ref([])

// ════════════════════════════════════════════════════════════════════════════
// PROPIEDADES COMPUTADAS
// ════════════════════════════════════════════════════════════════════════════

/**
 * El botón "Entrenar" se habilita solo cuando:
 *   - Hay al menos MIN_CLASSES (2) clases con nombre no vacío.
 *   - Cada una tiene al menos MIN_IMAGES_PER_CLASS (5) imágenes capturadas.
 */
const canTrain = computed(() => {
  const named = classes.filter((c) => c.name.trim())
  return (
    named.length >= MIN_CLASSES &&
    named.every((c) => c.imageCount >= MIN_IMAGES_PER_CLASS)
  )
})

// ════════════════════════════════════════════════════════════════════════════
// GESTIÓN DE CLASES
// ════════════════════════════════════════════════════════════════════════════

/**
 * Añade una nueva tarjeta de clase vacía al final de la lista.
 * El color se asigna cíclicamente desde PALETTE.
 */
function addClass() {
  const color = PALETTE[classes.length % PALETTE.length]
  classes.push(createClass(nextId++, color))
}

/**
 * Elimina la clase en la posición `idx` del array.
 * Impide bajar de MIN_CLASSES (2) para que siempre se pueda entrenar.
 * Detiene la cámara de esa tarjeta si estaba activa.
 */
function removeClass(idx) {
  if (classes.length <= MIN_CLASSES) return
  stopClassCamera(classes[idx])
  classes.splice(idx, 1)
}

// ════════════════════════════════════════════════════════════════════════════
// CÁMARA POR CLASE (fase de captura)
// ════════════════════════════════════════════════════════════════════════════

/**
 * Enciende o apaga la cámara de una tarjeta de clase.
 * - Si ya está encendida → la apaga liberando el stream.
 * - Si está apagada → solicita acceso con getUserMedia (720p),
 *   espera a que Vue monte el <video> con nextTick y enlaza el stream.
 */
async function toggleCamera(cls) {
  if (cls.cameraOn) {
    stopClassCamera(cls)
    return
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 1280, height: 720 },
    })
    streams[cls.id] = stream
    cls.cameraOn = true

    // nextTick: esperar a que el <video> exista en el DOM (v-if depende de cameraOn)
    await nextTick()
    const el = videoEls[cls.id]
    if (el) {
      el.srcObject = stream
      await el.play().catch(() => {})
    }
  } catch (err) {
    alert('No se pudo acceder a la cámara: ' + err.message)
  }
}

/**
 * Detiene el MediaStream de una clase y desvincula su <video>.
 * Se llama al apagar la cámara, al eliminar una clase y al hacer reset.
 */
function stopClassCamera(cls) {
  if (streams[cls.id]) {
    streams[cls.id].getTracks().forEach((t) => t.stop())
    delete streams[cls.id]
  }
  if (videoEls[cls.id]) {
    videoEls[cls.id].srcObject = null
  }
  cls.cameraOn = false
}

// ════════════════════════════════════════════════════════════════════════════
// CAPTURA DE IMÁGENES
// ════════════════════════════════════════════════════════════════════════════

/**
 * Captura CAPTURES_PER_BURST (15) fotogramas de la cámara de `cls` y los envía
 * al backend uno a uno con POST /upload.
 *
 * Cada fotograma se:
 *   1. Recorta al cuadrado central y escala a 224×224 en un canvas.
 *   2. Codifica como JPEG base64 (sin prefijo data:...).
 *   3. Envía al backend que lo almacena en RAM como array uint8 numpy.
 *
 * Muestra una barra de progreso y mensajes de estado durante la captura.
 * Tras completarse (o fallar), el mensaje desaparece automáticamente.
 */
async function captureImages(cls) {
  // Validaciones previas
  if (!cls.cameraOn || !videoEls[cls.id]) {
    alert('Activa la cámara primero.')
    return
  }
  if (!cls.name.trim()) {
    alert('Escribe el nombre de la clase primero.')
    return
  }

  // Activar estado de captura en la UI
  cls.capturing = true
  cls.capturePct = 0
  cls.captureMsg = ''

  try {
    for (let i = 0; i < CAPTURES_PER_BURST; i++) {
      // Actualizar barra de progreso visual
      cls.captureMsg = `${i + 1} / ${CAPTURES_PER_BURST}`
      cls.capturePct = Math.round(((i + 1) / CAPTURES_PER_BURST) * 100)

      // Capturar frame del vídeo y enviarlo al backend
      const b64 = frameToBase64(videoEls[cls.id])
      await apiFetch('/upload', {
        method: 'POST',
        body: JSON.stringify({ label: cls.name.trim(), image_b64: b64 }),
      })

      cls.imageCount++
      await sleep(CAPTURE_DELAY_MS)
    }

    // Éxito: mostrar confirmación temporal (2 s)
    cls.captureMsg = '✅ Listo'
    setTimeout(() => { cls.capturing = false; cls.captureMsg = '' }, 2000)
  } catch (e) {
    // Error: mostrar mensaje temporal (3 s)
    cls.captureMsg = `❌ Error: ${e.message}`
    setTimeout(() => { cls.capturing = false; cls.captureMsg = '' }, 3000)
  }
}

// ════════════════════════════════════════════════════════════════════════════
// ENTRENAMIENTO
// ════════════════════════════════════════════════════════════════════════════

/**
 * Lanza el entrenamiento del modelo en el backend (POST /train).
 *
 * Lo que hace el backend al recibir esta petición:
 *   1. Convierte los arrays uint8 a float32 con preprocess_input → rango [-1, 1].
 *   2. Construye MobileNetV2 (sin capa top) + cabeza personalizada
 *      (GlobalAveragePooling2D → Dropout(0.3) → Dense(128) → Dropout(0.2) → Dense(n_clases, softmax)).
 *   3. Fine-tune: descongela las últimas 30 capas del backbone MobileNetV2.
 *   4. Entrena con Adam(lr=1e-4), EarlyStopping(patience=5), ReduceLROnPlateau(patience=3).
 *   5. Devuelve: val_accuracy, epochs_run y la lista ordenada de clases.
 *
 * Al completarse con éxito, transiciona `phase` a 'predict' para activar
 * el panel de resultados en tiempo real.
 */
async function trainModel() {
  // Transicionar a fase de entrenamiento
  phase.value = 'training'
  trainRunning.value = true
  trainDone.value = false
  trainPct.value = 15
  trainMsg.value = 'Cargando MobileNetV2…'

  try {
    trainPct.value = 35
    trainMsg.value = 'Entrenando con Transfer Learning…'

    // Petición al backend — puede tardar según nº de imágenes y épocas
    const data = await apiFetch('/train', {
      method: 'POST',
      body: JSON.stringify({ epochs: 20, fine_tune: true }),
    })

    // Actualizar UI con los resultados del entrenamiento
    trainPct.value = 100
    trainMsg.value = `Precisión: ${(data.val_accuracy * 100).toFixed(1)}%  ·  ${data.epochs_run} épocas`
    trainAccuracy.value = data.val_accuracy
    trainDone.value = true

    // Preparar barras de probabilidad para la fase de predicción
    probClasses.value = data.classes
    data.classes.forEach((c) => { probData[c] = { pct: 0 } })

    // FIX: transicionar a 'predict' (antes nunca se asignaba este valor)
    phase.value = 'predict'
  } catch (e) {
    trainMsg.value = '❌ ' + e.message
    // Volver a captura si falla
    phase.value = 'capture'
  } finally {
    trainRunning.value = false
  }
}

// ════════════════════════════════════════════════════════════════════════════
// PREDICCIÓN EN TIEMPO REAL
// ════════════════════════════════════════════════════════════════════════════

/**
 * Abre una cámara independiente para predicción y arranca un bucle que
 * envía un frame al backend cada PREDICT_INTERVAL_MS (600 ms).
 *
 * La cámara de predicción es independiente de las cámaras de captura:
 * se puede predecir mientras las cámaras de las tarjetas están apagadas.
 */
async function startPredictCamera() {
  try {
    // Limpiar stream anterior si lo hubiera
    if (predictStream.value) {
      predictStream.value.getTracks().forEach((t) => t.stop())
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 1280, height: 720 },
    })
    predictStream.value = stream

    // Esperar a que el <video> de predicción esté montado y enlazar el stream
    await nextTick()
    predictVideoEl.value.srcObject = stream
    await predictVideoEl.value.play().catch(() => {})

    // Arrancar bucle de predicción
    predicting.value = true
    predictInterval.value = setInterval(predictFrame, PREDICT_INTERVAL_MS)
  } catch (err) {
    alert('No se pudo acceder a la cámara: ' + err.message)
  }
}

/**
 * Detiene la predicción: limpia el intervalo, cierra el stream de la cámara
 * y resetea los valores del overlay a sus valores por defecto.
 */
function stopPredict() {
  if (predictInterval.value) {
    clearInterval(predictInterval.value)
    predictInterval.value = null
  }
  if (predictStream.value) {
    predictStream.value.getTracks().forEach((t) => t.stop())
    predictStream.value = null
  }
  predicting.value = false
  overlayLabel.value = '—'
  overlayConf.value = ''
}

/**
 * Envía un frame al backend (POST /predict) y actualiza la UI con el resultado.
 *
 * El backend:
 *   1. Decodifica base64 → PIL → uint8 numpy (224×224).
 *   2. Aplica preprocess_input (float32, rango [-1, 1]).
 *   3. Ejecuta model.predict() → vector de probabilidades softmax.
 *   4. Devuelve: { label, confidence, probabilities: { clase: prob } }.
 *
 * Se actualiza:
 *   - overlayLabel / overlayConf: texto sobre el vídeo.
 *   - probData: barras de probabilidad de todas las clases.
 *   - logLines: historial de predicciones con timestamp.
 *
 * Los errores de red se ignoran silenciosamente para no interrumpir el bucle.
 */
async function predictFrame() {
  if (!predictVideoEl.value) return

  try {
    const data = await apiFetch('/predict', {
      method: 'POST',
      body: JSON.stringify({ image_b64: frameToBase64(predictVideoEl.value) }),
    })

    // Actualizar overlay sobre el vídeo
    overlayLabel.value = data.label
    overlayConf.value = `${(data.confidence * 100).toFixed(0)}%`

    // Actualizar barras de probabilidad para cada clase
    Object.entries(data.probabilities).forEach(([cls, p]) => {
      if (probData[cls]) {
        probData[cls].pct = +(p * 100).toFixed(1)
      }
    })

    // Añadir línea al log (máximo MAX_LOG_LINES, las más recientes arriba)
    const time = new Date().toLocaleTimeString()
    const conf = (data.confidence * 100).toFixed(0)
    logLines.value.unshift(`[${time}]  ${data.label}  ${conf}%`)
    if (logLines.value.length > MAX_LOG_LINES) logLines.value.pop()
  } catch {
    // Errores de red se ignoran para no cortar el bucle de predicción
  }
}

// ════════════════════════════════════════════════════════════════════════════
// REINICIO COMPLETO
// ════════════════════════════════════════════════════════════════════════════

/**
 * Reinicia toda la sesión a su estado inicial:
 *   1. Detiene la predicción y todas las cámaras activas.
 *   2. Llama a DELETE /reset para limpiar imágenes y modelo del backend.
 *   3. Elimina las clases extra (deja solo INITIAL_CLASS_COUNT) y las limpia.
 *   4. Resetea el contador de IDs, el estado de entrenamiento y predicción.
 *   5. Vuelve a la fase 'capture'.
 *
 * FIX: ahora sí elimina las clases añadidas por el usuario con "+ Añadir clase"
 * y limpia probData para no dejar datos huérfanos de sesiones anteriores.
 */
async function resetAll() {
  // Paso 1: detener todas las cámaras y la predicción
  stopPredict()
  classes.forEach(stopClassCamera)

  // Paso 2: limpiar estado del backend (imágenes + modelo en RAM)
  await fetch(`${API}/reset`, { method: 'DELETE' }).catch(() => {})

  // Paso 3: restaurar clases al estado inicial
  // FIX: eliminar clases extra que el usuario haya añadido
  classes.splice(INITIAL_CLASS_COUNT)
  classes.forEach((c) => {
    c.imageCount = 0
    c.cameraOn = false
    c.capturing = false
    c.capturePct = 0
    c.captureMsg = ''
    c.name = ''
  })
  nextId = INITIAL_CLASS_COUNT + 1

  // Paso 4: resetear estado de entrenamiento
  phase.value = 'capture'
  trainDone.value = false
  trainPct.value = 0
  trainMsg.value = ''
  trainAccuracy.value = null

  // Paso 5: resetear estado de predicción
  probClasses.value = []
  logLines.value = []
  // FIX: limpiar probData para no arrastrar datos de la sesión anterior
  Object.keys(probData).forEach((key) => delete probData[key])
}

// ════════════════════════════════════════════════════════════════════════════
// CICLO DE VIDA
// ════════════════════════════════════════════════════════════════════════════

/** Al desmontar el componente, liberar todos los recursos de cámara */
onUnmounted(() => {
  stopPredict()
  classes.forEach(stopClassCamera)
})
</script>

<template>
  <div class="app">

    <Header />
    <!-- ─── Layout de flujo ──────────────────────────────────────────────── -->
    <div class="flow-root">

      <!-- COLUMNA IZQUIERDA: tarjetas de clase -->
      <div class="col-classes">
        <div
          v-for="(cls, idx) in classes"
          :key="cls.id"
          class="class-card"
          :style="{ '--accent': cls.color }"
        >
          <!-- Título de clase -->
          <div class="card-header">
            <span class="dot" :style="{ background: cls.color }"></span>
            <input
              v-model="cls.name"
              class="name-input"
              placeholder="Nombre de la clase…"
              :disabled="phase !== 'capture'"
            />
            <button
              v-if="classes.length > 2 && phase === 'capture'"
              class="btn-icon remove"
              @click="removeClass(idx)"
              title="Eliminar clase"
            >✕</button>
          </div>

          <!-- Video de la clase -->
          <div class="video-box">
            <video
              :ref="el => { if (el) videoEls[cls.id] = el }"
              autoplay muted playsinline
              class="class-video"
              :class="{ active: cls.cameraOn }"
            ></video>
            <div v-if="!cls.cameraOn" class="video-placeholder">
              <span>📷</span>
              <small>Sin cámara</small>
            </div>
          </div>

          <!-- Acciones -->
          <div class="card-actions">
            <button
              class="btn"
              :class="cls.cameraOn ? 'btn-danger' : 'btn-info'"
              :disabled="phase !== 'capture'"
              @click="toggleCamera(cls)"
            >
              {{ cls.cameraOn ? '⏹ Apagar' : '▶ Cámara' }}
            </button>
            <button
              class="btn btn-primary"
              :disabled="!cls.cameraOn || cls.capturing || phase !== 'capture'"
              @click="captureImages(cls)"
            >
              📷 Capturar 15
            </button>
          </div>

          <!-- Progreso de captura -->
          <div v-if="cls.capturing" class="capture-progress">
            <span class="cap-msg">{{ cls.captureMsg }}</span>
            <div class="pbar"><div class="pfill" :style="{ width: cls.capturePct + '%', background: cls.color }"></div></div>
          </div>

          <!-- Contador -->
          <div class="img-count" :style="{ color: cls.color }">
            {{ cls.imageCount }} imágenes
            <span v-if="cls.imageCount >= 5" style="color:#86efac"> ✓</span>
            <span v-else style="color:#888"> (mín. 5)</span>
          </div>
        </div>

        <!-- Botón añadir clase -->
        <button
          v-if="phase === 'capture'"
          class="btn btn-ghost add-class-btn"
          @click="addClass"
        >+ Añadir clase</button>
      </div>

      <!-- Conector izquierda → centro -->
      <div class="connector">
        <div class="connector-line"></div>
        <div class="connector-arrow">▶</div>
      </div>

      <!-- COLUMNA CENTRAL: entrenamiento -->
      <div class="center-card">
        <div class="center-card-title">🧠 Entrenamiento</div>

        <div v-if="phase === 'capture'" class="train-summary">
          <p class="hint">Captura imágenes de tus clases y luego entrena el modelo.</p>
          <div class="class-summary">
            <div v-for="cls in classes" :key="cls.id" class="summary-row">
              <span class="dot" :style="{ background: cls.color }"></span>
              <span class="summary-name">{{ cls.name || '(sin nombre)' }}</span>
              <span class="summary-count" :style="{ color: cls.color }">{{ cls.imageCount }} imgs</span>
            </div>
          </div>
          <button
            class="btn btn-success train-btn"
            :disabled="!canTrain"
            @click="trainModel"
          >🚀 Entrenar modelo</button>
          <p v-if="!canTrain" class="hint-warn">Necesitas ≥ 2 clases con ≥ 5 imágenes cada una.</p>
        </div>

        <div v-else class="train-progress-block">
          <div class="big-pct" :class="{ done: trainDone }">{{ trainPct }}%</div>
          <div class="pbar"><div class="pfill accent" :style="{ width: trainPct + '%' }"></div></div>
          <p class="train-msg">{{ trainMsg }}</p>

          <div v-if="trainDone" class="accuracy-badge">
            ✅ Precisión: <strong>{{ (trainAccuracy * 100).toFixed(1) }}%</strong>
          </div>

          <div v-if="trainDone" class="prob-list">
            <div v-for="cls in probClasses" :key="cls" class="prob-row">
              <span class="prob-label">{{ cls }}</span>
              <div class="pbar"><div class="pfill accent" :style="{ width: probData[cls]?.pct + '%' }"></div></div>
              <span class="prob-val">{{ probData[cls]?.pct ?? 0 }}%</span>
            </div>
          </div>

          <!-- Botón de reinicio: permite volver a la fase de captura desde cero -->
          <button
            v-if="trainDone"
            class="btn btn-ghost train-btn"
            style="margin-top: 0.8rem"
            @click="resetAll"
          >🔄 Reiniciar</button>
        </div>
      </div>

      <!-- Conector centro → derecha -->
      <div class="connector" :class="{ dimmed: !trainDone }">
        <div class="connector-line"></div>
        <div class="connector-arrow">▶</div>
      </div>

      <!-- COLUMNA DERECHA: resultado en tiempo real -->
      <div class="result-card" :class="{ dimmed: !trainDone }">
        <div class="center-card-title">👁️ Resultado en tiempo real</div>

        <div v-if="!trainDone" class="result-waiting">
          <span>Entrena el modelo primero</span>
        </div>

        <template v-else>
          <!-- Video de predicción -->
          <div class="predict-video-box">
            <video
              ref="predictVideoEl"
              autoplay muted playsinline
              class="predict-video"
            ></video>
            <div v-if="predicting" class="predict-overlay">
              <span class="pred-label">{{ overlayLabel }}</span>
              <span class="pred-conf">{{ overlayConf }}</span>
            </div>
            <div v-if="!predicting" class="video-placeholder">
              <span>👁️</span><small>Sin cámara</small>
            </div>
          </div>

          <!-- Controles -->
          <div class="card-actions">
            <button class="btn btn-info"   :disabled="predicting"  @click="startPredictCamera">▶ Iniciar</button>
            <button class="btn btn-danger" :disabled="!predicting" @click="stopPredict">⏹ Detener</button>
          </div>

          <!-- Barras de probabilidad -->
          <div v-if="probClasses.length" class="prob-list" style="margin-top:0.8rem">
            <div v-for="cls in probClasses" :key="cls" class="prob-row">
              <span class="prob-label">{{ cls }}</span>
              <div class="pbar"><div class="pfill accent" :style="{ width: probData[cls]?.pct + '%' }"></div></div>
              <span class="prob-val">{{ probData[cls]?.pct ?? 0 }}%</span>
            </div>
          </div>

          <!-- Log -->
          <div class="log-box" v-if="logLines.length">
            <div v-for="(l, i) in logLines" :key="i" class="log-line">{{ l }}</div>
          </div>
        </template>
      </div>

    </div><!-- /flow-root -->
  </div>
</template>

<style scoped>
/* ─── Reset / base ────────────────────────────────────────────────────────── */
* { box-sizing: border-box; }

.app {
  font-family: 'Montserrat', system-ui, sans-serif;
  background: #ffffff;
  color: #1a1a1a;
  min-height: 100vh;
}

/* ─── Barra de acciones ───────────────────────────────────────────────────── */
.actions-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.7rem 2rem;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
}
.page-title { font-size: 1rem; font-weight: 700; color: #1B512D; font-family: 'Montserrat', sans-serif; }

/* ─── Layout de flujo horizontal ─────────────────────────────────────────── */
.flow-root {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0;
  padding: 2rem 1.5rem;
  overflow-x: auto;
  min-height: calc(100vh - 56px);
}

/* ─── Columna izquierda (clases) ─────────────────────────────────────────── */
.col-classes {
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
  min-width: 320px;
  max-width: 360px;
  flex-shrink: 0;
}

/* ─── Tarjeta de clase ───────────────────────────────────────────────────── */
.class-card {
  background: #e8f5e9;
  border: 2px solid var(--accent, #7c3aed);
  border-radius: 14px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  box-shadow: 0 2px 12px rgba(0,0,0,0.3);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.dot {
  width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
}
.name-input {
  flex: 1;
  background: #fff;
  border: 1px solid #ccc;
  border-radius: 6px;
  padding: 0.4rem 0.6rem;
  font-size: 0.9rem;
  color: #1a1a1a;
  outline: none;
}
.name-input:focus { border-color: var(--accent, #7c3aed); }
.btn-icon.remove {
  background: none; border: none; cursor: pointer;
  color: #dc2626; font-size: 1rem; padding: 0.1rem 0.3rem;
}

/* ─── Video dentro de la tarjeta ─────────────────────────────────────────── */
.video-box {
  position: relative;
  background: #1a1a2e;
  border-radius: 10px;
  overflow: hidden;
  aspect-ratio: 4/3;
  width: 100%;
}
.class-video {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0;
  transition: opacity 0.3s;
}
.class-video.active { opacity: 1; }

.video-placeholder {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: #555; gap: 0.4rem;
  font-size: 2rem;
}
.video-placeholder small { font-size: 0.75rem; color: #666; }

/* ─── Acciones de la tarjeta ─────────────────────────────────────────────── */
.card-actions {
  display: flex; gap: 0.5rem; flex-wrap: wrap;
}

/* ─── Barra de captura ───────────────────────────────────────────────────── */
.capture-progress { display: flex; flex-direction: column; gap: 0.3rem; }
.cap-msg { font-size: 0.8rem; color: #1a1a2e; font-weight: 600; }

/* ─── Contador de imágenes ───────────────────────────────────────────────── */
.img-count { font-size: 0.82rem; font-weight: 600; }

/* ─── Botón añadir clase ─────────────────────────────────────────────────── */
.add-class-btn {
  border: 2px dashed #1B512D;
  background: transparent;
  color: #1B512D;
  font-size: 0.9rem;
  padding: 0.7rem;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.2s;
}
.add-class-btn:hover { background: rgba(27,81,45,0.08); }

/* ─── Conector ───────────────────────────────────────────────────────────── */
.connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0 6px;
  min-height: 200px;
  gap: 2px;
  align-self: center;
  transition: opacity 0.3s;
}
.connector.dimmed { opacity: 0.3; }
.connector-line  { width: 40px; height: 2px; background: #b1cf5f; }
.connector-arrow { color: #1B512D; font-size: 0.9rem; margin-left: -4px; }

/* ─── Tarjeta central (entrenamiento) ────────────────────────────────────── */
.center-card {
  background: #e8f5e9;
  border: 2px solid #55a472;
  border-radius: 14px;
  padding: 1.2rem;
  min-width: 260px;
  max-width: 300px;
  flex-shrink: 0;
  align-self: center;
  box-shadow: 0 2px 12px rgba(0,0,0,0.3);
}
.center-card-title {
  font-size: 0.95rem; font-weight: 700;
  color: #1a3a26; margin-bottom: 0.9rem;
}

.hint      { font-size: 0.82rem; color: #444; margin-bottom: 0.8rem; }
.hint-warn { font-size: 0.78rem; color: #b45309; margin-top: 0.5rem; text-align: center; }

.class-summary   { display: flex; flex-direction: column; gap: 0.4rem; margin-bottom: 1rem; }
.summary-row     { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: #1a1a1a; }
.summary-name    { flex: 1; }
.summary-count   { font-weight: 700; }

.train-btn  { width: 100%; justify-content: center; margin-top: 0.5rem; }

.big-pct {
  font-size: 3rem; font-weight: 800; text-align: center;
  color: #2d6a4f; margin-bottom: 0.4rem; transition: color 0.3s;
}
.big-pct.done { color: #059669; }

.train-msg { font-size: 0.82rem; color: #444; text-align: center; margin-top: 0.5rem; }

.accuracy-badge {
  margin-top: 0.8rem; text-align: center;
  font-size: 0.9rem; color: #065f46;
  background: #d1fae5; border-radius: 8px; padding: 0.4rem;
}

/* ─── Tarjeta de resultado ───────────────────────────────────────────────── */
.result-card {
  background: #e8f5e9;
  border: 2px solid #55a472;
  border-radius: 14px;
  padding: 1.2rem;
  min-width: 280px;
  max-width: 340px;
  flex-shrink: 0;
  align-self: center;
  box-shadow: 0 2px 12px rgba(0,0,0,0.3);
  transition: opacity 0.3s;
}
.result-card.dimmed { opacity: 0.35; pointer-events: none; }

.result-waiting {
  text-align: center; color: #888; font-size: 0.85rem;
  padding: 2rem 0;
}

/* ─── Video de predicción ────────────────────────────────────────────────── */
.predict-video-box {
  position: relative;
  background: #1a1a2e;
  border-radius: 10px;
  overflow: hidden;
  aspect-ratio: 4/3;
  width: 100%;
  margin-bottom: 0.7rem;
}
.predict-video {
  width: 100%; height: 100%;
  object-fit: cover; display: block;
}
.predict-overlay {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: linear-gradient(transparent, rgba(0,0,0,0.75));
  padding: 0.8rem 0.6rem 0.5rem;
  display: flex; flex-direction: column; align-items: center;
}
.pred-label { font-size: 1.4rem; font-weight: 800; color: #fff; line-height: 1.1; }
.pred-conf  { font-size: 1rem;   font-weight: 600; color: #86efac; }

/* ─── Barras de probabilidad ─────────────────────────────────────────────── */
.prob-list { display: flex; flex-direction: column; gap: 0.35rem; }
.prob-row  { display: flex; align-items: center; gap: 0.5rem; font-size: 0.82rem; }
.prob-label { width: 90px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #1a1a1a; }
.prob-val   { width: 38px; text-align: right; font-weight: 700; color: #065f46; }

/* ─── Log ────────────────────────────────────────────────────────────────── */
.log-box {
  margin-top: 0.7rem;
  background: #0f0f20; border-radius: 8px; padding: 0.6rem;
  max-height: 100px; overflow-y: auto;
  font-size: 0.75rem; font-family: monospace; color: #86efac;
  border: 1px solid #2d2d4e;
}
.log-line { line-height: 1.6; }

/* ─── Barra de progreso genérica ─────────────────────────────────────────── */
.pbar  { flex: 1; background: #b7dfbb; border-radius: 6px; height: 8px; overflow: hidden; min-width: 60px; }
.pfill { height: 100%; border-radius: 6px; transition: width 0.35s; background: #059669; }
.pfill.accent { background: #2d6a4f; }

/* ─── Botones ─────────────────────────────────────────────────────────────── */
button { padding: 0.5rem 1rem; border-radius: 8px; border: none; cursor: pointer;
  font-size: 0.88rem; font-weight: 600; transition: opacity 0.2s; }
button:hover    { opacity: 0.85; }
button:disabled { opacity: 0.35; cursor: not-allowed; }
.btn-primary { background: #7c3aed; color: #fff; }
.btn-success { background: #059669; color: #fff; }
.btn-danger  { background: #dc2626; color: #fff; }
.btn-info    { background: #0369a1; color: #fff; }
.btn-ghost   { background: rgba(0,0,0,0.04); color: #555; border: 1px solid #ccc; }
</style>

