<script setup>
import Header from './components/Header.vue'
import Botones from './components/Botones.vue'
import SnakeCanvas from './components/SnakeCanvas.vue'
import PerformanceChart from './components/PerformanceChart.vue'
import { useSnakeModel } from './composables/useSnakeModel.js'

const {
  router,
  game,
  isTraining,
  isPaused,
  isLoading,
  episode,
  currentScore,
  bestScore,
  epsilon,
  scores,
  speed,
  statusText,
  startTraining,
  togglePause,
  stopTraining,
} = useSnakeModel()
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

            <!-- Status -->
            <div v-if="statusText" class="status-bar">
              <span class="spinner" v-if="isLoading">⏳</span>
              {{ statusText }}
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

<style scoped src="./styles/ModeloVideo.css"></style>    