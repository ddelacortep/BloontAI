import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'

const API          = '/api-audio'
const PALETTE      = ['#7c3aed', '#059669', '#0369a1', '#d97706', '#dc2626', '#0891b2', '#65a30d']
const RECORD_SECONDS = 3
const SAMPLE_RATE  = 48000

// ── Utils ──────────────────────────────────────────────────────────────────
function sleep(ms) {
  return new Promise(r => setTimeout(r, ms))
}

function mergeChunks(chunks) {
  const total  = chunks.reduce((acc, c) => acc + c.length, 0)
  const result = new Float32Array(total)
  let offset   = 0
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.length }
  return result
}

function float32ToBase64(float32Array) {
  const bytes  = new Uint8Array(float32Array.buffer)
  let binary   = ''
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}

async function captureAudio() {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { sampleRate: SAMPLE_RATE, channelCount: 1, echoCancellation: false, noiseSuppression: false },
  })
  const audioCtx  = new AudioContext({ sampleRate: SAMPLE_RATE })
  const source    = audioCtx.createMediaStreamSource(stream)
  const processor = audioCtx.createScriptProcessor(4096, 1, 1)
  const chunks    = []

  processor.onaudioprocess = (e) => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)))
  source.connect(processor)
  processor.connect(audioCtx.destination)

  await sleep(RECORD_SECONDS * 1000)

  processor.disconnect()
  source.disconnect()
  stream.getTracks().forEach(t => t.stop())
  await audioCtx.close()

  return { chunks, sampleRate: audioCtx.sampleRate || SAMPLE_RATE }
}

// ── Composable principal ───────────────────────────────────────────────────
export function useModeloAudio() {
  // Estado de usuarios
  const users  = reactive([
    { id: 1, name: '', audioCount: 0, color: PALETTE[0], recording: false, recordMsg: '', _localClips: [] },
    { id: 2, name: '', audioCount: 0, color: PALETTE[1], recording: false, recordMsg: '', _localClips: [] },
  ])
  let nextId = 3

  // Fase de la app: 'capture' | 'training' | 'predict'
  const phase = ref('capture')

  // Estado de entrenamiento
  const trainRunning  = ref(false)
  const trainMsg      = ref('')
  const trainPct      = ref(0)
  const trainDone     = ref(false)
  const trainAccuracy = ref(null)

  // Estado de predicción
  const predicting       = ref(false)
  const predictResult    = ref('')
  const predictConf      = ref('')
  const predictRecording = ref(false)
  const probUsers        = ref([])
  const probData         = reactive({})
  const logLines         = ref([])
  const continuousListening = ref(false)
  let _stopListening = false

  // Computed
  const canTrain = computed(() =>
    users.filter(u => u.name.trim()).length >= 2 &&
    users.filter(u => u.name.trim()).every(u => u.audioCount >= 3)
  )

  // ── Gestión de usuarios ──────────────────────────────────────────────────
  function addUser() {
    users.push({
      id: nextId++,
      name: '', audioCount: 0,
      color: PALETTE[users.length % PALETTE.length],
      recording: false, recordMsg: '', _localClips: [],
    })
  }

  function removeUser(idx) {
    if (users.length > 2) users.splice(idx, 1)
  }

  // ── Grabación ────────────────────────────────────────────────────────────
  async function recordAudio(user) {
    if (!user.name.trim()) { alert('Escribe el nombre del usuario primero.'); return }
    if (user.recording) return

    user.recording = true
    user.recordMsg = '🔴 Grabando…'

    let result
    try {
      result = await captureAudio()
    } catch (err) {
      user.recording = false
      user.recordMsg = ''
      alert('No se pudo acceder al micrófono: ' + err.message)
      return
    }

    user.recordMsg = 'Procesando…'
    const b64 = float32ToBase64(mergeChunks(result.chunks))

    try {
      const res = await fetch(`${API}/audio/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: user.name.trim(), audio_b64: b64, sample_rate: result.sampleRate }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      user._localClips.push({ b64, sr: result.sampleRate })
      user.audioCount++
      user.recordMsg = '✅ Guardado'
      setTimeout(() => { user.recording = false; user.recordMsg = '' }, 1500)
    } catch (e) {
      user.recordMsg = `❌ ${e.message}`
      setTimeout(() => { user.recording = false; user.recordMsg = '' }, 3000)
    }
  }

  async function recordMultiple(user, n = 5) {
    for (let i = 0; i < n; i++) {
      user.recordMsg = `Audio ${i + 1}/${n} — ¡Habla!`
      await recordAudio(user)
      if (i < n - 1) await sleep(500)
    }
  }

  // ── Entrenamiento ─────────────────────────────────────────────────────────
  async function trainModel() {
    phase.value        = 'training'
    trainRunning.value = true
    trainDone.value    = false
    trainPct.value     = 10
    trainMsg.value     = 'Limpiando sesión anterior…'

    try {
      await fetch(`${API}/audio/reset`, { method: 'DELETE' })

      trainPct.value = 20
      trainMsg.value = 'Subiendo audios al servidor…'

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

  // ── Predicción continua ───────────────────────────────────────────────────
  function toggleListening() {
    continuousListening.value ? stopListening() : startListening()
  }

  async function startListening() {
    if (continuousListening.value) return
    continuousListening.value = true
    _stopListening = false
    predicting.value = true

    while (!_stopListening) {
      predictRecording.value = true
      predictResult.value    = '🔴 Escuchando…'
      predictConf.value      = ''

      let result
      try {
        result = await captureAudio()
      } catch (err) {
        alert('No se pudo acceder al micrófono: ' + err.message)
        break
      }

      if (_stopListening) break

      predictResult.value    = 'Analizando…'
      predictRecording.value = false

      const b64 = float32ToBase64(mergeChunks(result.chunks))

      try {
        const res  = await fetch(`${API}/audio/predict`, {
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
      }

      if (!_stopListening) await sleep(300)
    }

    continuousListening.value = false
    predictRecording.value    = false
  }

  function stopListening() {
    _stopListening = true
  }

  // ── Reset ─────────────────────────────────────────────────────────────────
  async function resetAll() {
    stopListening()
    await fetch(`${API}/audio/reset`, { method: 'DELETE' }).catch(() => {})

    users.forEach(u => {
      u.audioCount = 0; u.recording = false
      u.recordMsg  = ''; u.name = ''; u._localClips = []
    })

    phase.value     = 'capture'
    trainDone.value = false; trainPct.value = 0; trainMsg.value = ''
    predicting.value = false; predictResult.value = ''; predictConf.value = ''
    continuousListening.value = false
    probUsers.value = []; logLines.value = []
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────
  onMounted(async () => {
    await fetch(`${API}/audio/reset`, { method: 'DELETE' }).catch(() => {})
  })

  onUnmounted(() => stopListening())

  return {
    // State
    users, phase, RECORD_SECONDS,
    trainRunning, trainMsg, trainPct, trainDone, trainAccuracy,
    predicting, predictResult, predictConf, predictRecording,
    probUsers, probData, logLines, continuousListening, canTrain,
    // Actions
    addUser, removeUser, recordAudio, recordMultiple,
    trainModel, toggleListening, resetAll,
  }
}
