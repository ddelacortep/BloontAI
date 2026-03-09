<script setup>
import Header from './components/Header.vue'
import { useModeloAudio } from './composables/ModeloAudio.js'

const {
  users, phase, RECORD_SECONDS,
  trainRunning, trainMsg, trainPct, trainDone, trainAccuracy,
  predicting, predictResult, predictConf, predictRecording,
  probUsers, probData, logLines, continuousListening, canTrain,
  addUser, removeUser, recordAudio, recordMultiple,
  trainModel, toggleListening, resetAll,
} = useModeloAudio()
</script>

<template>
  <Header />
  <div class="app">

    <!-- Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Layout de flujo Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ -->
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
              placeholder="Nombre del usuarioÃ¢â‚¬Â¦"
              :disabled="phase !== 'capture'"
            />
            <button
              v-if="users.length > 2 && phase === 'capture'"
              class="btn-icon remove"
              @click="removeUser(idx)"
              title="Eliminar usuario"
            >Ã¢Å“â€¢</button>
          </div>

          <!-- Indicador de grabaciÃƒÂ³n -->
          <div class="mic-area" :class="{ active: user.recording }">
            <div class="mic-icon">Ã°Å¸Å½Â¤</div>
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
              Ã°Å¸Å½Â¤ Grabar 1 audio
            </button>
            <button
              class="btn btn-info"
              :disabled="user.recording || phase !== 'capture'"
              @click="recordMultiple(user, 3)"
            >
              Ã°Å¸â€Â Grabar 3 audios
            </button>
          </div>

          <!-- Mensaje de estado -->
          <div v-if="user.recordMsg" class="rec-msg" :style="{ color: user.color }">
            {{ user.recordMsg }}
          </div>

          <!-- Contador -->
          <div class="audio-count" :style="{ color: user.color }">
            {{ user.audioCount }} audios
            <span v-if="user.audioCount >= 3" style="color:#86efac"> Ã¢Å“â€œ</span>
            <span v-else style="color:#888"> (mÃƒÂ­n. 3)</span>
          </div>
        </div>

        <!-- BotÃƒÂ³n aÃƒÂ±adir usuario -->
        <button
          v-if="phase === 'capture'"
          class="btn btn-ghost add-user-btn"
          @click="addUser"
        >+ AÃƒÂ±adir usuario</button>
      </div>

      <!-- Conector izquierda Ã¢â€ â€™ centro -->
      <div class="connector">
        <div class="connector-line"></div>
        <div class="connector-arrow">Ã¢â€“Â¶</div>
      </div>

      <!-- COLUMNA CENTRAL: entrenamiento -->
      <div class="center-card">
        <div class="center-card-title">Ã°Å¸Â§Â  Entrenamiento</div>

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
          >Ã°Å¸Å¡â‚¬ Entrenar modelo</button>
          <p v-if="!canTrain" class="hint-warn">Necesitas Ã¢â€°Â¥ 2 usuarios con Ã¢â€°Â¥ 3 audios cada uno.</p>
        </div>

        <div v-else class="train-progress-block">
          <div class="big-pct" :class="{ done: trainDone }">{{ trainPct }}%</div>
          <div class="pbar"><div class="pfill accent" :style="{ width: trainPct + '%' }"></div></div>
          <p class="train-msg">{{ trainMsg }}</p>

          <div v-if="trainDone" class="accuracy-badge">
            Ã¢Å“â€¦ PrecisiÃƒÂ³n: <strong>{{ (trainAccuracy * 100).toFixed(1) }}%</strong>
          </div>
        </div>
      </div>

      <!-- Conector centro Ã¢â€ â€™ derecha -->
      <div class="connector" :class="{ dimmed: !trainDone }">
        <div class="connector-line"></div>
        <div class="connector-arrow">Ã¢â€“Â¶</div>
      </div>

      <!-- COLUMNA DERECHA: predicciÃƒÂ³n -->
      <div class="result-card" :class="{ dimmed: !trainDone }">
        <div class="center-card-title">Ã°Å¸Å½â„¢Ã¯Â¸Â Ã‚Â¿QuiÃƒÂ©n habla?</div>

        <div v-if="!trainDone" class="result-waiting">
          <span>Entrena el modelo primero</span>
        </div>

        <template v-else>
          <!-- ÃƒÂrea de predicciÃƒÂ³n -->
          <div class="predict-mic-area" :class="{ active: predictRecording }">
            <div class="predict-mic-icon">Ã°Å¸Å½Â¤</div>
            <div v-if="predictRecording" class="rec-pulse big"></div>
          </div>

          <!-- Resultado -->
          <div v-if="predicting" class="predict-result-box">
            <span class="pred-label">{{ predictResult }}</span>
            <span v-if="predictConf" class="pred-conf">{{ predictConf }}</span>
          </div>

          <!-- BotÃƒÂ³n escucha continua -->
          <div class="card-actions" style="justify-content:center; margin-top:0.8rem">
            <button
              class="btn"
              :class="continuousListening ? 'btn-danger' : 'btn-primary'"
              @click="toggleListening"
            >
              {{ continuousListening ? 'Ã¢ÂÂ¹ Apagar escucha' : 'Ã°Å¸Å½Â¤ Escuchar' }}
            </button>
          </div>
          <p v-if="continuousListening" class="hint" style="text-align:center;margin-top:0.3rem;color:#86efac;font-size:0.8rem">
            Escucha continua activa Ã‚Â· graba cada {{ RECORD_SECONDS }}s
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

<style scoped src="./styles/ModeloAudio.css">
</style>
