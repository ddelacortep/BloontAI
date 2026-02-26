<template>
  <Header></Header>
  
  <div class="container-seleccion">
    <!-- Carrusel central de modelos -->
    <div class="seccion-central">      
      <div class="carrusel-container">
        <div class="controles-izquierda">
          <Botones class="boton-volver" @click="router.push('/')">
            <p>← Inicio</p>
          </Botones>
        </div>

        <div class="carrusel-modelos">
          <div 
            v-for="(modelo, index) in modelos" 
            :key="modelo.id"
            class="modelo-card"
            :class="{ 
              'modelo-seleccionado': index === modeloActivo,
              'modelo-arriba': index === modeloActivo - 1,
              'modelo-abajo': index === modeloActivo + 1,
              'modelo-oculto': Math.abs(index - modeloActivo) > 1
            }"
            @click="seleccionarModelo(index)"
          >
            <div class="modelo-contenido">
              <div class="modelo-icono">{{ modelo.icono }}</div>
              <div class="modelo-info">
                <h3>{{ modelo.nombre }}</h3>
                <p>{{ modelo.descripcion }}</p>
              </div>
            </div>
          </div>
        </div>
        
        <div class="carrusel-controles">
          <button @click="prevModel" class="carrusel-nav" :disabled="modeloActivo === 0">
            <span>▲</span>
          </button>
          <button @click="nextModel" class="carrusel-nav" :disabled="modeloActivo === modelos.length - 1">
            <span>▼</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Botones derecha -->
    <div class="seccion-derecha">
      <Botones class="boton-accion boton-ordenador" @click="subirDesdeOrdenador">
        <p>📁 Subir desde Ordenador</p>
      </Botones>
      
      <Botones class="boton-accion boton-drive" @click="subirDesdeDrive">
        <p>☁️ Subir desde Drive</p>
      </Botones>
      
      <input 
        ref="fileInput" 
        type="file" 
        accept=".json,.h5,.keras"
        style="display: none" 
        @change="handleFileUpload"
      >
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import Header from './components/Header.vue'
import Botones from './components/Botones.vue'

const router = useRouter()

// Referencia al input de archivo
const fileInput = ref(null)

// Estado del carrusel
const modeloActivo = ref(1)

// Modelos disponibles
const modelos = ref([
  {
    id: 1, 
    label: 'Audio', 
    link: '/modelo-audio', 
    class: 'modelo-audio',
    nombre: 'SeleccionAudio',
    descripcion: 'Entrena tu modelo con clases personalizadas usando audio.',
    icono: '🎤'
  },
  {
    id: 2, 
    label: 'Imagen', 
    link: '/modelo-imagenes', 
    class: 'modelo-imagenes',
    nombre: 'Imagen',
    descripcion: 'Realiza la preparación con imágenes de archivos o webcam.',
    icono: '🖼️'
  },
  {
    id: 3, 
    label: 'Video', 
    link: '/modelo-videos', 
    class: 'modelo-videos',
    nombre: 'Video',
    descripcion: 'Procesa y analiza videos desde archivos o captura.',
    icono: '🎥'
  },
  {
    id: 4, 
    label: 'Audio', 
    link: '/modelo-audio', 
    class: 'modelo-audio',
    nombre: 'Transcribir',
    descripcion: 'Convierte audio en texto con reconocimiento de voz.',
    icono: '📝'
  }
])

// Navegación del carrusel
function prevModel() {
  if (modeloActivo.value > 0) {
    modeloActivo.value--
  }
}

function nextModel() {
  if (modeloActivo.value < modelos.value.length - 1) {
    modeloActivo.value++
  }
}

function seleccionarModelo(index) {
  modeloActivo.value = index
  const modelo = modelos.value[index]
  if (modelo.link) {
    router.push(modelo.link)
  }
}

// Funciones de subida de archivos
function subirDesdeOrdenador() {
  fileInput.value?.click()
}

function handleFileUpload(event) {
  const file = event.target.files[0]
  if (file) {
    console.log('Archivo seleccionado:', file.name)
  }
}

function subirDesdeDrive() {
  alert('Funcionalidad de Google Drive en desarrollo')
}
</script>

<style scoped>
.container-seleccion {
  display: grid;
  grid-template-columns: 1fr 200px;
  gap: 40px;
  padding: 20px 60px;
  min-height: 70vh;
  align-items: start;
  max-width: 1200px;
  margin: 0 auto;
}

.boton-volver {
  background-color: #1B512D;
  border-radius: 20px;
  padding: 12px 20px;
  color: white;
  font-family: 'Montserrat', sans-serif;
  font-size: 14px;
  font-weight: 600;
  border: none;
  min-height: 45px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.boton-volver p {
  margin: 0;
  color: white;
}


.seccion-central {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.carrusel-container {
  display: flex;
  align-items: center;
  gap: 30px;
  width: 100%;
  max-width: 800px;
  position: relative;
}

.controles-izquierda {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.carrusel-modelos {
  flex: 1;
  position: relative;
  height: 550px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modelo-card {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  background: #7FD1AE;
  border-radius: 20px;
  padding: 40px 30px;
  transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  width: 85%;
  max-width: 480px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
}

.modelo-seleccionado {
  transform: translate(-50%, -50%) scale(1);
  z-index: 10;
  background: #7FD1AE;
  box-shadow: 0 8px 30px rgba(127, 209, 174, 0.35);
  height: 200px;
}

.modelo-arriba {
  transform: translate(-50%, -50%) translateY(-210px) scale(0.75);
  opacity: 0.7;
  z-index: 5;
  background: #7FD1AE;
  height: 150px;
}

.modelo-abajo {
  transform: translate(-50%, -50%) translateY(210px) scale(0.75);
  opacity: 0.7;
  z-index: 5;
  background: #7FD1AE;
  height: 150px;
}

.modelo-oculto {
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.5);
  pointer-events: none;
  z-index: 0;
}

.modelo-contenido {
  display: flex;
  align-items: center;
  gap: 25px;
  height: 100%;
}

.modelo-icono {
  font-size: 70px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: font-size 0.3s ease;
}

.modelo-arriba .modelo-icono,
.modelo-abajo .modelo-icono {
  font-size: 50px;
}

.modelo-info {
  flex: 1;
  text-align: left;
}

.modelo-card h3 {
  font-family: 'Montserrat', sans-serif;
  font-size: 26px;
  font-weight: 700;
  margin: 0 0 12px 0;
  color: #1B512D;
  transition: font-size 0.3s ease;
}

.modelo-arriba h3,
.modelo-abajo h3 {
  font-size: 20px;
  margin-bottom: 8px;
}

.modelo-card p {
  font-family: 'Montserrat', sans-serif;
  font-size: 15px;
  color: #2D5940;
  line-height: 1.5;
  margin: 0;
  transition: font-size 0.3s ease;
}

.modelo-arriba p,
.modelo-abajo p {
  font-size: 13px;
}

.carrusel-controles {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.carrusel-nav {
  background-color: #1B512D;
  color: white;
  border: none;
  border-radius: 50%;
  width: 45px;
  height: 45px;
  font-size: 18px;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.carrusel-nav:hover:not(:disabled) {
  background-color: #7FD1AE;
  transform: scale(1.1);
}

.carrusel-nav:active:not(:disabled) {
  transform: scale(0.95);
}

.carrusel-nav:disabled {
  background-color: #ccc;
  cursor: not-allowed;
  opacity: 0.5;
}

.carrusel-nav span {
  display: block;
  line-height: 1;
}


.seccion-derecha {
  display: flex;
  flex-direction: column;
  gap: 25px;
  align-items: center;
  justify-content: center;
}

.boton-accion {
  border-radius: 20px;
  padding: 18px 20px;
  font-family: 'Montserrat', sans-serif;
  font-size: 14px;
  font-weight: 600;
  border: none;
  text-align: center;
  transition: all 0.3s ease;
  width: 100%;
  min-height: 70px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.boton-ordenador {
  background-color: #B1CF5F;
  color: #1B512D;
}

.boton-drive {
  background-color: #B1CF5F;
  color: #1B512D;
}

.boton-accion p {
  margin: 0;
  line-height: 1.3;
  color: inherit;
}

.boton-accion:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
  filter: brightness(1.05);
}

.boton-accion:active {
  transform: translateY(-1px);
}


@media (max-width: 1024px) {
  .container-seleccion {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr auto;
    gap: 30px;
    padding: 30px;
  }

  .seccion-izquierda,
  .seccion-derecha {
    flex-direction: row;
    justify-content: center;
    gap: 20px;
  }

  .boton-volver,
  .boton-accion {
    max-width: 200px;
  }

  .carrusel-modelos {
    height: 450px;
  }

  .modelo-seleccionado {
    height: 180px;
  }

  .modelo-arriba,
  .modelo-abajo {
    height: 130px;
  }
}
</style>

