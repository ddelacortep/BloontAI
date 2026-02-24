<script setup>
import { ref, reactive, computed, nextTick, onUnmounted } from 'vue'

const API = '/api'

// ─── Paleta de colores ────────────────────────────────────────────────────
const PALETTE = ['#7c3aed', '#059669', '#0369a1', '#d97706', '#dc2626', '#0891b2', '#65a30d']

// ─── Clases: array reactivo de objetos ────────────────────────────────────
// Cada clase tiene su propia cámara y contador de imágenes
const classes = reactive([
  { id: 1, name: '', imageCount: 0, color: PALETTE[0], cameraOn: false, capturing: false, capturePct: 0, captureMsg: '' },
  { id: 2, name: '', imageCount: 0, color: PALETTE[1], cameraOn: false, capturing: false, capturePct: 0, captureMsg: '' },
])
let nextId = 3

// Refs dinámicos para los elementos <video> de cada clase (keyed por cls.id)
const videoEls = reactive({})     // { [id]: HTMLVideoElement }
const streams  = reactive({})     // { [id]: MediaStream }

// ─── Fase de la app ───────────────────────────────────────────────────────
// 'capture' | 'training' | 'predict'
const phase = ref('capture')

// ─── Entrenamiento ────────────────────────────────────────────────────────
const trainRunning  = ref(false)
const trainMsg      = ref('')
const trainPct      = ref(0)
const trainDone     = ref(false)
const trainAccuracy = ref(null)

// ─── Predicción ───────────────────────────────────────────────────────────
const predictVideoEl  = ref(null)
const predictStream   = ref(null)
const predictInterval = ref(null)
const predicting      = ref(false)
const overlayLabel    = ref('—')
const overlayConf     = ref('')
const probClasses     = ref([])
const probData        = reactive({})   // { cls: { pct: 0 } }
const logLines        = ref([])

// ─── Computed ─────────────────────────────────────────────────────────────
const canTrain = computed(() =>
  classes.filter(c => c.name.trim()).length >= 2 &&
  classes.filter(c => c.name.trim()).every(c => c.imageCount >= 5)
)

// ─── Gestión de clases ────────────────────────────────────────────────────
function addClass() {
  classes.push({
    id: nextId++,
    name: '', imageCount: 0,
    color: PALETTE[classes.length % PALETTE.length],
    cameraOn: false, capturing: false, capturePct: 0, captureMsg: '',
  })
}
function removeClass(idx) {
  if (classes.length <= 2) return
  const cls = classes[idx]
  stopClassCamera(cls)
  classes.splice(idx, 1)
}

// ─── Cámara por clase ─────────────────────────────────────────────────────
async function toggleCamera(cls) {
  if (cls.cameraOn) {
    stopClassCamera(cls)
    return
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } })
    streams[cls.id] = stream
    cls.cameraOn = true
    await nextTick()
    const el = videoEls[cls.id]
    if (el) { el.srcObject = stream; await el.play().catch(() => {}) }
  } catch (err) {
    alert('No se pudo acceder a la cámara: ' + err.message)
  }
}
function stopClassCamera(cls) {
  if (streams[cls.id]) { streams[cls.id].getTracks().forEach(t => t.stop()); delete streams[cls.id] }
  if (videoEls[cls.id]) videoEls[cls.id].srcObject = null
  cls.cameraOn = false
}

// ─── Captura de imágenes ──────────────────────────────────────────────────
function frameToBase64(el) {
  const c = document.createElement('canvas'); c.width = 224; c.height = 224
  const ctx = c.getContext('2d')
  const size = Math.min(el.videoWidth, el.videoHeight)
  ctx.drawImage(el, (el.videoWidth - size) / 2, (el.videoHeight - size) / 2, size, size, 0, 0, 224, 224)
  return c.toDataURL('image/jpeg', 0.85).split(',')[1]
}

async function captureImages(cls) {
  if (!cls.cameraOn || !videoEls[cls.id]) { alert('Activa la cámara primero.'); return }
  if (!cls.name.trim()) { alert('Escribe el nombre de la clase primero.'); return }
  const N = 15
  cls.capturing  = true
  cls.capturePct = 0
  cls.captureMsg = ''
  try {
    for (let i = 0; i < N; i++) {
      cls.captureMsg = `${i + 1} / ${N}`
      cls.capturePct = Math.round(((i + 1) / N) * 100)

      const b64 = frameToBase64(videoEls[cls.id])
      const res = await fetch(`${API}/upload`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: cls.name.trim(), image_b64: b64 }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      cls.imageCount++
      await sleep(150)
    }
    cls.captureMsg = '✅ Listo'
    setTimeout(() => { cls.capturing = false; cls.captureMsg = '' }, 2000)
  } catch (e) {
    cls.captureMsg = `❌ Error: ${e.message}`
    setTimeout(() => { cls.capturing = false; cls.captureMsg = '' }, 3000)
  }
}

// ─── Entrenamiento ────────────────────────────────────────────────────────
async function trainModel() {
  phase.value      = 'training'
  trainRunning.value = true
  trainDone.value    = false
  trainPct.value     = 15
  trainMsg.value     = 'Cargando MobileNetV2…'

  try {
    trainPct.value = 35
    trainMsg.value = 'Entrenando con Transfer Learning…'

    const res  = await fetch(`${API}/train`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ epochs: 20, fine_tune: true }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Error en entrenamiento')

    trainPct.value      = 100
    trainMsg.value      = `Precisión: ${(data.val_accuracy * 100).toFixed(1)}%  ·  ${data.epochs_run} épocas`
    trainAccuracy.value = data.val_accuracy
    trainDone.value     = true
    probClasses.value   = data.classes
    data.classes.forEach(c => { probData[c] = { pct: 0 } })
  } catch (e) {
    trainMsg.value = '❌ ' + e.message
    phase.value    = 'capture'
  } finally {
    trainRunning.value = false
  }
}

// ─── Cámara de predicción ─────────────────────────────────────────────────
async function startPredictCamera() {
  try {
    if (predictStream.value) predictStream.value.getTracks().forEach(t => t.stop())
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } })
    predictStream.value = stream
    await nextTick()
    predictVideoEl.value.srcObject = stream
    await predictVideoEl.value.play().catch(() => {})
    predicting.value      = true
    predictInterval.value = setInterval(predict, 600)
  } catch (err) {
    alert('No se pudo acceder a la cámara: ' + err.message)
  }
}
function stopPredict() {
  clearInterval(predictInterval.value); predictInterval.value = null
  if (predictStream.value) { predictStream.value.getTracks().forEach(t => t.stop()); predictStream.value = null }
  predicting.value   = false
  overlayLabel.value = '—'
  overlayConf.value  = ''
}

async function predict() {
  if (!predictVideoEl.value) return
  try {
    const res  = await fetch(`${API}/predict`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_b64: frameToBase64(predictVideoEl.value) }),
    })
    const data = await res.json()
    if (!res.ok) return
    overlayLabel.value = data.label
    overlayConf.value  = `${(data.confidence * 100).toFixed(0)}%`
    Object.entries(data.probabilities).forEach(([cls, p]) => {
      if (probData[cls]) probData[cls].pct = +(p * 100).toFixed(1)
    })
    logLines.value.unshift(`[${new Date().toLocaleTimeString()}]  ${data.label}  ${(data.confidence * 100).toFixed(0)}%`)
    if (logLines.value.length > 25) logLines.value.pop()
  } catch (e) { /* ignorar errores de red */ }
}

// ─── Reiniciar todo ───────────────────────────────────────────────────────
async function resetAll() {
  stopPredict()
  classes.forEach(stopClassCamera)
  await fetch(`${API}/reset`, { method: 'DELETE' }).catch(() => {})
  classes.forEach(c => { c.imageCount = 0; c.cameraOn = false; c.capturing = false; c.name = '' })
  phase.value    = 'capture'
  trainDone.value = false; trainPct.value = 0; trainMsg.value = ''
  probClasses.value = []; logLines.value = []
}

// ─── Utils ────────────────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

onUnmounted(() => {
  stopPredict()
  classes.forEach(stopClassCamera)
})
</script>

<template>
  <div class="app">

    <!-- Cabecera -->
    <header class="topbar">
      <div class="topbar-title">🎯 Clasificador Webcam · Transfer Learning</div>
      <button class="btn btn-ghost" @click="resetAll" title="Reiniciar todo">↺ Reiniciar</button>
    </header>

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
  font-family: system-ui, sans-serif;
  background: #0d0d14;
  color: #e5e5e5;
  min-height: 100vh;
}

/* ─── Topbar ──────────────────────────────────────────────────────────────── */
.topbar {
  background: #13132a;
  border-bottom: 2px solid #7c3aed;
  padding: 0.9rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.topbar-title { font-size: 1.2rem; font-weight: 700; color: #a78bfa; }

/* ─── Layout de flujo horizontal ─────────────────────────────────────────── */
.flow-root {
  display: flex;
  align-items: flex-start;
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
  border: 2px dashed #4c4c8a;
  background: transparent;
  color: #a78bfa;
  font-size: 0.9rem;
  padding: 0.7rem;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.2s;
}
.add-class-btn:hover { background: rgba(124,58,237,0.1); }

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
.connector-line  { width: 40px; height: 2px; background: #4c4c8a; }
.connector-arrow { color: #4c4c8a; font-size: 0.9rem; margin-left: -4px; }

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
.btn-ghost   { background: rgba(255,255,255,0.08); color: #ccc; border: 1px solid #444; }
</style>

