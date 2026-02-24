<template>
    <div v-for="modelo in modelos" :key="modelo.id" id="container"> 
        <div id="modelo">
            <p>{{ modelo.nombre }}</p>
            <input type="file" id="archivo">
        </div>
    </div>
</template>

<script setup>
import { ref } from 'vue';
const modelos = ref([
    { id: 1, nombre: "audio" },
    { id: 2, nombre: "video" },
    { id: 3, nombre: "imagen" },
]);

</script>

<style>
#container {
    display: flex;
    justify-content: space-around;
    align-items: center;
    background-color: cyan;
}

#modelo {
    height: 100%;
    width: 100%;
    background-color: blue;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: flex-start;
}
</style>