<script setup>
import Header from './components/Header.vue'
import { useModeloImagenes } from './composables/ModeloImagenes'

const {
  classes,
  canTrain,
  cameraElements,
  appPhase,
  isTraining,
  trainingMessage,
  trainingProgress,
  isTrainingComplete,
  trainingAccuracy,
  showTrainingSettings,
  trainingConfig,
  predictCameraEl,
  isPredicting,
  predictedLabel,
  predictedConfidence,
  trainedClassNames,
  classProbabilities,
  predictionLog,
  addClass,
  removeClass,
  toggleCamera,
  captureImages,
  trainModel,
  startPredictCamera,
  stopPrediction,
  resetAll,
} = useModeloImagenes()
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

<style scoped src="./styles/ModeloImagenes.css"></style>
