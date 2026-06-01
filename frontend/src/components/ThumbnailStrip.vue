<template>
  <div class="thumbstrip" ref="stripRef">
    <!-- loading state -->
    <div v-if="loading" class="thumbstrip__loading">加载缩略图中…</div>

    <!-- thumbnail rail -->
    <div
      v-if="!loading && thumbnails.length > 0"
      class="thumbstrip__rail"
      ref="railRef"
      @scroll="onRailScroll"
    >
      <div
        v-for="(th, i) in thumbnails"
        :key="i"
        class="thumbstrip__item"
        :class="{ 'thumbstrip__item--active': i === activeIndex }"
        :style="{ width: thumbWidth + 'px' }"
        @click="seekTo(th.timestamp)"
        @mousedown.prevent="onDragStart(i, $event)"
      >
        <img
          :src="th.data_uri"
          :alt="`${fmtTime(th.timestamp)}`"
          class="thumbstrip__img"
          loading="lazy"
        />
        <span class="thumbstrip__time">{{ fmtTime(th.timestamp) }}</span>
      </div>
    </div>

    <!-- empty state -->
    <div v-else-if="!loading && thumbnails.length === 0" class="thumbstrip__empty">
      无法生成缩略图
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue';

const props = defineProps<{
  videoId: string;
  apiBaseUrl: string;
  duration: number;
  currentTime: number;
}>();

const emit = defineEmits<{
  seek: [time: number];
}>();

const thumbnails = ref<{ timestamp: number; data_uri: string }[]>([]);
const loading = ref(false);
const activeIndex = ref(0);
const thumbWidth = 120;
const railRef = ref<HTMLDivElement | null>(null);
const stripRef = ref<HTMLDivElement | null>(null);

// ── Drag state ──
let _dragging = false;
let _dragStartX = 0;
let _dragStartScroll = 0;

// ── Fetch thumbnails on mount ──
onMounted(async () => {
  if (!props.videoId) return;
  await fetchThumbnails();
});

watch(() => props.videoId, async () => {
  if (props.videoId) await fetchThumbnails();
});

async function fetchThumbnails() {
  loading.value = true;
  try {
    const base = props.apiBaseUrl.replace(/\/+$/, '');
    const interval = calcInterval();
    const res = await fetch(`${base}/upload/video/${props.videoId}/thumbnails?interval=${interval}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    thumbnails.value = await res.json();
  } catch {
    thumbnails.value = [];
  } finally {
    loading.value = false;
  }
}

function calcInterval(): number {
  if (props.duration <= 10) return 0.5;
  if (props.duration <= 30) return 1;
  if (props.duration <= 60) return 2;
  if (props.duration <= 180) return 3;
  if (props.duration <= 600) return 5;
  return 10;
}

// ── Sync active highlight from parent currentTime ──
watch(() => props.currentTime, (t) => {
  const idx = thumbnails.value.findIndex(
    (th, i) =>
      t >= th.timestamp &&
      (i === thumbnails.value.length - 1 || t < thumbnails.value[i + 1].timestamp)
  );
  if (idx >= 0) activeIndex.value = idx;
});

// ── Scroll rail to keep active thumb visible ──
watch(activeIndex, (idx) => {
  const rail = railRef.value;
  if (!rail) return;
  const item = rail.children[idx] as HTMLElement | undefined;
  if (!item) return;
  const rLeft = rail.scrollLeft;
  const rRight = rLeft + rail.clientWidth;
  const iLeft = item.offsetLeft;
  const iRight = iLeft + item.offsetWidth;
  if (iLeft < rLeft || iRight > rRight) {
    item.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  }
});

// ── Click seek ──
function seekTo(t: number) {
  emit('seek', t);
}

// ── Drag seek ──
function onDragStart(idx: number, e: MouseEvent) {
  _dragging = true;
  _dragStartX = e.clientX;
  _dragStartScroll = railRef.value?.scrollLeft ?? 0;
  document.addEventListener('mousemove', onDragMove);
  document.addEventListener('mouseup', onDragEnd);

  // Also seek to clicked position
  seekTo(thumbnails.value[idx].timestamp);
}

function onDragMove(e: MouseEvent) {
  if (!_dragging) return;
  e.preventDefault();
  const rail = railRef.value;
  if (!rail) return;
  // Drag to scroll
  rail.scrollLeft = _dragStartScroll + (_dragStartX - e.clientX);
}

function onDragEnd(_e: MouseEvent) {
  _dragging = false;
  document.removeEventListener('mousemove', onDragMove);
  document.removeEventListener('mouseup', onDragEnd);
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onDragMove);
  document.removeEventListener('mouseup', onDragEnd);
});

// ── Sync scroll position from rail scroll (for mouse-only scrolling) ──
function onRailScroll() {
  // no derived state needed — activeIndex is driven by currentTime
}

function fmtTime(s: number): string {
  if (!s || s <= 0) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}
</script>

<style scoped>
.thumbstrip {
  margin-top: 8px;
  user-select: none;
}
.thumbstrip__loading,
.thumbstrip__empty {
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-muted, #888);
  text-align: center;
  background: var(--bg-elevated, #1e1e2e);
  border-radius: 6px;
}
.thumbstrip__rail {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 6px 0;
  scroll-behavior: smooth;
  cursor: grab;
}
.thumbstrip__rail:active {
  cursor: grabbing;
}
.thumbstrip__item {
  flex: 0 0 auto;
  position: relative;
  border-radius: 4px;
  overflow: hidden;
  border: 2px solid transparent;
  transition: transform 0.15s ease, border-color 0.15s ease;
  cursor: pointer;
}
.thumbstrip__item:hover {
  transform: scale(1.3);
  z-index: 10;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
}
.thumbstrip__item--active {
  border-color: #4a9eff;
  box-shadow: 0 0 0 1px #4a9eff;
}
.thumbstrip__img {
  display: block;
  width: 100%;
  height: auto;
  pointer-events: none;
}
.thumbstrip__time {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 2px 4px;
  font-size: 10px;
  color: #fff;
  background: rgba(0, 0, 0, 0.6);
  text-align: center;
  pointer-events: none;
  white-space: nowrap;
}
</style>
