<script setup>
import { ref, reactive, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import Header from './components/Header.vue'
import Botones from './components/Botones.vue'
import SnakeCanvas from './components/SnakeCanvas.vue'
import PerformanceChart from './components/PerformanceChart.vue'

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
const episode = ref(0)
const currentScore = ref(0)
const bestScore = ref(0)
const epsilon = ref(1)
const scores = ref([])
const speed = ref(50)
const trainBatch = ref(50) // episodios por lote de entrenamiento

async function startTraining() {
  if (isTraining.value) return
  isTraining.value = true
  isPaused.value = false

  // Resetear agente en el backend
  await fetch(`${API}/snake/reset`, { method: 'DELETE' })
  episode.value = 0
  scores.value = []
  bestScore.value = 0

  await runTrainingLoop()
}

async function runTrainingLoop() {
  while (isTraining.value) {
    if (isPaused.value) { await sleep(200); continue }

    // Entrenar un lote de episodios en el backend
    const res = await fetch(`${API}/snake/train`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episodes: trainBatch.value, grid_size: GRID }),
    })
    const data = await res.json()

    // Actualizar métricas desde la respuesta del backend
    episode.value = data.episodes_trained
    bestScore.value = data.best_score
    epsilon.value = data.epsilon
    scores.value = [...scores.value, ...data.last_scores]
    currentScore.value = data.last_scores[data.last_scores.length - 1] ?? 0

    // Reproducir una partida para visualizar el progreso
    await playOneGame()
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
</script>

<template>
  <Header />

  <div class="app">
    <!-- Top bar -->
    <div class="actions-bar">
      <Botones class="btn-back" @click="router.push('/seleccion-modelo')">
        <p>← Volver</p>
      </Botones>
      <span class="page-title">🎮 Modelo Video — Snake IA</span>
      <div></div>
    </div>

    <!-- Layout 2 columnas -->
    <div class="layout">
      <!-- COLUMNA IZQUIERDA -->
      <div class="col-left">
        <!-- Gráfico rendimiento -->
        <div class="panel">
          <div class="panel-header">
            <span class="panel-icon">📊</span>
            <h2>Rendimiento</h2>
          </div>
          <div class="panel-body">
            <PerformanceChart :scores="scores" />
          </div>
        </div>
      </div>

      <!-- COLUMNA DERECHA -->
      <div class="col-right">
        <div class="panel panel-game">
          <div class="panel-header">
            <span class="panel-icon">🐍</span>
            <h2>Snake — Entrenamiento IA</h2>
          </div>
          <div class="panel-body game-body">
            <SnakeCanvas :game="game" :size="400" />

            <!-- Stats -->
            <div class="stats-row">
              <div class="stat">
                <span class="stat-label">Episodio</span>
                <span class="stat-value">{{ episode }}</span>
              </div>
              <div class="stat">
                <span class="stat-label">Score actual</span>
                <span class="stat-value">{{ currentScore }}</span>
              </div>
              <div class="stat">
                <span class="stat-label">Mejor score</span>
                <span class="stat-value highlight">{{ bestScore }}</span>
              </div>
              <div class="stat">
                <span class="stat-label">Epsilon (ε)</span>
                <span class="stat-value">{{ epsilon }}</span>
              </div>
            </div>

            <!-- Velocidad -->
            <div class="speed-control">
              <label>Velocidad: <strong>{{ speed === 0 ? 'Máxima' : speed + ' ms' }}</strong></label>
              <input type="range" min="0" max="200" step="10" v-model.number="speed" />
            </div>

            <!-- Botones -->
            <div class="controls">
              <Botones v-if="!isTraining" class="btn-train" @click="startTraining">
                <p>🚀 Iniciar Entrenamiento</p>
              </Botones>
              <template v-else>
                <Botones class="btn-pause" @click="togglePause">
                  <p>{{ isPaused ? '▶ Reanudar' : '⏸ Pausar' }}</p>
                </Botones>
                <Botones class="btn-stop" @click="stopTraining">
                  <p>⏹ Detener</p>
                </Botones>
              </template>
            </div>

            <!-- Pasos -->
            <div v-if="!isTraining && episode === 0" class="steps-list">
              <div class="step">
                <span class="step-num">1</span>
                <span>Pulsa "Iniciar Entrenamiento"</span>
              </div>
              <div class="step">
                <span class="step-num">2</span>
                <span>La IA aprende por Deep Q-Learning en tiempo real</span>
              </div>
              <div class="step">
                <span class="step-num">3</span>
                <span>Observa cómo mejora en el gráfico de rendimiento</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }

.app {
  font-family: 'Montserrat', system-ui, sans-serif;
  background: #f5f5f5;
  color: #1a1a1a;
  min-height: 100vh;
}

/* Top bar */
.actions-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 2rem;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.btn-back {
  background-color: #1B512D;
  border-radius: 15px;
  padding: 10px 20px;
  color: white;
  font-size: 14px;
  font-weight: 600;
  border: none;
}
.btn-back p { margin: 0; color: white; }
.page-title { font-size: 1.2rem; font-weight: 700; color: #1B512D; }

/* Layout */
.layout {
  display: flex;
  gap: 1.5rem;
  padding: 1.5rem 2rem;
  align-items: flex-start;
}
.col-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  min-width: 0;
}
.col-right { flex: 1.2; min-width: 0; }

/* Panel */
.panel {
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08);
  overflow: hidden;
}
.panel-header {
  background: linear-gradient(135deg, #1B512D 0%, #2D7A4A 100%);
  color: white;
  padding: 0.9rem 1.3rem;
  display: flex;
  align-items: center;
  gap: 0.7rem;
}
.panel-icon { font-size: 1.3rem; }
.panel-header h2 { margin: 0; font-size: 1rem; font-weight: 600; }
.panel-body { padding: 1.2rem; }

/* Game body */
.game-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

/* Stats */
.stats-row {
  display: flex; gap: 1rem; flex-wrap: wrap;
  justify-content: center; width: 100%;
}
.stat {
  background: #f0fdf4; border-radius: 12px;
  padding: 0.6rem 1rem; text-align: center; min-width: 90px;
}
.stat-label { display: block; font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
.stat-value { display: block; font-size: 1.3rem; font-weight: 700; color: #1B512D; }
.stat-value.highlight { color: #B1CF5F; }

/* Speed */
.speed-control { width: 100%; max-width: 400px; text-align: center; }
.speed-control label { font-size: 0.85rem; color: #666; }
.speed-control input[type=range] { width: 100%; accent-color: #1B512D; margin-top: 0.3rem; }

/* Controls */
.controls { display: flex; gap: 0.8rem; flex-wrap: wrap; justify-content: center; }
.btn-train {
  background: linear-gradient(135deg, #B1CF5F 0%, #7FD1AE 100%);
  color: #1B512D; padding: 0.9rem 2rem; border-radius: 15px;
  font-weight: 700; border: none;
}
.btn-train p { margin: 0; }
.btn-pause {
  background: #f59e0b; color: #fff;
  padding: 0.8rem 1.5rem; border-radius: 15px;
  font-weight: 600; border: none;
}
.btn-pause p { margin: 0; color: white; }
.btn-stop {
  background: #dc2626; color: #fff;
  padding: 0.8rem 1.5rem; border-radius: 15px;
  font-weight: 600; border: none;
}
.btn-stop p { margin: 0; color: white; }

/* Steps */
.steps-list { display: flex; flex-direction: column; gap: 0.7rem; width: 100%; max-width: 400px; }
.step { display: flex; align-items: center; gap: 0.8rem; padding: 0.6rem; background: #f0fdf4; border-radius: 10px; }
.step-num {
  background: #1B512D; color: white; width: 26px; height: 26px;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 0.8rem; flex-shrink: 0;
}
.step span:last-child { font-size: 0.9rem; }

/* Responsive */
@media (max-width: 960px) {
  .layout { flex-direction: column; }
  .col-right { order: -1; }
}
</style>    