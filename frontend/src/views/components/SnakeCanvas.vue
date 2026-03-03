<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  game: { type: Object, required: true },
  size: { type: Number, default: 400 },
})

const canvasRef = ref(null)
let animId = null

function draw() {
  const canvas = canvasRef.value
  if (!canvas || !props.game) return
  const ctx = canvas.getContext('2d')
  const g = props.game
  const cell = props.size / g.gridSize

  ctx.fillStyle = '#0a0a0a'
  ctx.fillRect(0, 0, props.size, props.size)

  ctx.strokeStyle = 'rgba(255,255,255,0.04)'
  for (let i = 0; i <= g.gridSize; i++) {
    ctx.beginPath(); ctx.moveTo(i * cell, 0); ctx.lineTo(i * cell, props.size); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(0, i * cell); ctx.lineTo(props.size, i * cell); ctx.stroke()
  }

  g.snake.forEach((seg, idx) => {
    ctx.fillStyle = idx === 0 ? '#7FD1AE' : '#1B512D'
    const r = idx === 0 ? 6 : 4
    ctx.beginPath()
    ctx.roundRect(seg.x * cell + 1, seg.y * cell + 1, cell - 2, cell - 2, r)
    ctx.fill()
  })

  ctx.fillStyle = '#B1CF5F'
  ctx.beginPath()
  ctx.arc(g.food.x * cell + cell / 2, g.food.y * cell + cell / 2, cell / 2.5, 0, Math.PI * 2)
  ctx.fill()

  ctx.fillStyle = 'rgba(255,255,255,0.7)'
  ctx.font = 'bold 14px Montserrat, sans-serif'
  ctx.fillText(`Score: ${g.score}`, 8, 18)
}

function loop() {
  draw()
  animId = requestAnimationFrame(loop)
}

onMounted(() => loop())
onBeforeUnmount(() => { if (animId) cancelAnimationFrame(animId) })
watch(() => props.game, () => draw())
</script>

<template>
  <canvas ref="canvasRef" :width="size" :height="size" class="snake-canvas" />
</template>

<style scoped>
.snake-canvas {
  border-radius: 12px;
  display: block;
  background: #0a0a0a;
}
</style>
