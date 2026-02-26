<template>
  <div>
    <input ref="fileInput" type="file" :accept="accept" @change="onChange" />
    <div v-if="error" style="color: red; margin-top: 8px;">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue';
const props = defineProps({
  regexp: { type: RegExp, required: true },
  accept: { type: String, default: '' },
  tipo: { type: String, required: true }
});
const emit = defineEmits(['file-selected']);
const error = ref('');
const fileInput = ref(null);

function resetInput() {
  // Resetear el input file para permitir volver a subir el mismo archivo
  if (fileInput.value) {
    fileInput.value.value = '';
  }
}

function onChange(event) {
  error.value = '';
  const file = event.target.files[0];
  if (file && props.regexp.test(file.name)) {
    emit('file-selected', { tipo: props.tipo, file });
    nextTick(resetInput);
  } else {
    error.value = `Archivo inválido para ${props.tipo}`;
    emit('file-selected', { tipo: props.tipo, file: null });
    nextTick(resetInput);
  }
}
</script>

<style scoped>
input[type="file"] {
  margin-top: 16px;
}
</style>
