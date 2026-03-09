import { ref, reactive, computed, nextTick, onUnmounted } from 'vue'

// ─── Constantes ───────────────────────────────────────────────────────────────
const API = '/api'

// Colores asignados rotativamente a cada clase de entrenamiento
const PALETTE = ['#7c3aed', '#059669', '#0369a1', '#d97706', '#dc2626', '#0891b2', '#65a30d']

// Mínimo de imágenes que debe tener cada clase para poder entrenar
const MIN_IMAGES_PER_CLASS = 15

export function useModeloImagenes() {
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

  // Retornar todo lo que el template necesita
  return {
    classes,
    canTrain,
    cameraElements,
    cameraStreams,
    appPhase,
    isTraining,
    trainingMessage,
    trainingProgress,
    isTrainingComplete,
    trainingAccuracy,
    showTrainingSettings,
    trainingConfig,
    predictCameraEl,
    predictCameraStream,
    predictionTimer,
    isPredicting,
    predictedLabel,
    predictedConfidence,
    trainedClassNames,
    classProbabilities,
    predictionLog,
    addClass,
    removeClass,
    toggleCamera,
    stopClassCamera,
    frameToBase64,
    uploadImageToAPI,
    captureImages,
    trainModel,
    startPredictCamera,
    stopPrediction,
    runPrediction,
    resetAll,
    sleep,
  }
}
