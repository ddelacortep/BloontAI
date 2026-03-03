# Diseño: Exportación del modelo entrenado

**Fecha**: 2026-03-03
**Rama**: modelo-imagenes
**Estado**: Aprobado

## Problema

El modelo entrenado via Transfer Learning (MobileNetV2 + cabeza personalizada) vive solo en RAM del servidor FastAPI. Al reiniciar el servidor, el modelo se pierde. No hay forma de reutilizarlo en otro contexto.

## Objetivo

Permitir al usuario descargar el modelo entrenado en dos formatos:
- **TensorFlow.js** — para usarlo en el browser sin backend
- **Keras H5** — para cargarlo en otro script/servidor Python

## Enfoque elegido: ZIP único con ambos formatos

Un solo endpoint `GET /export` que genera y devuelve un ZIP con:

```
modelo_exportado.zip
├── tfjs/
│   ├── model.json
│   └── group1-shard1of1.bin
├── keras/
│   └── model.h5
├── class_names.json
├── uso_javascript.html
└── uso_python.py
```

## Arquitectura

### Backend — `GET /export`

1. Verificar `state.model is not None` → 400 si no hay modelo entrenado
2. Crear directorio temporal con `tempfile.mkdtemp()`
3. Guardar Keras H5: `model.save(temp/keras/model.h5)`
4. Convertir a TF.js: `tensorflowjs.converters.save_keras_model(model, temp/tfjs/)`
5. Serializar class_names como JSON
6. Generar `uso_javascript.html` y `uso_python.py` como strings
7. Empaquetar todo en `io.BytesIO` como ZIP
8. Retornar `StreamingResponse` con Content-Disposition attachment
9. Limpiar directorio temporal en `finally`

### Frontend — botón "Exportar modelo"

- Visible solo cuando `isTrainingComplete === true`
- Estado `isExporting: ref(false)` para feedback visual
- `fetch('/api/export')` → `blob()` → descarga via `<a>` temporal
- Ubicación: panel central de entrenamiento, debajo del accuracy badge

## Incongruencias resueltas

| Riesgo | Resolución |
|---|---|
| Incompatibilidad TF vs tensorflowjs | Usar API Python `save_keras_model()` en lugar del CLI |
| BatchNorm en TF.js | TF.js maneja BN en modo inferencia correctamente al cargar LayersModel |
| CORS al cargar model.json desde `file://` | HTML de ejemplo incluye instrucción `python -m http.server` |
| Botón activo antes de modelo listo | Solo aparece cuando `isTrainingComplete === true` |
| ZIP grande (~14MB) | Botón muestra estado "Exportando..." durante la generación |
| Temp dir cleanup | `shutil.rmtree()` en bloque `finally` |

## Dependencias nuevas

- `tensorflowjs` (pip) — conversión Keras → TF.js

## Archivos a modificar

- `backend/Modelos/modeloImagenes.py` — agregar endpoint `GET /export`
- `frontend/src/views/ModeloImagenes.vue` — agregar botón y función `exportModel()`

## Archivos a crear

- Ninguno (los archivos de ejemplo se generan dinámicamente en el endpoint)
