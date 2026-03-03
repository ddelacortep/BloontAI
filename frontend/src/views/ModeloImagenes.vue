<script setup>
import { ref, reactive, computed, nextTick, onUnmounted } from 'vue'
import Header from './components/Header.vue'

// ─── Constantes ───────────────────────────────────────────────────────────────
const API = '/api'

// Colores asignados rotativamente a cada clase de entrenamiento
const PALETTE = ['#7c3aed', '#059669', '#0369a1', '#d97706', '#dc2626', '#0891b2', '#65a30d']

// Mínimo de imágenes que debe tener cada clase para poder entrenar
const MIN_IMAGES_PER_CLASS = 15

// ─── Estado de las clases de entrenamiento ────────────────────────────────────
// Cada clase tiene su propia cámara, contador de imágenes y objetivo de captura configurable
const classes = reactive([
  {
    id: 1, name: '', imageCount: 0, color: PALETTE[0],
    cameraOn: false, capturing: false,
    captureProgress: 0, captureMessage: '',
    captureTarget: MIN_IMAGES_PER_CLASS,
  },
  {
    id: 2, name: '', imageCount: 0, color: PALETTE[1],
    cameraOn: false, capturing: false,
    captureProgress: 0, captureMessage: '',
    captureTarget: MIN_IMAGES_PER_CLASS,
  },
])
let nextClassId = 3

// Referencias a los elementos <video> y los MediaStreams de cada clase (indexados por cls.id)
const cameraElements = reactive({})   // { [id]: HTMLVideoElement }
const cameraStreams  = reactive({})   // { [id]: MediaStream }

// ─── Fase de la aplicación ────────────────────────────────────────────────────
// 'capture'  → el usuario captura imágenes de entrenamiento
// 'training' → el modelo está entrenando o ya ha terminado
const appPhase = ref('capture')

// ─── Estado del entrenamiento ─────────────────────────────────────────────────
const isTraining         = ref(false)   // True mientras la petición /train está en curso
const trainingMessage    = ref('')      // Texto de estado que se muestra al usuario
const trainingProgress   = ref(0)       // Porcentaje de progreso visual (0–100)
const isTrainingComplete = ref(false)   // True cuando el entrenamiento ha concluido con éxito
const trainingAccuracy   = ref(null)    // Precisión en validación devuelta por el backend
const isExporting        = ref(false)   // True mientras el ZIP se está generando/descargando

// ─── Configuración de hiperparámetros (modal de ajustes) ──────────────────────
const showTrainingSettings = ref(false)   // Controla si el modal de configuración es visible
const trainingConfig = reactive({
  epochs:       20,       // Número máximo de épocas
  batchSize:    16,       // Imágenes procesadas por paso de gradiente
  learningRate: 0.0001,   // Tasa de aprendizaje inicial del optimizador Adam
})

// ─── Estado de la predicción en tiempo real ───────────────────────────────────
const predictCameraEl     = ref(null)   // Elemento <video> de la sección de predicción
const predictCameraStream = ref(null)   // MediaStream activo de la cámara de predicción
const predictionTimer     = ref(null)   // Intervalo que dispara la inferencia periódicamente
const isPredicting        = ref(false)  // True cuando la predicción continua está activa

// Resultado de la última predicción (mostrado en el overlay del video)
const predictedLabel      = ref('—')   // Nombre de la clase predicha
const predictedConfidence = ref('')    // Confianza como texto (p.ej. "87%")

// Barras de probabilidad por clase
const trainedClassNames  = ref([])        // Nombres de las clases del modelo entrenado
const classProbabilities = reactive({})   // { nombre_clase: { pct: 0..100 } }

// Historial de las últimas predicciones (máximo 25 entradas)
const predictionLog = ref([])

// ─── Computed ─────────────────────────────────────────────────────────────────
// Habilita el botón de entrenar solo cuando hay ≥ 2 clases con nombre y ≥ MIN_IMAGES_PER_CLASS imágenes
const canTrain = computed(() => {
  const namedClasses = classes.filter(c => c.name.trim())
  return namedClasses.length >= 2 && namedClasses.every(c => c.imageCount >= MIN_IMAGES_PER_CLASS)
})

// ─── Gestión de clases ────────────────────────────────────────────────────────

/** Añade una nueva clase al array reactivo con el siguiente color de la paleta. */
function addClass() {
  classes.push({
    id: nextClassId++,
    name: '',
    imageCount: 0,
    color: PALETTE[classes.length % PALETTE.length],
    cameraOn: false,
    capturing: false,
    captureProgress: 0,
    captureMessage: '',
    captureTarget: MIN_IMAGES_PER_CLASS,
  })
}

/** Elimina la clase en la posición idx. No permite reducir a menos de 2 clases. */
function removeClass(idx) {
  if (classes.length <= 2) return
  stopClassCamera(classes[idx])
  classes.splice(idx, 1)
}

// ─── Control de cámara por clase ─────────────────────────────────────────────

/** Activa la cámara de una clase si estaba apagada, o la detiene si ya estaba encendida. */
async function toggleCamera(cls) {
  if (cls.cameraOn) {
    stopClassCamera(cls)
    return
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } })
    cameraStreams[cls.id] = stream
    cls.cameraOn = true
    await nextTick()   // Esperar a que Vue renderice el elemento <video>
    const videoEl = cameraElements[cls.id]
    if (videoEl) {
      videoEl.srcObject = stream
      await videoEl.play().catch(() => {})
    }
  } catch (err) {
    alert('No se pudo acceder a la cámara: ' + err.message)
  }
}

/** Detiene la cámara de una clase y libera el MediaStream del sistema operativo. */
function stopClassCamera(cls) {
  if (cameraStreams[cls.id]) {
    cameraStreams[cls.id].getTracks().forEach(track => track.stop())
    delete cameraStreams[cls.id]
  }
  if (cameraElements[cls.id]) cameraElements[cls.id].srcObject = null
  cls.cameraOn = false
}

// ─── Captura de imágenes ──────────────────────────────────────────────────────

/**
 * Extrae un frame del elemento <video>, lo recorta a cuadrado centrado y
 * lo devuelve como JPEG en Base64 (sin el prefijo data:image/...).
 * El recorte cuadrado centrado mantiene la proporción correcta para MobileNetV2 (224×224).
 */
function frameToBase64(videoEl) {
  const canvas = document.createElement('canvas')
  canvas.width  = 224
  canvas.height = 224
  const ctx      = canvas.getContext('2d')
  const cropSize = Math.min(videoEl.videoWidth, videoEl.videoHeight)
  const offsetX  = (videoEl.videoWidth  - cropSize) / 2
  const offsetY  = (videoEl.videoHeight - cropSize) / 2
  ctx.drawImage(videoEl, offsetX, offsetY, cropSize, cropSize, 0, 0, 224, 224)
  return canvas.toDataURL('image/jpeg', 0.85).split(',')[1]
}

/**
 * Envía una imagen en Base64 al backend /upload para almacenarla en RAM
 * asociada a la etiqueta de clase indicada.
 */
async function uploadImageToAPI(label, imageBase64) {
  const response = await fetch(`${API}/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label, image_b64: imageBase64 }),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * Captura cls.captureTarget frames del video de la clase (mínimo MIN_IMAGES_PER_CLASS)
 * y los sube uno a uno al backend. Actualiza la barra de progreso durante el proceso.
 */
async function captureImages(cls) {
  if (!cls.cameraOn || !cameraElements[cls.id]) { alert('Activa la cámara primero.'); return }
  if (!cls.name.trim()) { alert('Escribe el nombre de la clase primero.'); return }

  // Garantizar que nunca se capturen menos del mínimo requerido
  const totalImages   = Math.max(MIN_IMAGES_PER_CLASS, cls.captureTarget)
  cls.capturing       = true
  cls.captureProgress = 0
  cls.captureMessage  = ''

  try {
    for (let i = 0; i < totalImages; i++) {
      cls.captureMessage  = `${i + 1} / ${totalImages}`
      cls.captureProgress = Math.round(((i + 1) / totalImages) * 100)

      const imageBase64 = frameToBase64(cameraElements[cls.id])
      await uploadImageToAPI(cls.name.trim(), imageBase64)
      cls.imageCount++
      await sleep(150)   // Pequeña pausa para que los frames capturados varíen ligeramente
    }
    cls.captureMessage = '✅ Listo'
    setTimeout(() => { cls.capturing = false; cls.captureMessage = '' }, 2000)
  } catch (err) {
    cls.captureMessage = `❌ Error: ${err.message}`
    setTimeout(() => { cls.capturing = false; cls.captureMessage = '' }, 3000)
  }
}

// ─── Entrenamiento del modelo ─────────────────────────────────────────────────

/**
 * Envía una petición POST /train al backend con los hiperparámetros configurados.
 * Actualiza la barra de progreso y, al completar, guarda los nombres de clase
 * para inicializar las barras de probabilidad en la vista de predicción.
 */
async function trainModel() {
  appPhase.value         = 'training'
  isTraining.value       = true
  isTrainingComplete.value = false
  trainingProgress.value = 15
  trainingMessage.value  = 'Cargando MobileNetV2…'

  try {
    trainingProgress.value = 35
    trainingMessage.value  = 'Entrenando con Transfer Learning…'

    const response = await fetch(`${API}/train`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        epochs:        trainingConfig.epochs,
        batch_size:    trainingConfig.batchSize,
        learning_rate: trainingConfig.learningRate,
        fine_tune:     true,
      }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Error en entrenamiento')

    trainingProgress.value   = 100
    trainingMessage.value    = `Precisión: ${(data.val_accuracy * 100).toFixed(1)}%  ·  ${data.epochs_run} épocas`
    trainingAccuracy.value   = data.val_accuracy
    isTrainingComplete.value = true
    trainedClassNames.value  = data.classes

    // Inicializar todas las barras de probabilidad a 0 hasta que el usuario prediga
    data.classes.forEach(cls => { classProbabilities[cls] = { pct: 0 } })
  } catch (err) {
    trainingMessage.value = '❌ ' + err.message
    appPhase.value        = 'capture'
  } finally {
    isTraining.value = false
  }
}

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

// ─── Predicción en tiempo real ────────────────────────────────────────────────

/** Inicia la cámara de predicción y arranca el intervalo de inferencia (cada 600 ms). */
async function startPredictCamera() {
  try {
    if (predictCameraStream.value) predictCameraStream.value.getTracks().forEach(t => t.stop())
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } })
    predictCameraStream.value = stream
    await nextTick()
    predictCameraEl.value.srcObject = stream
    await predictCameraEl.value.play().catch(() => {})
    isPredicting.value    = true
    predictionTimer.value = setInterval(runPrediction, 600)
  } catch (err) {
    alert('No se pudo acceder a la cámara: ' + err.message)
  }
}

/** Detiene la cámara de predicción y limpia el intervalo de inferencia. */
function stopPrediction() {
  clearInterval(predictionTimer.value)
  predictionTimer.value = null
  if (predictCameraStream.value) {
    predictCameraStream.value.getTracks().forEach(t => t.stop())
    predictCameraStream.value = null
  }
  isPredicting.value        = false
  predictedLabel.value      = '—'
  predictedConfidence.value = ''
}

/**
 * Captura un frame de la cámara de predicción, lo envía al backend /predict
 * y actualiza el overlay de resultado y las barras de probabilidad en tiempo real.
 */
async function runPrediction() {
  if (!predictCameraEl.value) return
  try {
    const response = await fetch(`${API}/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_b64: frameToBase64(predictCameraEl.value) }),
    })
    const data = await response.json()
    if (!response.ok) return

    predictedLabel.value      = data.label
    predictedConfidence.value = `${(data.confidence * 100).toFixed(0)}%`

    // Actualizar las barras de probabilidad para cada clase
    Object.entries(data.probabilities).forEach(([cls, probability]) => {
      if (classProbabilities[cls]) classProbabilities[cls].pct = +(probability * 100).toFixed(1)
    })

    // Registrar en el log (máximo 25 entradas, las más recientes primero)
    predictionLog.value.unshift(
      `[${new Date().toLocaleTimeString()}]  ${data.label}  ${(data.confidence * 100).toFixed(0)}%`
    )
    if (predictionLog.value.length > 25) predictionLog.value.pop()
  } catch {
    // Ignorar errores de red transitorios durante la predicción continua
  }
}

// ─── Reinicio total ───────────────────────────────────────────────────────────

/**
 * Detiene todas las cámaras activas, llama a /reset en el backend para limpiar la RAM
 * y restablece todo el estado local al estado inicial de la aplicación.
 */
async function resetAll() {
  stopPrediction()
  classes.forEach(stopClassCamera)
  await fetch(`${API}/reset`, { method: 'DELETE' }).catch(() => {})

  classes.forEach(cls => {
    cls.imageCount      = 0
    cls.cameraOn        = false
    cls.capturing       = false
    cls.name            = ''
    cls.captureProgress = 0
    cls.captureMessage  = ''
    cls.captureTarget   = MIN_IMAGES_PER_CLASS
  })

  appPhase.value           = 'capture'
  isTrainingComplete.value = false
  trainingProgress.value   = 0
  trainingMessage.value    = ''
  trainedClassNames.value  = []
  predictionLog.value      = []
  showTrainingSettings.value = false
}

// ─── Utilidades ───────────────────────────────────────────────────────────────
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)) }

// Liberar todos los recursos de cámara al desmontar el componente (evitar memory leaks)
onUnmounted(() => {
  stopPrediction()
  classes.forEach(stopClassCamera)
})
</script>

<template>
  <div class="app">

    <Header />

    <!-- ─── Modal de configuración de hiperparámetros ─────────────────────── -->
    <!-- Se abre al pulsar ⚙️ junto al botón de entrenar -->
    <div
      v-if="showTrainingSettings"
      class="modal-overlay"
      @click.self="showTrainingSettings = false"
    >
      <div class="modal-card">
        <div class="modal-header">
          <span class="modal-title">⚙️ Configuración de entrenamiento</span>
          <button class="btn-icon remove" @click="showTrainingSettings = false" title="Cerrar">✕</button>
        </div>

        <div class="modal-body">
          <!-- Épocas: número máximo de iteraciones completas sobre el dataset -->
          <div class="config-row">
            <label class="config-label">Épocas</label>
            <input
              type="number"
              v-model.number="trainingConfig.epochs"
              min="1" max="200"
              class="config-input"
            />
            <span class="config-hint">Iteraciones completas sobre los datos (el early stopping puede detener antes)</span>
          </div>

          <!-- Tamaño de lote: imágenes procesadas por cada paso de gradiente -->
          <div class="config-row">
            <label class="config-label">Tamaño de lote</label>
            <select v-model.number="trainingConfig.batchSize" class="config-select">
              <option :value="8">8 — muy pequeño</option>
              <option :value="16">16 — por defecto</option>
              <option :value="32">32 — mediano</option>
              <option :value="64">64 — grande</option>
            </select>
            <span class="config-hint">Imágenes procesadas por paso de gradiente</span>
          </div>

          <!-- Tasa de aprendizaje: velocidad de ajuste del optimizador Adam -->
          <div class="config-row">
            <label class="config-label">Tasa de aprendizaje</label>
            <select v-model.number="trainingConfig.learningRate" class="config-select">
              <option :value="0.01">0.01 — rápida</option>
              <option :value="0.001">0.001 — media</option>
              <option :value="0.0001">0.0001 — lenta (recomendada)</option>
              <option :value="0.00001">0.00001 — muy lenta</option>
            </select>
            <span class="config-hint">Velocidad de ajuste de los pesos de la red</span>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-success" @click="showTrainingSettings = false">✓ Guardar configuración</button>
        </div>
      </div>
    </div>

    <!-- ─── Layout de flujo horizontal ──────────────────────────────────────── -->
    <div class="flow-root">

      <!-- COLUMNA IZQUIERDA: tarjetas de clase con cámara y captura -->
      <div class="col-classes">
        <div
          v-for="(cls, idx) in classes"
          :key="cls.id"
          class="class-card"
          :style="{ '--accent': cls.color }"
        >
          <!-- Cabecera: punto de color + nombre de la clase + botón eliminar -->
          <div class="card-header">
            <span class="dot" :style="{ background: cls.color }"></span>
            <input
              v-model="cls.name"
              class="name-input"
              placeholder="Nombre de la clase…"
              :disabled="appPhase !== 'capture'"
            />
            <button
              v-if="classes.length > 2 && appPhase === 'capture'"
              class="btn-icon remove"
              @click="removeClass(idx)"
              title="Eliminar clase"
            >✕</button>
          </div>

          <!-- Previsualización de la cámara de la clase -->
          <div class="video-box">
            <video
              :ref="el => { if (el) cameraElements[cls.id] = el }"
              autoplay muted playsinline
              class="class-video"
              :class="{ active: cls.cameraOn }"
            ></video>
            <div v-if="!cls.cameraOn" class="video-placeholder">
              <span>📷</span>
              <small>Sin cámara</small>
            </div>
          </div>

          <!-- Botones de acción: encender cámara, capturar, número de imágenes -->
          <div class="card-actions">
            <button
              class="btn"
              :class="cls.cameraOn ? 'btn-danger' : 'btn-info'"
              :disabled="appPhase !== 'capture'"
              @click="toggleCamera(cls)"
            >
              {{ cls.cameraOn ? '⏹ Apagar' : '▶ Cámara' }}
            </button>
            <button
              class="btn btn-primary"
              :disabled="!cls.cameraOn || cls.capturing || appPhase !== 'capture'"
              @click="captureImages(cls)"
            >
              📷 Capturar
            </button>
            <!-- Input para elegir cuántas imágenes capturar (mínimo 15) -->
            <input
              type="number"
              v-model.number="cls.captureTarget"
              min="15"
              max="500"
              class="capture-count-input"
              :disabled="cls.capturing || appPhase !== 'capture'"
              title="Número de imágenes a capturar (mín. 15)"
            />
          </div>

          <!-- Barra de progreso durante una captura activa -->
          <div v-if="cls.capturing" class="capture-progress">
            <span class="cap-msg">{{ cls.captureMessage }}</span>
            <div class="pbar">
              <div class="pfill" :style="{ width: cls.captureProgress + '%', background: cls.color }"></div>
            </div>
          </div>

          <!-- Contador de imágenes con indicador de si supera el mínimo -->
          <div class="img-count" :style="{ color: cls.color }">
            {{ cls.imageCount }} imágenes
            <span v-if="cls.imageCount >= 15" style="color:#86efac"> ✓</span>
            <span v-else style="color:#888"> (mín. 15)</span>
          </div>
        </div>

        <!-- Botón para añadir una nueva clase de entrenamiento -->
        <button
          v-if="appPhase === 'capture'"
          class="btn btn-ghost add-class-btn"
          @click="addClass"
        >+ Añadir clase</button>
      </div>

      <!-- Conector visual izquierda → centro -->
      <div class="connector">
        <div class="connector-line"></div>
        <div class="connector-arrow">▶</div>
      </div>

      <!-- COLUMNA CENTRAL: panel de entrenamiento -->
      <div class="center-card">
        <div class="center-card-title">🧠 Entrenamiento</div>

        <!-- Vista de captura: resumen de clases + botones de entrenar y configurar -->
        <div v-if="appPhase === 'capture'" class="train-summary">
          <p class="hint">Captura imágenes de tus clases y luego entrena el modelo.</p>

          <!-- Resumen compacto: clase → número de imágenes capturadas -->
          <div class="class-summary">
            <div v-for="cls in classes" :key="cls.id" class="summary-row">
              <span class="dot" :style="{ background: cls.color }"></span>
              <span class="summary-name">{{ cls.name || '(sin nombre)' }}</span>
              <span class="summary-count" :style="{ color: cls.color }">{{ cls.imageCount }} imgs</span>
            </div>
          </div>

          <!-- Botón de entrenar + engranaje de configuración en la misma fila -->
          <div class="train-actions">
            <button
              class="btn btn-success train-btn"
              :disabled="!canTrain"
              @click="trainModel"
            >🚀 Entrenar modelo</button>
            <button
              class="btn btn-ghost settings-btn"
              @click="showTrainingSettings = true"
              title="Configurar épocas, tamaño de lote y tasa de aprendizaje"
            >⚙️</button>
          </div>
          <p v-if="!canTrain" class="hint-warn">
            Necesitas ≥ 2 clases con ≥ 15 imágenes cada una.
          </p>

          <!-- Botón de reinicio total (limpia cámaras, imágenes y modelo) -->
          <button class="btn btn-outline-danger reset-btn" @click="resetAll">
            🗑️ Reiniciar todo
          </button>
        </div>

        <!-- Vista de progreso / resultado del entrenamiento -->
        <div v-else class="train-progress-block">
          <div class="big-pct" :class="{ done: isTrainingComplete }">{{ trainingProgress }}%</div>
          <div class="pbar"><div class="pfill accent" :style="{ width: trainingProgress + '%' }"></div></div>
          <p class="train-msg">{{ trainingMessage }}</p>

          <!-- Insignia con la precisión de validación final -->
          <div v-if="isTrainingComplete" class="accuracy-badge">
            ✅ Precisión: <strong>{{ (trainingAccuracy * 100).toFixed(1) }}%</strong>
          </div>

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

          <!-- Barras de probabilidad por clase (se actualizan al predecir) -->
          <div v-if="isTrainingComplete" class="prob-list">
            <div v-for="cls in trainedClassNames" :key="cls" class="prob-row">
              <span class="prob-label">{{ cls }}</span>
              <div class="pbar"><div class="pfill accent" :style="{ width: classProbabilities[cls]?.pct + '%' }"></div></div>
              <span class="prob-val">{{ classProbabilities[cls]?.pct ?? 0 }}%</span>
            </div>
          </div>

          <!-- Botón de reinicio también disponible tras el entrenamiento -->
          <button class="btn btn-outline-danger reset-btn" style="margin-top:1rem" @click="resetAll">
            🗑️ Reiniciar todo
          </button>
        </div>
      </div>

      <!-- Conector visual centro → derecha (atenuado hasta que haya modelo listo) -->
      <div class="connector" :class="{ dimmed: !isTrainingComplete }">
        <div class="connector-line"></div>
        <div class="connector-arrow">▶</div>
      </div>

      <!-- COLUMNA DERECHA: resultado de predicción en tiempo real -->
      <div class="result-card" :class="{ dimmed: !isTrainingComplete }">
        <div class="center-card-title">👁️ Resultado en tiempo real</div>

        <!-- Mensaje de espera si el modelo todavía no está entrenado -->
        <div v-if="!isTrainingComplete" class="result-waiting">
          <span>Entrena el modelo primero</span>
        </div>

        <template v-else>
          <!-- Video con overlay que muestra la clase predicha y la confianza -->
          <div class="predict-video-box">
            <video
              ref="predictCameraEl"
              autoplay muted playsinline
              class="predict-video"
            ></video>
            <div v-if="isPredicting" class="predict-overlay">
              <span class="pred-label">{{ predictedLabel }}</span>
              <span class="pred-conf">{{ predictedConfidence }}</span>
            </div>
            <div v-if="!isPredicting" class="video-placeholder">
              <span>👁️</span><small>Sin cámara</small>
            </div>
          </div>

          <!-- Controles de predicción -->
          <div class="card-actions">
            <button class="btn btn-info"   :disabled="isPredicting"  @click="startPredictCamera">▶ Iniciar</button>
            <button class="btn btn-danger" :disabled="!isPredicting" @click="stopPrediction">⏹ Detener</button>
          </div>

          <!-- Barras de probabilidad actualizadas en tiempo real -->
          <div v-if="trainedClassNames.length" class="prob-list" style="margin-top:0.8rem">
            <div v-for="cls in trainedClassNames" :key="cls" class="prob-row">
              <span class="prob-label">{{ cls }}</span>
              <div class="pbar"><div class="pfill accent" :style="{ width: classProbabilities[cls]?.pct + '%' }"></div></div>
              <span class="prob-val">{{ classProbabilities[cls]?.pct ?? 0 }}%</span>
            </div>
          </div>

          <!-- Log de predicciones recientes con timestamp -->
          <div class="log-box" v-if="predictionLog.length">
            <div v-for="(entry, i) in predictionLog" :key="i" class="log-line">{{ entry }}</div>
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

/* ─── Modal overlay ───────────────────────────────────────────────────────── */
/* Fondo semitransparente que cubre toda la pantalla al abrir el modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-card {
  background: #fff;
  border: 2px solid #55a472;
  border-radius: 16px;
  padding: 1.5rem;
  min-width: 340px;
  max-width: 440px;
  width: 90%;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.2rem;
}

.modal-title {
  font-size: 1rem;
  font-weight: 700;
  color: #1a3a26;
}

.modal-body {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}

.modal-footer {
  margin-top: 1.4rem;
  display: flex;
  justify-content: flex-end;
}

/* ─── Filas de configuración dentro del modal ────────────────────────────── */
.config-row {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.config-label {
  font-size: 0.85rem;
  font-weight: 700;
  color: #1a3a26;
}

.config-input,
.config-select {
  padding: 0.45rem 0.6rem;
  border: 1.5px solid #b7dfbb;
  border-radius: 8px;
  font-size: 0.88rem;
  color: #1a1a1a;
  background: #f0faf2;
  outline: none;
  width: 100%;
  font-family: 'Montserrat', sans-serif;
}

.config-input:focus,
.config-select:focus { border-color: #55a472; }

.config-hint {
  font-size: 0.75rem;
  color: #666;
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
  max-width: 380px;
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
  display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;
}

/* Input para elegir cuántas imágenes capturar (mínimo 15) */
.capture-count-input {
  width: 64px;
  padding: 0.44rem 0.4rem;
  border: 1.5px solid #b7dfbb;
  border-radius: 6px;
  font-size: 0.85rem;
  text-align: center;
  background: #f0faf2;
  color: #1a1a1a;
  outline: none;
  font-family: 'Montserrat', sans-serif;
}
.capture-count-input:focus    { border-color: #55a472; }
.capture-count-input:disabled { opacity: 0.4; }

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

/* Fila con botón de entrenar + engranaje de configuración */
.train-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-top: 0.5rem;
}
.train-btn    { flex: 1; justify-content: center; }
.settings-btn { flex-shrink: 0; font-size: 1rem; padding: 0.5rem 0.7rem; }

/* Botón de reinicio al pie del panel central */
.reset-btn { width: 100%; justify-content: center; margin-top: 0.8rem; }

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

/* ─── Log de predicciones ────────────────────────────────────────────────── */
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
button {
  padding: 0.5rem 1rem; border-radius: 8px; border: none; cursor: pointer;
  font-size: 0.88rem; font-weight: 600; transition: opacity 0.2s;
}
button:hover    { opacity: 0.85; }
button:disabled { opacity: 0.35; cursor: not-allowed; }

.btn-primary      { background: #7c3aed; color: #fff; }
.btn-success      { background: #059669; color: #fff; }
.btn-danger       { background: #dc2626; color: #fff; }
.btn-info         { background: #0369a1; color: #fff; }
.btn-ghost        { background: rgba(0,0,0,0.04); color: #555; border: 1px solid #ccc; }
.btn-outline-danger {
  background: transparent;
  color: #dc2626;
  border: 1.5px solid #dc2626;
}
.btn-outline-danger:hover { background: rgba(220,38,38,0.06); }

.btn-export {
  background: #1B512D;
  color: #fff;
}
.btn-export:hover:not(:disabled) { background: #2d6a4f; }
</style>
