# Plan de Refactorización: ModeloImagenes.vue

## Objetivo
Separar la lógica (JavaScript) y los estilos (CSS) del archivo `ModeloImagenes.vue` para mejorar la escalabilidad, legibilidad y mantenibilidad del código.

## Estructura de Archivos Propuesta

Para lograr una arquitectura escalable, se separarán las responsabilidades en tres archivos distintos.

### 1. Lógica de Negocio (Composable)
**Archivo:** `src/views/composables/ModeloImagenes.js`
**Responsabilidad:** Contener toda la lógica reactiva, llamadas a la API y gestión del estado.
**Contenido:**
- Definición de constantes (`API`, `PALETTE`, etc.).
- Estado reactivo (`classes`, `appPhase`, `isTraining`, etc.).
- Funciones de manipulación (`addClass`, `captureImages`, `trainModel`).
- Hooks del ciclo de vida (`onUnmounted`).

### 2. Hoja de Estilos
**Archivo:** `src/views/styles/ModeloImagenes.css`
**Responsabilidad:** Contener todas las reglas de estilo visual.
**Contenido:**
- Todo el CSS que actualmente reside en el bloque `<style scoped>`.

### 3. Componente de Vista
**Archivo:** `src/views/ModeloImagenes.vue`
**Responsabilidad:** Estructura visual (Template) e integración.
**Contenido:**
- Importación del composable `useModeloImagenes`.
- Importación del componente `Header`.
- Template HTML.
- Referencia al archivo CSS externo.

## Pasos de Ejecución

1.  **Creación de Carpetas**:
    -   Crear `src/views/composables/` si no existe.
    -   Crear `src/views/styles/` si no existe.

2.  **Extracción de Lógica (`ModeloImagenes.js`)**:
    -   Crear el archivo `.js`.
    -   Importar `ref`, `reactive`, `computed`, `nextTick`, `onUnmounted` de `vue`.
    -   Exportar una función `useModeloImagenes()`.
    -   Mover todo el código del `<script setup>` dentro de esta función.
    -   **Importante**: Retornar un objeto con todas las variables y funciones que el template necesita (ej: `classes`, `canTrain`, `cameraElements`, `trainModel`, etc.).

3.  **Extracción de Estilos (`ModeloImagenes.css`)**:
    -   Crear el archivo `.css`.
    -   Mover el contenido de `<style scoped>` a este archivo.

4.  **Refactorización del Componente (`ModeloImagenes.vue`)**:
    -   Limpiar `<script setup>`.
    -   Importar `useModeloImagenes` desde la ruta relativa correcta.
    -   Instanciar el composable: `const { ... } = ModeloImagenes()`.
    -   Modificar la etiqueta style: `<style scoped src="./styles/ModeloImagenes.css"></style>`.

## Verificación de Integridad (Checklist de Errores Comunes)
-   [ ] **Reactividad**: Asegurar que `classes` y `trainingConfig` mantengan su reactividad al pasar por el composable.
-   [ ] **Referencias al DOM**: Las variables `cameraElements` y `predictCameraEl` deben ser retornadas por el composable para que el `ref=""` del template funcione correctamente.
-   [ ] **Imports**: Verificar que `Header.vue` se importe en el `.vue` y no en el `.js`.
-   [ ] **Rutas**: Comprobar que las rutas de los imports (`../components/Header.vue`, `./styles/ModeloImagenes.css`) sean correctas tras mover los archivos.