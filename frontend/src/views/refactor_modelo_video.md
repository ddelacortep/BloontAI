# Plan de Refactorización: ModeloVideo.vue

## Objetivo
Separar la lógica de negocio (JavaScript) y los estilos (CSS) del componente `ModeloVideo.vue` en archivos dedicados. Esta refactorización mejorará la legibilidad, mantenibilidad y escalabilidad del código, siguiendo la misma arquitectura que otros componentes del proyecto.

## Estructura de Archivos Propuesta

Se propone la siguiente estructura para desacoplar las responsabilidades:

### 1. Lógica de Negocio (Composable)
**Archivo:** `src/views/composables/useSnakeModel.js`
**Responsabilidad:** Contener toda la lógica reactiva, el estado del juego, las llamadas a la API del backend de Snake y las funciones de control.
**Contenido:**
- Definición de constantes (`API`, `GRID`).
- Estado reactivo (`game`, `isTraining`, `isPlaying`, `scores`, `speed`, etc.).
- Funciones de control del entrenamiento y la visualización (`startTraining`, `runTrainingLoop`, `playOneGame`, `togglePause`, `stopTraining`).
- El hook `useRouter` para la navegación.
- El hook del ciclo de vida `onBeforeUnmount` para limpiar los procesos al salir del componente.

### 2. Hoja de Estilos
**Archivo:** `src/views/styles/ModeloVideo.css`
**Responsabilidad:** Contener todas las reglas de estilo visual para el componente `ModeloVideo.vue`.
**Contenido:**
- Todo el código CSS que actualmente se encuentra en el bloque `<style scoped>` del archivo `.vue`.

### 3. Componente de Vista
**Archivo:** `src/views/ModeloVideo.vue`
**Responsabilidad:** Actuar como la capa de presentación, mostrando la estructura visual (HTML) y conectando la lógica del composable con el template.
**Contenido:**
- Importación del composable `useSnakeModel`.
- Importación de los componentes hijos (`Header`, `Botones`, `SnakeCanvas`, `PerformanceChart`).
- El bloque `<template>` con todo el HTML.
- Un bloque `<script setup>` mínimo para instanciar el composable.
- Una referencia al archivo CSS externo en la etiqueta `<style>`.

## Pasos de Ejecución

1.  **Creación de Archivos**:
    -   Crear el archivo `src/views/composables/useSnakeModel.js`.
    -   Crear el archivo `src/views/styles/ModeloVideo.css`.
    -   Asegurarse de que las carpetas `composables` y `styles` existen dentro de `src/views/`.

2.  **Extracción de Lógica a `useSnakeModel.js`**:
    -   Importar las funciones necesarias de `vue` (`ref`, `reactive`, `onBeforeUnmount`) y `vue-router` (`useRouter`).
    -   Crear y exportar una función `export function useSnakeModel() { ... }`.
    -   Mover todo el código del bloque `<script setup>` de `ModeloVideo.vue` (excepto las importaciones de componentes) dentro de la función `useSnakeModel`.
    -   **Retornar un objeto** desde `useSnakeModel` con todas las variables y funciones que el template necesita para funcionar. Ejemplo:
        ```javascript
        return {
          router,
          game,
          isTraining,
          isPlaying,
          // ... todas las demás refs y funciones
          startTraining,
          togglePause,
          stopTraining
        };
        ```

3.  **Extracción de Estilos a `ModeloVideo.css`**:
    -   Copiar todo el contenido del bloque `<style scoped>` de `ModeloVideo.vue`.
    -   Pegar el contenido en el nuevo archivo `src/views/styles/ModeloVideo.css`.

4.  **Refactorización del Componente `ModeloVideo.vue`**:
    -   Vaciar el bloque `<style scoped>` y modificarlo para que apunte al nuevo archivo:
        ```html
        <style scoped src="./styles/ModeloVideo.css"></style>
        ```
    -   Simplificar el bloque `<script setup>` para que solo contenga las importaciones de componentes y la llamada al nuevo composable.

## Verificación de Integridad (Checklist)
-   [ ] **Reactividad**: Comprobar que todas las variables de estado (`game`, `isTraining`, `scores`, etc.) siguen siendo reactivas en el template después de moverlas al composable.
-   [ ] **Router**: Asegurarse de que la instancia de `router` se obtiene con `useRouter()` dentro del composable y se retorna para que el botón "Volver" funcione.
-   [ ] **Imports**: Verificar que las importaciones de componentes (`Header.vue`, `SnakeCanvas.vue`, etc.) permanecen en `ModeloVideo.vue` y no se mueven al archivo `.js`.
-   [ ] **Rutas de Archivos**: Confirmar que las rutas en las importaciones (`./composables/useSnakeModel.js`, `./styles/ModeloVideo.css`) son correctas desde la ubicación de `ModeloVideo.vue`.
-   [ ] **Ciclo de Vida**: Asegurarse de que el hook `onBeforeUnmount` se ha movido correctamente al composable y sigue funcionando para detener el entrenamiento al salir de la página.
