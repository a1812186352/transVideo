<template>
  <div class="aw" ref="containerRef">
    <canvas
      ref="canvasRef"
      class="aw__canvas"
      @click="onCanvasClick"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';

const props = defineProps<{
  energyCurve: number[];
  duration: number;       // module duration in seconds (NOT total video duration)
  startTime?: number;     // module start offset in video (default 0)
  currentTime: number;    // global playhead position in seconds
  bpm?: number;
  moodLabels?: Array<{ at: number; label: string; color: string }>;
}>();

const emit = defineEmits<{
  seek: [time: number];
}>();

// Effective time range for this waveform
const rangeStart = computed(() => props.startTime ?? 0);
const rangeEnd = computed(() => rangeStart.value + (props.duration || 0));

const canvasRef = ref<HTMLCanvasElement | null>(null);
const containerRef = ref<HTMLDivElement | null>(null);
const WIDTH = 280;
const HEIGHT = 64;
const BAR_GAP = 2;

// Map energy_curve to bar heights (normalize to 0..1)
const bars = computed(() => {
  const raw = props.energyCurve || [];
  if (!raw.length) return new Array(20).fill(0.02);
  const max = Math.max(...raw, 0.01);
  return raw.map(v => Math.max(0.02, v / max));
});

function draw() {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // HiDPI
  const dpr = window.devicePixelRatio || 1;
  const w = WIDTH * dpr;
  const h = HEIGHT * dpr;
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
    canvas.style.width = WIDTH + 'px';
    canvas.style.height = HEIGHT + 'px';
  }
  ctx.scale(dpr, dpr);

  // Clear
  ctx.clearRect(0, 0, WIDTH, HEIGHT);

  const data = bars.value;
  const count = data.length;
  if (!count) return;

  const barW = Math.max(2, (WIDTH - (count - 1) * BAR_GAP) / count);
  const totalW = count * barW + (count - 1) * BAR_GAP;
  const offsetX = (WIDTH - totalW) / 2;

  // — Draw bars —
  for (let i = 0; i < count; i++) {
    const hVal = data[i] * (HEIGHT - 8);
    const x = offsetX + i * (barW + BAR_GAP);
    const y = HEIGHT / 2 - hVal / 2;

    // Color: low → light muted, high → accent
    const t = data[i];
    const r = Math.round(30 + t * 190);
    const g = Math.round(40 + t * 160);
    const b = Math.round(60 + t * 200);
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(x, y, barW, hVal);
  }

  // — Mood label zones (offset by module start_time) —
  if (props.moodLabels?.length && props.duration > 0) {
    for (const mood of props.moodLabels) {
      const localAt = mood.at - rangeStart.value;
      if (localAt < 0 || localAt > props.duration) continue;
      const x = (localAt / props.duration) * WIDTH;
      ctx.fillStyle = mood.color + '22'; // very transparent
      ctx.fillRect(x - 1, 0, 4, HEIGHT);
    }
  }

  // — Playhead (offset by module start_time) —
  if (props.duration > 0 && props.currentTime >= 0) {
    const localTime = props.currentTime - rangeStart.value;
    const inRange = localTime >= -0.05 && localTime <= props.duration + 0.05;
    if (inRange) {
      const px = (Math.max(0, Math.min(localTime, props.duration)) / props.duration) * WIDTH;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(px, 0);
      ctx.lineTo(px, HEIGHT);
      ctx.stroke();

      // Playhead triangle
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      ctx.moveTo(px - 4, 0);
      ctx.lineTo(px + 4, 0);
      ctx.lineTo(px, 5);
      ctx.closePath();
      ctx.fill();
    }
  }
}

// Redraw on data changes
watch([() => props.energyCurve, () => props.currentTime, () => props.duration, () => props.startTime], draw, { deep: true });

let rafId = 0;
function loop() {
  draw();
  rafId = requestAnimationFrame(loop);
}

onMounted(() => {
  rafId = requestAnimationFrame(loop);
});

onUnmounted(() => {
  cancelAnimationFrame(rafId);
});

// — Click to seek (maps canvas position → module-local time → global time) —
function onCanvasClick(e: MouseEvent) {
  if (!props.duration) return;
  const rect = (e.target as HTMLCanvasElement).getBoundingClientRect();
  const x = e.clientX - rect.left;
  const localT = (x / WIDTH) * props.duration;
  emit('seek', rangeStart.value + localT);
}
</script>

<style scoped>
.aw {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 4px;
}
.aw__canvas {
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: block;
}
.aw__canvas:hover {
  opacity: 0.9;
}
</style>
