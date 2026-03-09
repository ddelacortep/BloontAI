import { ref, reactive, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'

export function useSnakeModel() {
  const router = useRouter()
  const API = 'http://localhost:8002'

  /* ─── Snake Game + IA (backend Python) ─── */
  const GRID = 20

  // Estado reactivo del juego para renderizar en SnakeCanvas
  const game = reactive({
    gridSize: GRID,
    snake: [{ x: 10, y: 10 }],
    food: { x: 15, y: 15 },
    score: 0,
    direction: 1,
    gameOver: false,
  })

  const isTraining = ref(false)
  const isPlaying = ref(false)
  const isPaused = ref(false)
  const isLoading = ref(false)
  const episode = ref(0)
  const currentScore = ref(0)
  const bestScore = ref(0)
  const epsilon = ref(1)
  const scores = ref([])
  const speed = ref(50)
  const trainBatch = ref(10) // episodios por lote de entrenamiento
  const statusText = ref('')

  async function startTraining() {
    if (isTraining.value) return
    isTraining.value = true
    isPaused.value = false
    statusText.value = 'Reseteando agente...'

    try {
      // Resetear agente en el backend
      await fetch(`${API}/snake/reset`, { method: 'DELETE' })
      episode.value = 0
      scores.value = []
      bestScore.value = 0

      await runTrainingLoop()
    } catch (e) {
      console.error('Error en startTraining:', e)
      statusText.value = 'Error: ' + e.message
      isTraining.value = false
    }
  }

  async function runTrainingLoop() {
    while (isTraining.value) {
      if (isPaused.value) { await sleep(200); continue }

      try {
        isLoading.value = true
        statusText.value = `Entrenando ${trainBatch.value} episodios...`

        // Entrenar un lote de episodios en el backend
        const res = await fetch(`${API}/snake/train`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ episodes: trainBatch.value, grid_size: GRID }),
        })

        if (!res.ok) {
          const err = await res.text()
          console.error('Error /snake/train:', err)
          statusText.value = 'Error en entrenamiento'
          break
        }

        const data = await res.json()
        isLoading.value = false

        // Actualizar métricas desde la respuesta del backend
        episode.value = data.episodes_trained
        bestScore.value = data.best_score
        epsilon.value = data.epsilon
        scores.value = [...scores.value, ...data.last_scores]
        currentScore.value = data.last_scores[data.last_scores.length - 1] ?? 0

        // Reproducir una partida para visualizar el progreso
        statusText.value = 'Reproduciendo partida de la IA...'
        await playOneGame()
        statusText.value = ''
      } catch (e) {
        console.error('Error en runTrainingLoop:', e)
        statusText.value = 'Error: ' + e.message
        isLoading.value = false
        break
      }
    }
  }

  async function playOneGame() {
    const res = await fetch(`${API}/snake/play`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grid_size: GRID }),
    })
    const data = await res.json()

    isPlaying.value = true
    for (const frame of data.frames) {
      if (!isTraining.value && !isPlaying.value) break
      game.snake = frame.snake
      game.food = frame.food
      game.score = frame.score
      game.direction = frame.direction
      currentScore.value = frame.score
      if (speed.value > 0) await sleep(speed.value)
    }
    isPlaying.value = false
  }

  function togglePause() { isPaused.value = !isPaused.value }

  function stopTraining() {
    isTraining.value = false
    isPaused.value = false
    isPlaying.value = false
  }

  onBeforeUnmount(() => stopTraining())

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

  return {
    router,
    game,
    isTraining,
    isPlaying,
    isPaused,
    isLoading,
    episode,
    currentScore,
    bestScore,
    epsilon,
    scores,
    speed,
    trainBatch,
    statusText,
    startTraining,
    togglePause,
    stopTraining,
  }
}
