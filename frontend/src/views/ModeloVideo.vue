<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import Header from './components/Header.vue'
import Botones from './components/Botones.vue'

const router = useRouter()

// Estado del video
const videoFile = ref(null)
const videoPreview = ref(null)
const isProcessing = ref(false)
const processingProgress = ref(0)
const processingMsg = ref('')
const resultVideo = ref(null)

// Funciones
function handleVideoUpload(event) {
  const file = event.target.files[0]
  if (file && file.type.startsWith('video/')) {
    videoFile.value = file
    videoPreview.value = URL.createObjectURL(file)
  }
}

function removeVideo() {
  videoFile.value = null
  videoPreview.value = null
}

async function startTraining() {
  if (!videoFile.value) {
    alert('Por favor, sube un video primero')
    return
  }
  
  isProcessing.value = true
  processingProgress.value = 0
  processingMsg.value = 'Analizando video...'
  
  // Simulación de progreso (aquí iría la lógica real)
  // TODO: Implementar conexión con backend
}

function downloadResult() {
  // TODO: Implementar descarga del video resultado
  alert('Funcionalidad en desarrollo')
}
</script>

<template>
  <Header></Header>
  
  <div class="app">
    <!-- Barra de acciones -->
    <div class="actions-bar">
      <Botones class="btn-back" @click="router.push('/SeleccionM')">
        <p>← Volver</p>
      </Botones>
      <span class="page-title">🎮 Modelo Video - Snake IA</span>
      <div></div>
    </div>

    <!-- Contenido principal -->
    <div class="main-content">
      <!-- Panel izquierdo: Subir video -->
      <div class="panel panel-upload">
        <div class="panel-header">
          <span class="panel-icon">📹</span>
          <h2>Video de Entrenamiento</h2>
        </div>
        
        <div class="panel-body">
          <div 
            class="upload-area"
            :class="{ 'has-video': videoPreview }"
          >
            <div v-if="!videoPreview" class="upload-placeholder">
              <div class="upload-icon">🎬</div>
              <p>Arrastra un video aquí o</p>
              <label class="upload-btn">
                <input 
                  type="file" 
                  accept="video/*" 
                  @change="handleVideoUpload"
                  hidden
                >
                Seleccionar archivo
              </label>
              <span class="upload-hint">MP4, WebM, AVI (máx. 500MB)</span>
            </div>
            
            <div v-else class="video-preview">
              <video 
                :src="videoPreview" 
                controls
                class="preview-video"
              ></video>
              <button class="remove-btn" @click="removeVideo">✕</button>
            </div>
          </div>
          
          <div class="video-info" v-if="videoFile">
            <p><strong>Archivo:</strong> {{ videoFile.name }}</p>
            <p><strong>Tamaño:</strong> {{ (videoFile.size / 1024 / 1024).toFixed(2) }} MB</p>
          </div>
        </div>
      </div>

      <!-- Conector -->
      <div class="connector">
        <div class="connector-line"></div>
        <div class="connector-arrow">▶</div>
      </div>

      <!-- Panel central: Procesamiento -->
      <div class="panel panel-process">
        <div class="panel-header">
          <span class="panel-icon">🧠</span>
          <h2>Entrenamiento IA</h2>
        </div>
        
        <div class="panel-body">
          <div v-if="!isProcessing && !resultVideo" class="process-idle">
            <p class="hint">La IA aprenderá a jugar Snake analizando tu video de gameplay.</p>
            
            <div class="steps-list">
              <div class="step">
                <span class="step-num">1</span>
                <span>Sube un video jugando al Snake</span>
              </div>
              <div class="step">
                <span class="step-num">2</span>
                <span>La IA analizará tus movimientos</span>
              </div>
              <div class="step">
                <span class="step-num">3</span>
                <span>Entrenará usando tus estrategias</span>
              </div>
            </div>
            
            <Botones 
              class="btn-train"
              :class="{ disabled: !videoFile }"
              @click="startTraining"
            >
              <p>🚀 Iniciar Entrenamiento</p>
            </Botones>
          </div>
          
          <div v-if="isProcessing" class="process-running">
            <div class="progress-circle">
              <span class="progress-pct">{{ processingProgress }}%</span>
            </div>
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: processingProgress + '%' }"></div>
            </div>
            <p class="progress-msg">{{ processingMsg }}</p>
          </div>
          
          <div v-if="resultVideo" class="process-done">
            <div class="success-icon">✅</div>
            <p>¡Entrenamiento completado!</p>
          </div>
        </div>
      </div>

      <!-- Conector -->
      <div class="connector">
        <div class="connector-line"></div>
        <div class="connector-arrow">▶</div>
      </div>

      <!-- Panel derecho: Resultado -->
      <div class="panel panel-result">
        <div class="panel-header">
          <span class="panel-icon">🐍</span>
          <h2>Resultado</h2>
        </div>
        
        <div class="panel-body">
          <div class="result-area">
            <div v-if="!resultVideo" class="result-placeholder">
              <div class="result-icon">🎮</div>
              <p>Aquí aparecerá el video de la IA jugando al Snake</p>
            </div>
            
            <div v-else class="result-video">
              <video 
                :src="resultVideo" 
                controls
                class="preview-video"
              ></video>
            </div>
          </div>
          
          <Botones 
            v-if="resultVideo"
            class="btn-download"
            @click="downloadResult"
          >
            <p>📥 Descargar Video</p>
          </Botones>
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

/* ─── Barra de acciones ─────────────────────────────────────────────────── */
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

.btn-back p {
  margin: 0;
  color: white;
}

.page-title {
  font-size: 1.2rem;
  font-weight: 700;
  color: #1B512D;
}

/* ─── Contenido principal ───────────────────────────────────────────────── */
.main-content {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 0;
  padding: 2rem;
  min-height: calc(100vh - 140px);
}

/* ─── Paneles ───────────────────────────────────────────────────────────── */
.panel {
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  min-width: 320px;
  max-width: 380px;
  overflow: hidden;
}

.panel-header {
  background: linear-gradient(135deg, #1B512D 0%, #2D7A4A 100%);
  color: white;
  padding: 1rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.8rem;
}

.panel-icon {
  font-size: 1.5rem;
}

.panel-header h2 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.panel-body {
  padding: 1.5rem;
}

/* ─── Área de subida ────────────────────────────────────────────────────── */
.upload-area {
  border: 3px dashed #7FD1AE;
  border-radius: 15px;
  padding: 2rem;
  text-align: center;
  transition: all 0.3s ease;
  min-height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-area:hover {
  border-color: #1B512D;
  background: #f0fdf4;
}

.upload-area.has-video {
  border-style: solid;
  padding: 0;
}

.upload-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.8rem;
}

.upload-icon {
  font-size: 4rem;
}

.upload-placeholder p {
  margin: 0;
  color: #666;
}

.upload-btn {
  background: #7FD1AE;
  color: #1B512D;
  padding: 0.8rem 1.5rem;
  border-radius: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.upload-btn:hover {
  background: #1B512D;
  color: white;
}

.upload-hint {
  font-size: 0.8rem;
  color: #999;
}

.video-preview {
  position: relative;
  width: 100%;
  height: 100%;
}

.preview-video {
  width: 100%;
  border-radius: 12px;
}

.remove-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  background: #dc2626;
  color: white;
  border: none;
  border-radius: 50%;
  width: 30px;
  height: 30px;
  cursor: pointer;
  font-size: 1rem;
}

.video-info {
  margin-top: 1rem;
  padding: 1rem;
  background: #f0fdf4;
  border-radius: 10px;
  font-size: 0.9rem;
}

.video-info p {
  margin: 0.3rem 0;
  color: #1B512D;
}

/* ─── Conector ──────────────────────────────────────────────────────────── */
.connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 1rem;
}

.connector-line {
  width: 60px;
  height: 3px;
  background: #7FD1AE;
}

.connector-arrow {
  color: #1B512D;
  font-size: 1.5rem;
  margin-top: -0.5rem;
}

/* ─── Panel de procesamiento ────────────────────────────────────────────── */
.process-idle {
  text-align: center;
}

.hint {
  color: #666;
  font-size: 0.95rem;
  margin-bottom: 1.5rem;
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.step {
  display: flex;
  align-items: center;
  gap: 1rem;
  text-align: left;
  padding: 0.8rem;
  background: #f0fdf4;
  border-radius: 10px;
}

.step-num {
  background: #1B512D;
  color: white;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.9rem;
}

.btn-train {
  background: linear-gradient(135deg, #B1CF5F 0%, #7FD1AE 100%);
  color: #1B512D;
  padding: 1rem 2rem;
  border-radius: 15px;
  font-weight: 700;
  border: none;
  width: 100%;
}

.btn-train.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-train p {
  margin: 0;
}

/* ─── Progreso ──────────────────────────────────────────────────────────── */
.process-running {
  text-align: center;
}

.progress-circle {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: linear-gradient(135deg, #7FD1AE 0%, #B1CF5F 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1.5rem;
}

.progress-pct {
  font-size: 2rem;
  font-weight: 700;
  color: #1B512D;
}

.progress-bar {
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 1rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1B512D, #7FD1AE);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-msg {
  color: #666;
  font-size: 0.95rem;
}

/* ─── Resultado ─────────────────────────────────────────────────────────── */
.result-area {
  border: 3px dashed #7FD1AE;
  border-radius: 15px;
  min-height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.result-placeholder {
  text-align: center;
  color: #999;
}

.result-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

.result-placeholder p {
  margin: 0;
}

.process-done {
  text-align: center;
}

.success-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

.btn-download {
  background: #1B512D;
  color: white;
  padding: 1rem 2rem;
  border-radius: 15px;
  font-weight: 600;
  border: none;
  width: 100%;
  margin-top: 1rem;
}

.btn-download p {
  margin: 0;
  color: white;
}

/* ─── Responsive ────────────────────────────────────────────────────────── */
@media (max-width: 1200px) {
  .main-content {
    flex-direction: column;
    align-items: center;
  }
  
  .connector {
    transform: rotate(90deg);
    padding: 1rem 0;
  }
  
  .panel {
    max-width: 100%;
    width: 100%;
  }
}
</style>    