<template>
    <button class="button">
        <slot></slot>
    </button>
    
</template>

<script setup>
</script>

<style> 
.button {
    cursor: pointer;
    transition: all 0.3s ease;
}

.button:hover {
    transform: translateY(-2px);
    filter: brightness(1.1);
}

.button:active {
    transform: translateY(0);
}
</style>    