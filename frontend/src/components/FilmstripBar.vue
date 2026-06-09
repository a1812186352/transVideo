<template>
  <div class="filmstrip" v-if="videoId" ref="containerRef">
    <div
      class="filmstrip__track"
      ref="trackRef"
      @click="onTrackClick"
      @mousemove="onHover"
      @mouseleave="hoverIndex = -1"
    >
      <div
        v-for="(thumb, i) in thumbnails"
        :key="i"
        class="filmstrip__frame"
        :class="{ 'filmstrip__frame--active': activeIndex === i }"
        :style="{ width: frameWidth + 'px', backgroundImage: `url(${thumb.data_uri})` }"
      >
        <!-- Hover magnifier -->
        <div
          v-if="hoverIndex === i"
          class="filmstrip__popup"
          :style="{ left: Math.min(i * frameWidth - 60, 0) + 'px' }"
        >
          <img :src="thumb.data_uri" :alt="`@${thumb.timestamp}s`" />
          <span class="filmstrip__popup-time">{{ fmtTime(thumb.timestamp) }}</span>
        </div>
      </div>
    </div>
    <!-- Playhead -->
    <div class="filmstrip__playhead" :style="{ left: playheadPct + '%' }" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useProjectStore } from '../stores/project';

const store = useProjectStore();

const containerRef = ref<HTMLDivElement | null>(null);
const trackRef = ref<HTMLDivElement | null>(null);
const thumbnails = ref<{ timestamp: number; data_uri: string }[]>([]);
const hoverIndex = ref(-1);

// ── Derived ──
const videoId = computed(() => store.videoId);
const activeIndex = computed(() => {
  if (!thumbnails.value.length || !store.currentTime) return -1;
  // Find nearest thumbnail to current playhead
  let best = 0;
  let bestDist = Infinity;
  for (let i = 0; i < thumbnails.value.length; i++) {
    const d = Math.abs(thumbnails.value[i].timestamp - store.currentTime);
    if (d < bestDist) { bestDist = d; best = i; }
  }
  return best;
});

// ── Width: each frame proportionally fills the bar ──
const frameWidth = computed(() => {
  if (!containerRef.value || !thumbnails.value.length) return 0;
  return containerRef.value.offsetWidth / thumbnails.value.length;
});

const playheadPct = computed(() => {
  const dur = store.script.metadata.total_duration;
  if (!dur || dur <= 0 || !store.currentTime) return 0;
  return (store.currentTime / dur) * 100;
});

// ── Fetch thumbnails when video changes ──
async function fetchFilmstrip(id: string) {
  const base = store.apiBaseUrl.replace(/\/+$/, '');
  // 30 thumbnails fills a wide timeline nicely
  try {
    const res = await fetch(`${base}/upload/video/${id}/filmstrip?count=30`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data: { timestamp: number; data_uri: string }[] = await res.json();
    thumbnails.value = data;
  } catch (e) {
    console.warn('Filmstrip fetch failed:', e);
    thumbnails.value = [];
  }
}

watch(videoId, (id) => {
  if (!id) { thumbnails.value = []; return; }
  fetchFilmstrip(id);
});

// ── Click to seek ──
function onTrackClick(e: MouseEvent) {
  if (!trackRef.value || !thumbnails.value.length) return;
  const rect = trackRef.value.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const pct = x / rect.width;
  const dur = store.script.metadata.total_duration;
  if (dur > 0) {
    const time = pct * dur;
    store.currentTime = time;
    // Also drive the video element
    const video = document.querySelector('.preview__video') as HTMLVideoElement | null;
    if (video) video.currentTime = time;
  }
}

// ── Hover magnifier ──
function onHover(e: MouseEvent) {
  if (!trackRef.value || !thumbnails.value.length) return;
  const rect = trackRef.value.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const idx = Math.floor(x / rect.width * thumbnails.value.length);
  hoverIndex.value = Math.max(0, Math.min(thumbnails.value.length - 1, idx));
}

// ── Format time ──
const fmtTime = (s: number): string => {
  if (!s || s <= 0) return '0:00';
  const min = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${min}:${String(sec).padStart(2, '0')}`;
};
</script>

<style scoped>
.filmstrip {
  position: relative;
  width: 100%;
  height: 44px;
  overflow: hidden;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg-root);
}

.filmstrip__track {
  display: flex;
  height: 100%;
  cursor: pointer;
  position: relative;
}

.filmstrip__frame {
  flex-shrink: 0;
  height: 100%;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  transition: filter 120ms ease;
  position: relative;
}

.filmstrip__frame:hover {
  filter: brightness(1.15);
}

.filmstrip__frame--active {
  box-shadow: inset 0 0 0 1px var(--accent);
}

/* ── Hover popup ── */
.filmstrip__popup {
  position: absolute;
  bottom: 100%;
  margin-bottom: 6px;
  z-index: 20;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.filmstrip__popup img {
  width: 160px;
  height: auto;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
  border: 2px solid var(--accent);
  display: block;
}

.filmstrip__popup-time {
  margin-top: 3px;
  font-size: 10px;
  font-weight: 600;
  color: var(--accent);
  background: var(--bg-surface);
  padding: 1px 6px;
  border-radius: 3px;
  font-family: var(--font-mono);
}

/* ── Playhead ── */
.filmstrip__playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--accent);
  pointer-events: none;
  z-index: 10;
  transform: translateX(-50%);
  transition: left 150ms ease;
}

.filmstrip__playhead::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 6px solid var(--accent);
}
</style>
