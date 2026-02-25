# Explicación completa del sistema de clasificación de imágenes

> **Archivo de referencia** para entender cómo funciona el modelo de Transfer Learning
> que aprende a identificar objetos a partir de fotos capturadas desde la webcam del navegador.

---

## Índice

1. [Visión general](#1-visión-general)
2. [Arquitectura del sistema](#2-arquitectura-del-sistema)
3. [Fase 1 — Captura de imágenes (Frontend)](#3-fase-1--captura-de-imágenes-frontend)
4. [Fase 2 — Entrenamiento (Backend)](#4-fase-2--entrenamiento-backend)
5. [Fase 3 — Predicción en tiempo real](#5-fase-3--predicción-en-tiempo-real)
6. [El modelo de TensorFlow en detalle](#6-el-modelo-de-tensorflow-en-detalle)
7. [Incongruencias y notas importantes](#7-incongruencias-y-notas-importantes)
8. [Diagrama de flujo completo](#8-diagrama-de-flujo-completo)

---

## 1. Visión general

El sistema permite entrenar un clasificador de imágenes personalizado **sin escribir una sola
línea de código**, directamente desde el navegador:

1. El usuario apunta su cámara web a diferentes objetos y etiqueta cada uno con un nombre (clase).
2. El frontend captura fotogramas y los envía al backend.
3. El backend entrena un modelo de red neuronal usando **Transfer Learning** sobre MobileNetV2
   (una red ya entrenada con millones de imágenes de ImageNet).
4. Una vez entrenado, el modelo reconoce objetos en tiempo real a 600 ms/fotograma.

**Todo el estado vive exclusivamente en RAM.** Al reiniciar el servidor FastAPI desaparecen
las imágenes y el modelo entrenado.

---

## 2. Arquitectura del sistema

```
┌──────────────────────────────────────┐      HTTP/JSON
│  FRONTEND  (Vue 3 + Vite)            │  ─────────────►  ┌─────────────────────────────────┐
│  ModeloImagenes.vue                  │                   │  BACKEND  (FastAPI + TensorFlow) │
│                                      │  ◄─────────────   │  modeloImagenes.py               │
│  • Gestiona webcam con getUserMedia  │                   │                                  │
│  • Recorta/escala frame a 224×224    │                   │  • /upload  guarda imagen en RAM │
│  • Convierte a JPEG base64           │                   │  • /train   entrena el modelo    │
│  • Muestra overlay con predicción    │                   │  • /predict devuelve clase+prob  │
└──────────────────────────────────────┘                   │  • /reset   limpia la memoria    │
                                                           └─────────────────────────────────┘
```

### Proxy Vite

El frontend llama a `/api/upload`, `/api/train`, etc.
Vite intercepta esas rutas y las reescribe eliminando el prefijo `/api`,
redirigiendo la petición al backend en `http://localhost:8000`:

```
/api/upload  ──rewrite──►  http://localhost:8000/upload
/api/train   ──rewrite──►  http://localhost:8000/train
/api/predict ──rewrite──►  http://localhost:8000/predict
/api/reset   ──rewrite──►  http://localhost:8000/reset
```

Configurado en `frontend/vite.config.js`:

```js
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ''),
    },
  },
},
```

---

## 3. Fase 1 — Captura de imágenes (Frontend)

### 3.1 Estructura de clases

La interfaz arranca con **dos clases vacías**. Cada clase tiene:

| Propiedad     | Descripción                                      |
|---------------|--------------------------------------------------|
| `name`        | Etiqueta que el usuario escribe (ej.: "gato")    |
| `imageCount`  | Imágenes ya enviadas al backend para esta clase  |
| `cameraOn`    | Si la webcam de esa tarjeta está activa          |
| `capturing`   | Si hay una captura en curso (bloquea el botón)   |

Se pueden añadir y eliminar clases dinámicamente. El sistema necesita **mínimo 2 clases**
con **mínimo 5 imágenes cada una** para habilitar el botón de entrenamiento.

### 3.2 Pipeline de captura de un fotograma

```
Webcam (1280×720)
        │
        ▼
  <video> element en el DOM (srcObject = MediaStream)
        │
        ▼
  frameToBase64(videoEl)
        │  1. Crea un <canvas> de 224×224
        │  2. Calcula el cuadrado central del frame:
        │       size = Math.min(videoWidth, videoHeight)
        │     y dibuja solo ese cuadrado estirado a 224×224
        │     (recorte centrado → elimina las franjas negras laterales)
        │  3. canvas.toDataURL('image/jpeg', 0.85)
        │  4. Elimina el prefijo "data:image/jpeg;base64," → queda solo el base64
        │
        ▼
  String base64 JPEG 224×224
```

### 3.3 Envío al backend (POST /upload)

La función `captureImages(cls)` hace un bucle de **N = 15 iteraciones**,
con 150 ms de pausa entre cada una, enviando cada fotograma como:

```json
{
  "label": "nombre_de_la_clase",
  "image_b64": "<base64 del JPEG>"
}
```

El backend responde con el conteo actualizado. El frontend incrementa `cls.imageCount`.

---

## 4. Fase 2 — Entrenamiento (Backend)

### 4.1 Almacenamiento en memoria

Las imágenes NO se guardan en disco. El objeto `AppState` mantiene:

```python
state.image_data = defaultdict(list)
# Ejemplo tras capturar:
# {
#   "gato":  [array(224,224,3, uint8), array(224,224,3, uint8), ...],
#   "perro": [array(224,224,3, uint8), ...]
# }
```

Cuando llega una imagen por `/upload`:
1. Se decodifica el base64 → PIL Image → RGB.
2. Se redimensiona a 224×224 con PIL (redundante, ya llega a ese tamaño, pero inofensivo).
3. Se convierte a `numpy uint8` y se guarda en `state.image_data[label]`.

El preprocesado específico de MobileNetV2 (normalizar a rango [-1, 1]) se aplica
**más tarde**, justo antes de entrenar, para evitar operaciones de TensorFlow costosas
durante la captura.

### 4.2 Construcción del dataset

Al recibir POST /train, la función `build_dataset_from_memory()`:

1. Ordena alfabéticamente las clases con al menos 1 imagen → `class_names = ["gato", "perro"]`.
2. Para cada clase, convierte cada array `uint8` a `float32` con `preprocess_input`:
   ```
   pixel_nuevo = (pixel_original / 127.5) - 1.0   → rango [-1, 1]
   ```
3. Construye dos arrays numpy:
   - `X` de forma `(N_total, 224, 224, 3)` en float32.
   - `y` de forma `(N_total,)` con el índice entero de cada clase.
4. Baraja aleatoriamente con `np.random.permutation`.

### 4.3 Entrenamiento del modelo

```python
model.fit(
    X, y,
    epochs=20,
    batch_size=16,
    validation_split=0.2,   # 80% entreno, 20% validación
    callbacks=[
        EarlyStopping(patience=5, monitor='val_accuracy', restore_best_weights=True),
        ReduceLROnPlateau(factor=0.5, patience=3),
    ]
)
```

- **`validation_split=0.2`**: el último 20% del array (ya barajado) se usa para medir
  el rendimiento en datos no vistos.
- **EarlyStopping**: si la precisión de validación no mejora en 5 épocas seguidas,
  para el entrenamiento y restaura los pesos de la mejor época.
- **ReduceLROnPlateau**: si no mejora en 3 épocas, divide el learning rate entre 2
  (útil para salir de mesetas de aprendizaje).

---

## 5. Fase 3 — Predicción en tiempo real

Una vez entrenado el modelo, el frontend abre una segunda webcam
(independiente de las de captura) y cada **600 ms** ejecuta:

```
Webcam → frameToBase64 → POST /api/predict → { label, confidence, probabilities }
```

El backend:
1. Convierte la imagen recibida al mismo formato que en training (float32, [-1,1]).
2. Pasa el tensor por el modelo: `model.predict(tensor)` → vector de probabilidades.
3. Devuelve la clase con mayor probabilidad y todas las probabilidades.

El frontend muestra en el overlay del vídeo:
- **Etiqueta predicha** (ej.: `gato`)
- **Confianza** en porcentaje (ej.: `94%`)
- **Barras de probabilidad** para todas las clases en tiempo real
- **Log** con las últimas 25 predicciones con timestamp

---

## 6. El modelo de TensorFlow en detalle

### 6.1 Qué es Transfer Learning

En lugar de entrenar una red neuronal desde cero (lo que requeriría miles de imágenes
y mucho tiempo), el sistema parte de **MobileNetV2**, una red que ya sabe extraer
características visuales de imágenes (bordes, texturas, formas, objetos) gracias
a haber sido entrenada con 1,4 millones de imágenes de ImageNet.

Se reusan esas "habilidades visuales" y solo se entrena una pequeña cabeza clasificadora
propia encima.

### 6.2 Arquitectura completa

```
Input (224, 224, 3)  ← imagen RGB normalizada a [-1, 1]
        │
        ▼
MobileNetV2 (base)
  ├─ Pesos: ImageNet (1000 clases entrenadas)
  ├─ include_top=False → NO incluye la capa final de ImageNet
  └─ Salida: tensor de forma (7, 7, 1280)   ← mapa de características
        │
        ▼
GlobalAveragePooling2D
  └─ Promedia espacialmente → vector de 1280 números
        │
        ▼
Dropout(0.3)          ← regularización: apaga el 30% de neuronas al azar en training
        │
        ▼
Dense(128, activation='relu')   ← capa de aprendizaje personalizado
        │
        ▼
Dropout(0.2)          ← regularización adicional
        │
        ▼
Dense(num_classes, activation='softmax')
  └─ Salida: vector de probabilidades que suman 1.0
             ej.: [0.92, 0.08] para [gato, perro]
```

### 6.3 Estrategia de entrenamiento en dos etapas

**Etapa 1 — Solo la cabeza (primeras épocas)**

Al construir el modelo, `base.trainable = False`: todos los pesos de MobileNetV2
están congelados. Solo se actualizan los pesos de `Dense(128)` y `Dense(num_classes)`.

**Etapa 2 — Fine-tuning (con `fine_tune=True`)**

Inmediatamente después, `base.trainable = True` pero se re-congelan todas las capas
**excepto las últimas 30** de MobileNetV2:

```python
for layer in base.layers[:-30]:
    layer.trainable = False
# Las últimas 30 capas quedan entrenables
```

Las últimas capas de MobileNetV2 aprenden características de alto nivel
(formas complejas, partes de objetos). Descongelarlas permite que se adapten
a los objetos específicos del usuario. Las primeras capas (detectores de bordes
y texturas básicas) permanecen congeladas porque son universales y no necesitan cambiar.

**Nota técnica importante**: aunque las últimas 30 capas se descongelan,
el backbone siempre se llama con `training=False`:

```python
x = base(inputs, training=False)
```

Esto congela las estadísticas de las capas **Batch Normalization** (media y varianza
aprendidas en ImageNet) incluso durante el fine-tuning. Con datasets pequeños
(15 imágenes × pocas clases) esto es la práctica **recomendada por TensorFlow**
para evitar que las BN stats se corrompan con muestras insuficientes.

### 6.4 Función de pérdida y optimizador

| Parámetro          | Valor                             | Por qué                                               |
|--------------------|-----------------------------------|-------------------------------------------------------|
| Optimizador        | Adam (lr = 1e-4)                  | Tasa de aprendizaje baja para no destruir pesos pre-entrenados |
| Loss               | sparse_categorical_crossentropy   | Para clasificación multiclase con etiquetas enteras   |
| Métrica            | accuracy                          | Porcentaje de predicciones correctas                  |

### 6.5 Preprocesado MobileNetV2

MobileNetV2 fue entrenada con píxeles en rango **[-1, 1]**, no [0, 255]:

```
pixel_normalizado = (pixel_uint8 / 127.5) - 1.0
```

Si se alimentara la red con píxeles en [0, 255] las activaciones serían completamente
incorrectas y el modelo no funcionaría. La función `preprocess_input` de Keras
aplica esta transformación automáticamente.

---

## 7. Incongruencias y notas importantes

### ✅ Funcionalmente correcto

| Elemento                | Análisis                                                                                |
|-------------------------|-----------------------------------------------------------------------------------------|
| Proxy Vite `/api`       | Correctamente configurado con rewrite                                                   |
| Pipeline base64         | Frontend envía solo el string b64 (sin prefijo), backend lo maneja en ambos casos       |
| Preprocesado MobileNetV2| Aplicado consistentemente en upload→train y en predict                                  |
| EarlyStopping           | Restaura los mejores pesos automáticamente                                               |
| `training=False` en BN  | Comportamiento recomendado para fine-tuning con pocos datos                              |

### ⚠️ Incongruencias encontradas

#### 1. El estado `'predict'` de `phase` es código muerto

```js
// Declarado como posible valor:
// 'capture' | 'training' | 'predict'
const phase = ref('capture')

// En trainModel(), phase jamás se asigna a 'predict':
async function trainModel() {
  phase.value = 'training'
  // ... nunca: phase.value = 'predict'
}
```

La columna derecha de resultados se activa con `trainDone`, no con `phase === 'predict'`.
El estado `predict` existe en la documentación del código pero **nunca se activa**.
No rompre nada, pero el código insinúa una lógica que no está implementada.

**Corrección sugerida**: añadir `phase.value = 'predict'` al final de `trainModel()`
cuando el entrenamiento tenga éxito, o eliminar `predict` de los valores posibles.

#### 2. `resetAll()` no tiene botón en el template principal

La función `resetAll()` está implementada completa y correcta, pero no hay ningún
`@click="resetAll"` en el template de `ModeloImagenes.vue`. Si no está en `Header.vue`,
el usuario no puede reiniciar la sesión sin recargar la página.

**Corrección sugerida**: añadir un botón "🔄 Reiniciar" en la interfaz.

#### 3. `resetAll()` no elimina las clases extra añadidas por el usuario

```js
async function resetAll() {
  // ...
  classes.forEach(c => { c.imageCount = 0; c.cameraOn = false; c.name = '' })
  // ❌ Si el usuario añadió una 3ª, 4ª clase... siguen ahí después del reset
}
```

Si el usuario añadió clases adicionales con "+ Añadir clase", tras el reinicio
esas tarjetas de clase vacías permanecen en pantalla.

**Corrección sugerida**: en `resetAll()`, reducir `classes` a sus 2 elementos iniciales:

```js
classes.splice(2)  // elimina todo lo que haya a partir del índice 2
```

#### 4. Doble redimensionado a 224×224 (inofensivo)

El frontend ya envía la imagen a 224×224 px. El backend llama igualmente
a `img.resize((224, 224))`. El resultado es el mismo, pero supone un paso
de procesado innecesario.

**Impacto**: ninguno en la calidad. Latencia mínimamente mayor en cada upload.

---

## 8. Diagrama de flujo completo

```
USUARIO
  │
  ├─ [1] Escribe nombre de clase (ej.: "gato")
  │
  ├─ [2] Activa cámara  →  MediaStream → <video>
  │
  ├─ [3] Pulsa "Capturar 15"
  │         │
  │         └─ × 15 veces (cada 150ms):
  │              frame → canvas 224×224 → JPEG base64
  │              POST /api/upload { label, image_b64 }
  │              Backend: base64 → PIL → uint8 numpy → RAM
  │
  ├─ [4] Repite pasos 1-3 para cada clase (mín. 2 clases, mín. 5 imgs/clase)
  │
  ├─ [5] Pulsa "Entrenar modelo"
  │         │
  │         └─ POST /api/train { epochs: 20, fine_tune: true }
  │              Backend:
  │                1. uint8 arrays → preprocess_input (float32, [-1,1])
  │                2. Construye MobileNetV2 + cabeza personalizada
  │                3. Fase 1: entrena solo la cabeza (base congelada)
  │                4. Fase 2: fine-tune últimas 30 capas de MobileNetV2
  │                5. EarlyStopping + ReduceLROnPlateau
  │                6. Guarda model + class_names en RAM
  │              Respuesta: { val_accuracy, epochs_run, classes }
  │
  └─ [6] Modelo entrenado → panel de predicción activo
           │
           └─ Activa segunda cámara
                │
                └─ Cada 600ms:
                     frame → canvas 224×224 → JPEG base64
                     POST /api/predict { image_b64 }
                     Backend:
                       base64 → PIL → uint8 → float32 [-1,1]
                       model.predict() → [0.94, 0.06]
                       argmax → "gato", confidence: 0.94
                     Frontend: label + barra de confianza + log
```

---

*Documento generado el 25 de febrero de 2026 para el proyecto BloontAI.*
