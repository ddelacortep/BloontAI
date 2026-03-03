<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS, Title, Tooltip, Legend,
  LineElement, PointElement, CategoryScale, LinearScale, Filler,
} from 'chart.js'

ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale, Filler)

const props = defineProps({
  scores: { type: Array, default: () => [] },
})

const chartData = computed(() => ({
  labels: props.scores.map((_, i) => i + 1),
  datasets: [{
    label: 'Puntuación por episodio',
    data: props.scores,
    borderColor: '#1B512D',
    backgroundColor: 'rgba(127, 209, 174, 0.25)',
    fill: true,
    tension: 0.3,
    pointRadius: props.scores.length > 80 ? 0 : 3,
    pointBackgroundColor: '#1B512D',
  }],
}))

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 0 },
  scales: {
    x: { title: { display: true, text: 'Episodio' } },
    y: { title: { display: true, text: 'Puntuación' }, beginAtZero: true },
  },
  plugins: { legend: { display: false } },
}
</script>

<template>
  <div class="chart-wrapper">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>

<style scoped>
.chart-wrapper { width: 100%; height: 260px; }
</style>
