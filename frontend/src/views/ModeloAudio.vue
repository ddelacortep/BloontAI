<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import Header from './components/Header.vue'

const API = '/api-audio'

// Al montar la página, limpiar datos de sesiones anteriores en el backend
onMounted(async () => {
  await fetch(`${API}/audio/reset`, { method: 'DELETE' }).catch(() => {})
})

// ─── Paleta de colores ────────────────────────────────────────────────────
const PALETTE = ['#7c3aed', '#059669', '#0369a1', '#d97706', '#dc2626', '#0891b2', '#65a30d']

// ─── Usuarios: array reactivo ─────────────────────────────────────────────
const users = reactive([
  { id: 1, name: '', audioCount: 0, color: PALETTE[0], recording: false, recordMsg: '', _localClips: [] },
  { id: 2, name: '', audioCount: 0, color: PALETTE[1], recording: false, recordMsg: '', _localClips: [] },
])
let nextId = 3

// ─── Fase de la app ───────────────────────────────────────────────────────
const phase = ref('capture')   // 'capture' | 'training' | 'predict'

// ─── Entrenamiento ────────────────────────────────────────────────────────
const trainRunning  = ref(false)
const trainMsg      = ref('')
const trainPct      = ref(0)
const trainDone     = ref(false)
const trainAccuracy = ref(null)

// ─── Predicción ───────────────────────────────────────────────────────────
const predicting       = ref(false)
const predictResult    = ref('')
const predictConf      = ref('')
const probUsers        = ref([])
const probData         = reactive({})
const logLines         = ref([])
const predictRecording = ref(false)

// ─── Computed ─────────────────────────────────────────────────────────────
const canTrain = computed(() =>
  users.filter(u => u.name.trim()).length >= 2 &&
  users.filter(u => u.name.trim()).every(u => u.audioCount >= 3)
)

// ─── Gestión de usuarios ──────────────────────────────────────────────────
function addUser() {
  users.push({
    id: nextId++,
    name: '', audioCount: 0,
    color: PALETTE[users.length % PALETTE.length],
    recording: false, recordMsg: '', _localClips: [],
  })
}
function removeUser(idx) {
  if (users.length <= 2) return
  users.splice(idx, 1)
}

// ─── Grabación de audio (PCM float32 vía AudioContext) ────────────────────
const RECORD_SECONDS = 3
const SAMPLE_RATE    = 48000

async function recordAudio(user) {
  if (!user.name.trim()) { alert('Escribe el nombre del usuario primero.'); return }
  if (user.recording) return

  user.recording = true
  user.recordMsg = '🔴 Grabando…'

  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: SAMPLE_RATE, channelCount: 1, echoCancellation: false, noiseSuppression: false }
    })
  } catch (err) {
    user.recording = false
    user.recordMsg = ''
    alert('No se pudo acceder al micrófono: ' + err.message)
    return
  }

  const audioCtx   = new AudioContext({ sampleRate: SAMPLE_RATE })
  const source     = audioCtx.createMediaStreamSource(stream)
  const processor  = audioCtx.createScriptProcessor(4096, 1, 1)
  const chunks     = []

  processor.onaudioprocess = (e) => {
    chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)))
  }

  source.connect(processor)
  processor.connect(audioCtx.destination)

  // Graba durante RECORD_SECONDS segundos
  await sleep(RECORD_SECONDS * 1000)

  // Detener todo
  processor.disconnect()
  source.disconnect()
  stream.getTracks().forEach(t => t.stop())
  await audioCtx.close()

  user.recordMsg = 'Procesando…'

  // Concatenar chunks en un solo Float32Array
  const totalLength = chunks.reduce((acc, c) => acc + c.length, 0)
  const pcmData     = new Float32Array(totalLength)
  let offset = 0
  for (const chunk of chunks) {
    pcmData.set(chunk, offset)
    offset += chunk.length
  }

  // Convertir a base64
  const b64 = float32ToBase64(pcmData)

  // Enviar al backend
  try {
    const res = await fetch(`${API}/audio/upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        label: user.name.trim(),
        audio_b64: b64,
        sample_rate: audioCtx.sampleRate || SAMPLE_RATE,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    // Guardar clip localmente para poder re-subir tras reset
    const sr = audioCtx.sampleRate || SAMPLE_RATE
    if (!user._localClips) user._localClips = []
    user._localClips.push({ b64, sr })
    user.audioCount++
    user.recordMsg = '✅ Guardado'
    setTimeout(() => { user.recording = false; user.recordMsg = '' }, 1500)
  } catch (e) {
    user.recordMsg = `❌ ${e.message}`
    setTimeout(() => { user.recording = false; user.recordMsg = '' }, 3000)
  }
}

// ─── Grabar múltiples clips seguidos ──────────────────────────────────────
async function recordMultiple(user, n = 5) {
  for (let i = 0; i < n; i++) {
    user.recordMsg = `Audio ${i + 1}/${n} — ¡Habla!`
    await recordAudio(user)
    if (i < n - 1) await sleep(500)
  }
}

// ─── Entrenamiento ────────────────────────────────────────────────────────
async function trainModel() {
  phase.value        = 'training'
  trainRunning.value = true
  trainDone.value    = false
  trainPct.value     = 10
  trainMsg.value     = 'Limpiando sesión anterior…'

  try {
    // 1. Reset del backend (elimina modelo y audios previos)
    await fetch(`${API}/audio/reset`, { method: 'DELETE' })

    trainPct.value = 20
    trainMsg.value = 'Subiendo audios al servidor…'

    // 2. Re-subir todos los audios de la sesión actual
    //    (localAudio guarda los blobs base64 de cada usuario)
    for (const user of users) {
      const name = user.name.trim()
      if (!name || !user._localClips?.length) continue
      for (const clip of user._localClips) {
        await fetch(`${API}/audio/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label: name, audio_b64: clip.b64, sample_rate: clip.sr }),
        })
      }
    }

    trainPct.value = 40
    trainMsg.value = 'Entrenando red neuronal…'

    const res  = await fetch(`${API}/audio/train`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ epochs: 50 }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Error en entrenamiento')

    trainPct.value      = 100
    trainMsg.value      = `Precisión: ${(data.val_accuracy * 100).toFixed(1)}%  ·  ${data.epochs_run} épocas`
    trainAccuracy.value = data.val_accuracy
    trainDone.value     = true
    probUsers.value     = data.users
    data.users.forEach(u => { probData[u] = { pct: 0 } })
  } catch (e) {
    trainMsg.value = '❌ ' + e.message
    phase.value    = 'capture'
  } finally {
    trainRunning.value = false
  }
}

// ─── Predicción continua ──────────────────────────────────────────────────
const continuousListening = ref(false)
let _stopListening = false   // flag interna para cortar el bucle

function toggleListening() {
  if (continuousListening.value) {
    stopListening()
  } else {
    startListening()
  }
}

async function startListening() {
  if (continuousListening.value) return
  continuousListening.value = true
  _stopListening = false
  predicting.value = true

  // Bucle continuo: graba → predice → repite
  while (!_stopListening) {
    predictRecording.value = true
    predictResult.value    = '🔴 Escuchando…'
    predictConf.value      = ''

    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: SAMPLE_RATE, channelCount: 1, echoCancellation: false, noiseSuppression: false }
      })
    } catch (err) {
      alert('No se pudo acceder al micrófono: ' + err.message)
      break
    }

    // Si el usuario paró mientras pedíamos el mic, salimos limpiamente
    if (_stopListening) { stream.getTracks().forEach(t => t.stop()); break }

    const audioCtx  = new AudioContext({ sampleRate: SAMPLE_RATE })
    const source    = audioCtx.createMediaStreamSource(stream)
    const processor = audioCtx.createScriptProcessor(4096, 1, 1)
    const chunks    = []

    processor.onaudioprocess = (e) => {
      chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)))
    }

    source.connect(processor)
    processor.connect(audioCtx.destination)

    // Graba durante RECORD_SECONDS
    await sleep(RECORD_SECONDS * 1000)

    processor.disconnect()
    source.disconnect()
    stream.getTracks().forEach(t => t.stop())
    await audioCtx.close()

    if (_stopListening) break

    predictResult.value = 'Analizando…'
    predictRecording.value = false

    // Concatenar chunks
    const totalLength = chunks.reduce((acc, c) => acc + c.length, 0)
    const pcmData     = new Float32Array(totalLength)
    let offset = 0
    for (const chunk of chunks) { pcmData.set(chunk, offset); offset += chunk.length }

    const b64 = float32ToBase64(pcmData)

    try {
      const res = await fetch(`${API}/audio/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio_b64: b64, sample_rate: SAMPLE_RATE }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Error en predicción')

      predictResult.value = data.label
      predictConf.value   = `${(data.confidence * 100).toFixed(0)}%`

      Object.entries(data.probabilities).forEach(([usr, p]) => {
        if (probData[usr]) probData[usr].pct = +(p * 100).toFixed(1)
      })

      logLines.value.unshift(`[${new Date().toLocaleTimeString()}]  ${data.label}  ${(data.confidence * 100).toFixed(0)}%`)
      if (logLines.value.length > 25) logLines.value.pop()
    } catch (e) {
      predictResult.value = '❌ Error'
      predictConf.value   = e.message
      // Un error puntual no para la escucha; sigue intentando
    }

    // Pequeña pausa entre iteraciones para no saturar
    if (!_stopListening) await sleep(300)
  }

  // Limpieza al salir del bucle
  continuousListening.value = false
  predictRecording.value    = false
}

function stopListening() {
  _stopListening = true
}

// ─── Reiniciar todo ───────────────────────────────────────────────────────
async function resetAll() {
  stopListening()
  await fetch(`${API}/audio/reset`, { method: 'DELETE' }).catch(() => {})
  users.forEach(u => { u.audioCount = 0; u.recording = false; u.recordMsg = ''; u.name = ''; u._localClips = [] })
  phase.value     = 'capture'
  trainDone.value = false; trainPct.value = 0; trainMsg.value = ''
  predicting.value = false; predictResult.value = ''; predictConf.value = ''
  continuousListening.value = false
  probUsers.value = []; logLines.value = []
}

// ─── Utils ────────────────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

function float32ToBase64(float32Array) {
  const bytes = new Uint8Array(float32Array.buffer)
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

onUnmounted(() => {
  stopListening()
})
</script>

<template>
  <Header />
  <div class="app">

    <!-- ─── Layout de flujo ──────────────────────────────────────────────── -->
    <div class="flow-root">

      <!-- COLUMNA IZQUIERDA: tarjetas de usuario -->
      <div class="col-users">
        <div
          v-for="(user, idx) in users"
          :key="user.id"
          class="user-card"
          :style="{ '--accent': user.color }"
        >
          <!-- Nombre -->
          <div class="card-header">
            <span class="dot" :style="{ background: user.color }"></span>
            <input
              v-model="user.name"
              class="name-input"
              placeholder="Nombre del usuario…"
              :disabled="phase !== 'capture'"
            />
            <button
              v-if="users.length > 2 && phase === 'capture'"
              class="btn-icon remove"
              @click="removeUser(idx)"
              title="Eliminar usuario"
            >✕</button>
          </div>

          <!-- Indicador de grabación -->
          <div class="mic-area" :class="{ active: user.recording }">
            <div class="mic-icon">🎤</div>
            <div v-if="user.recording" class="rec-pulse"></div>
            <small v-if="!user.recording" class="mic-hint">{{ RECORD_SECONDS }}s por clip</small>
          </div>

          <!-- Acciones -->
          <div class="card-actions">
            <button
              class="btn btn-primary"
              :disabled="user.recording || phase !== 'capture'"
              @click="recordAudio(user)"
            >
              🎤 Grabar 1 audio
            </button>
            <button
              class="btn btn-info"
              :disabled="user.recording || phase !== 'capture'"
              @click="recordMultiple(user, 3)"
            >
              🔁 Grabar 3 audios
            </button>
          </div>

          <!-- Mensaje de estado -->
          <div v-if="user.recordMsg" class="rec-msg" :style="{ color: user.color }">
            {{ user.recordMsg }}
          </div>

          <!-- Contador -->
          <div class="audio-count" :style="{ color: user.color }">
            {{ user.audioCount }} audios
            <span v-if="user.audioCount >= 3" style="color:#86efac"> ✓</span>
            <span v-else style="color:#888"> (mín. 3)</span>
          </div>
        </div>

        <!-- Botón añadir usuario -->
        <button
          v-if="phase === 'capture'"
          class="btn btn-ghost add-user-btn"
          @click="addUser"
        >+ Añadir usuario</button>
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
          <p class="hint">Graba audios de cada usuario y luego entrena el modelo.</p>
          <div class="user-summary">
            <div v-for="user in users" :key="user.id" class="summary-row">
              <span class="dot" :style="{ background: user.color }"></span>
              <span class="summary-name">{{ user.name || '(sin nombre)' }}</span>
              <span class="summary-count" :style="{ color: user.color }">{{ user.audioCount }} audios</span>
            </div>
          </div>
          <button
            class="btn btn-success train-btn"
            :disabled="!canTrain"
            @click="trainModel"
          >🚀 Entrenar modelo</button>
          <p v-if="!canTrain" class="hint-warn">Necesitas ≥ 2 usuarios con ≥ 3 audios cada uno.</p>
        </div>

        <div v-else class="train-progress-block">
          <div class="big-pct" :class="{ done: trainDone }">{{ trainPct }}%</div>
          <div class="pbar"><div class="pfill accent" :style="{ width: trainPct + '%' }"></div></div>
          <p class="train-msg">{{ trainMsg }}</p>

          <div v-if="trainDone" class="accuracy-badge">
            ✅ Precisión: <strong>{{ (trainAccuracy * 100).toFixed(1) }}%</strong>
          </div>
        </div>
      </div>

      <!-- Conector centro → derecha -->
      <div class="connector" :class="{ dimmed: !trainDone }">
        <div class="connector-line"></div>
        <div class="connector-arrow">▶</div>
      </div>

      <!-- COLUMNA DERECHA: predicción -->
      <div class="result-card" :class="{ dimmed: !trainDone }">
        <div class="center-card-title">🎙️ ¿Quién habla?</div>

        <div v-if="!trainDone" class="result-waiting">
          <span>Entrena el modelo primero</span>
        </div>

        <template v-else>
          <!-- Área de predicción -->
          <div class="predict-mic-area" :class="{ active: predictRecording }">
            <div class="predict-mic-icon">🎤</div>
            <div v-if="predictRecording" class="rec-pulse big"></div>
          </div>

          <!-- Resultado -->
          <div v-if="predicting" class="predict-result-box">
            <span class="pred-label">{{ predictResult }}</span>
            <span v-if="predictConf" class="pred-conf">{{ predictConf }}</span>
          </div>

          <!-- Botón escucha continua -->
          <div class="card-actions" style="justify-content:center; margin-top:0.8rem">
            <button
              class="btn"
              :class="continuousListening ? 'btn-danger' : 'btn-primary'"
              @click="toggleListening"
            >
              {{ continuousListening ? '⏹ Apagar escucha' : '🎤 Escuchar' }}
            </button>
          </div>
          <p v-if="continuousListening" class="hint" style="text-align:center;margin-top:0.3rem;color:#86efac;font-size:0.8rem">
            Escucha continua activa · graba cada {{ RECORD_SECONDS }}s
          </p>

          <!-- Barras de probabilidad -->
          <div v-if="probUsers.length" class="prob-list" style="margin-top:0.8rem">
            <div v-for="usr in probUsers" :key="usr" class="prob-row">
              <span class="prob-label">{{ usr }}</span>
              <div class="pbar"><div class="pfill accent" :style="{ width: probData[usr]?.pct + '%' }"></div></div>
              <span class="prob-val">{{ probData[usr]?.pct ?? 0 }}%</span>
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

/* ─── Columna izquierda (usuarios) ───────────────────────────────────────── */
.col-users {
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
  min-width: 320px;
  max-width: 360px;
  flex-shrink: 0;
}

/* ─── Tarjeta de usuario ─────────────────────────────────────────────────── */
.user-card {
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

/* ─── Área del micrófono ─────────────────────────────────────────────────── */
.mic-area {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f0fdf4;
  border: 1px solid #d1fae5;
  border-radius: 10px;
  padding: 1.2rem;
  min-height: 80px;
}
.mic-icon { font-size: 2rem; }
.mic-hint { color: #666; font-size: 0.75rem; margin-top: 0.3rem; }

.mic-area.active {
  background: #fef2f2;
  border: 2px solid #dc2626;
}

/* ─── Pulso de grabación ─────────────────────────────────────────────────── */
.rec-pulse {
  position: absolute;
  top: 8px; right: 8px;
  width: 12px; height: 12px;
  border-radius: 50%;
  background: #dc2626;
  animation: pulse 1s infinite;
}
.rec-pulse.big {
  width: 16px; height: 16px;
}
@keyframes pulse {
  0%   { opacity: 1; transform: scale(1); }
  50%  { opacity: 0.4; transform: scale(1.3); }
  100% { opacity: 1; transform: scale(1); }
}

/* ─── Mensaje de grabación ───────────────────────────────────────────────── */
.rec-msg {
  font-size: 0.82rem;
  font-weight: 600;
  text-align: center;
}

/* ─── Acciones de la tarjeta ─────────────────────────────────────────────── */
.card-actions {
  display: flex; gap: 0.5rem; flex-wrap: wrap;
}

/* ─── Contador de audios ─────────────────────────────────────────────────── */
.audio-count { font-size: 0.82rem; font-weight: 600; }

/* ─── Botón añadir usuario ───────────────────────────────────────────────── */
.add-user-btn {
  border: 2px dashed #1B512D;
  background: transparent;
  color: #1B512D;
  font-size: 0.9rem;
  padding: 0.7rem;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.2s;
}
.add-user-btn:hover { background: rgba(27,81,45,0.08); }

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

.user-summary    { display: flex; flex-direction: column; gap: 0.4rem; margin-bottom: 1rem; }
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

/* ─── Área de micrófono de predicción ────────────────────────────────────── */
.predict-mic-area {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0fdf4;
  border: 1px solid #d1fae5;
  border-radius: 10px;
  padding: 2rem;
  margin-bottom: 0.7rem;
}
.predict-mic-area.active {
  background: #fef2f2;
  border: 2px solid #dc2626;
}
.predict-mic-icon { font-size: 3rem; }

/* ─── Resultado de predicción ────────────────────────────────────────────── */
.predict-result-box {
  text-align: center;
  padding: 0.6rem;
}
.pred-label {
  display: block;
  font-size: 1.4rem; font-weight: 800; color: #1a3a26;
  line-height: 1.2;
}
.pred-conf {
  display: block;
  font-size: 1rem; font-weight: 600; color: #059669;
  margin-top: 0.2rem;
}

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
