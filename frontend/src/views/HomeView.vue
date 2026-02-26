<template>
    <Header></Header>

    <div id="containerHome">
        <div id="divIzquierdo">
            <h1>Lorem ipsum dolor sit amet consectetur adipisicing elit. Quo eum omnis commodi dolor repellat, maiores voluptatum enim atque magnam inventore dolorem quam et architecto recusandae dolore officia sit reprehenderit mollitia.</h1>
            <p> Descripcion </p>
        </div>
        <div id="divDerecho">
            <img :src="abascalImg" alt="Imagen Clara">
        </div>
    </div>
</template>

<script setup>
import Header from './components/Header.vue';
import Botones from './components/Botones.vue';
import abascalImg from '@/assets/abascal.webp';
</script>

<style>
#containerHome {
    display: grid;
    grid-template-columns: 50% 50%;
    justify-content: center;
    width: 80%;
    margin: 0 auto;
}

#divIzquierdo, #divDerecho {
    margin: 10px;
    margin-top: 10vh;
}

#divDerecho img {
    max-width: 100%;
    height: auto;
    object-fit: contain;
    border-radius: 20px;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.2);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

#divDerecho img:hover {
    transform: scale(1.05);
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.3);
}

</style>