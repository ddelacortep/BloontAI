<template>
    <div id="container">
        <div id="izquierda">
            <h1 style="font-family: Montserrat;">BloontAI</h1>
        </div>
        <div id="derecha">
            <Botones v-for="item in header" :key="item.id" :class="item.class" @click="$emit(item.link)">
                <p>{{ item.label }}</p>
            </Botones>
        </div>
    </div>

</template>

<script setup>
import Botones from './Botones.vue';

const header = [
    {
        id: 2, label: 'FAQs', link: '#faqs', class: 'faqs'
    },
    {

        id: 1, label: 'Primeros Pasos', link: '#primerosPasos', class: 'primerosPasos'
    },
]
</script>

<style>
#container {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px;
}

#derecha {
    display: flex;
    gap: 150px;
}

#izquierda {
    display: flex;
    align-items: center;
    text-align: center;
    justify-content: center;
    background-color: #B1CF5F;
    border-radius: 30px;
    width: 12vw;
    height: 8vh;
}


.faqs {
    background-color: transparent;
    border-color: transparent;
    color: black;
    font-family: "Montserrat";
}

.primerosPasos {
    background-color: #1B512D;
    border-color: transparent;
    color: white;
    font-family: "Montserrat";
    border-radius: 30px;
}

.menu {
    background-color: transparent;
    border-color: transparent;
    color: black;
}
</style>
