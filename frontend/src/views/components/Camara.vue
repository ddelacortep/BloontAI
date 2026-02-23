<template>
    <div id="webcam-container">
        <video ref="video" autoplay playsinline></video>
    </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from "vue";

const video = ref(null);

const startWebcam = async () => {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (video.value) {
            video.value.srcObject = stream;
        }
    } catch (error) {
        console.error("Error al acceder a la webcam:", error);
    }
};

const stopWebcam = () => {
    if (video.value && video.value.srcObject) {
        const stream = video.value.srcObject;
        const tracks = stream.getTracks();
        tracks.forEach((track) => track.stop());
    }
};

onMounted(() => {
    startWebcam();
});

onBeforeUnmount(() => {
    stopWebcam();
});
</script>

<style>
#webcam-container {
    width: 400px;
    height: 300px;
    border: 5px solid #1b512d;
    border-radius: 15px;
    display: flex;
    justify-content: center;
    align-items: center;
    background-color: #f0f0f0;
    overflow: hidden;
}

video {
    width: 100%;
    height: 100%;
    object-fit: cover;
}
</style>
