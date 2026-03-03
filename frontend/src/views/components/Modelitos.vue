<template>
    <div id="container">
        <div v-for="modelo in modelos" :key="modelo.id" class="modelo">
            <p>{{ modelo.nombre }}</p>
            <RegexpFileInput :tipo="modelo.tipo"
                :accept="modelo.tipo === 'audio' ? '.mp3' : modelo.tipo === 'video' ? '.mp4' : '.jpg'"
                :regexp="modelo.tipo === 'audio' ? regexpAudio : modelo.tipo === 'video' ? regexpVideo : regexpImagen"
                @file-selected="handleFileSelected" />
            <div v-if="archivos[modelo.tipo]" class="archivo-info">
                <span>{{ archivos[modelo.tipo].name }}</span>
                <button @click="deleteFile(modelo.tipo)" class="btn-eliminar">Eliminar</button>
            </div>
                        <button
                            v-if="modelo.tipo === 'imagen'"
                            class="modelo-btn"
                            @click="generarImagen"
                        >Generar Imagen</button>
                        <button
                            v-else
                            class="modelo-btn"
                            disabled
                        >Generar {{modelo.nombre}}</button>
            <div v-if="errorArchivo" class="error-archivo">
                {{ errorArchivo }}
            </div>
            <button @click="generarImagen" class="modelo-btn">Generar Imagen</button>
        </div>
    </div>
</template>

<script setup>
import { ref, reactive } from 'vue';
import RegexpFileInput from './RegexpFileInput.vue';

const modelos = ref([
    { id: 1, nombre: "Audio", tipo: "audio"},
    { id: 2, nombre: "Video", tipo: "video"},
    { id: 3, nombre: "Imagen", tipo: "imagen" },
]);

const regexpAudio = /\.mp3$/i;
const regexpVideo = /\.mp4$/i;
const regexpImagen = /\.jpg$/i;

const emit = defineEmits(['file-selected']);

const archivos = reactive({ audio: null, video: null, imagen: null });

function handleFileSelected({ tipo, file }) {
    archivos[tipo] = file;
    emit('file-selected', { tipo, file });
}

function deleteFile(tipo) {
    archivos[tipo] = null;
    emit('file-selected', { tipo, file: null });
}

async function generarImagen() {
    const file = archivos['imagen'];
    if (!file) return;
    const formData = new FormData();
    formData.append('imagen', file);
    try {
        const response = await fetch('/api-texto/imagen-a-texto', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (data.caption) {
            alert('Descripción generada: ' + data.caption);
        } else if (data.error) {
            alert('Error: ' + data.error);
        }
    } catch (err) {
        alert('Error de conexión con el backend');
    }
}
</script>

<style>
body {
    font-family: 'Montserrat';
}

#container {
    display: flex;
    justify-content: center;
    align-items: stretch;
    gap: 32px;
    padding: 40px 0;
}

.modelo {
    flex: 1 1 0;
    max-width: 320px;
    min-width: 220px;
    background: linear-gradient(135deg, #274472 0%, #406999 100%);
    color: #f3f6fa;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    border-radius: 18px;
    box-shadow: 0 4px 16px 0 rgba(30, 40, 60, 0.18);
    padding: 32px 20px 24px 20px;
    transition: box-shadow 0.2s, transform 0.2s;
    border: 1.5px solid #183153;
    min-height: 400px;
}

.modelo:hover {
    box-shadow: 0 8px 24px 0 rgba(30, 40, 60, 0.28);
    transform: translateY(-4px) scale(1.03);
}

.modelo p {
    font-size: 1.3rem;
    font-weight: 600;
    margin-bottom: 18px;
    color: #90caf9;
    letter-spacing: 0.5px;
}

.archivo {
    margin-top: 16px;
}
.archivo-info {
    margin-top: 12px;
    display: flex;
    align-items: center;
    gap: 10px;
    background: #fff2;
    border-radius: 6px;
    padding: 6px 10px;
}
.btn-eliminar {
    background: #d32f2f;
    color: #fff;
    border: none;
    border-radius: 4px;
    padding: 2px 8px;
    cursor: pointer;
    font-size: 0.95rem;
    font-weight: 500;
    transition: background 0.2s;
}
.btn-eliminar:hover {
    background: #b71c1c;
}
.modelo-btn {
    width: 100%;
    background: #1976d2;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 10px 0;
    font-size: 1rem;
    font-weight: 600;
    margin-top: 24px;
    cursor: pointer;
    transition: background 0.2s;
}
.modelo-btn:hover {
    background: #1565c0;
}
.error-archivo {
    color: #fff;
    background: #d32f2f;
    padding: 12px;
    border-radius: 6px;
    margin-bottom: 16px;
    font-weight: bold;
    width: 100%;
    text-align: center;
}

.modelo-btn {
    width: 100%;
    background: #1976d2;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 10px 0;
    font-size: 1rem;
    font-weight: 600;
    margin-top: 18px;
    cursor: pointer;
    transition: background 0.2s;
}
.modelo-btn:hover {
    background: #1565c0;
}
</style>