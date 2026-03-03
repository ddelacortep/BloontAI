<template>
    <Header></Header>
    <Modelitos @file-selected="onFileSelected"/>
    
</template>

<script setup>
function deleteFile(tipo) {
    if (tipo === 'audio') {
        archivoAudio.value = null;
    } else if (tipo === 'video') {
        archivoVideo.value = null;
    } else if (tipo === 'imagen') {
        archivoImagen.value = null;
    }
    errorArchivo.value = '';
}

import { ref } from 'vue';
import Header from './components/Header.vue';
import Modelitos from './components/Modelitos.vue';

const archivoAudio = ref(null);
const archivoVideo = ref(null);
const archivoImagen = ref(null);
const errorArchivo = ref('');

function onFileSelected({ tipo, file }) {
    errorArchivo.value = '';
    let valid = false;
    if (tipo === 'audio') {
        valid = file && /\.mp3$/i.test(file.name);
        if (valid) {
            archivoAudio.value = file;
        } else {
            archivoAudio.value = null;
            errorArchivo.value = 'Solo se permiten archivos .mp3 para audio.';
        }
    } else if (tipo === 'video') {
        valid = file && /\.mp4$/i.test(file.name);
        if (valid) {
            archivoVideo.value = file;
        } else {
            archivoVideo.value = null;
            errorArchivo.value = 'Solo se permiten archivos .mp4 para video.';
        }
    } else if (tipo === 'imagen') {
        valid = file && /\.jpg$/i.test(file.name);
        if (valid) {
            archivoImagen.value = file;
        } else {
            archivoImagen.value = null;
            errorArchivo.value = 'Solo se permiten archivos .jpg para imagen.';
        }
    }
    console.log('Archivo seleccionado:', tipo, file);
}

</script>

<style lang="scss" scoped>

</style>