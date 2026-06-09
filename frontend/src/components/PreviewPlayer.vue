<template>
  <div class="pp">
    <!-- ═══ Controls ═══ -->
    <div class="pp__controls">
      <button class="pp__btn" @click="stepBack" title="后退">⏮</button>
      <button class="pp__btn pp__btn--play" @click="togglePlay" :title="playing ? '暂停' : '播放'">
        {{ playing ? '⏸' : '▶' }}
      </button>
      <button class="pp__btn" @click="stepForward" title="前进">⏭</button>
      <button class="pp__btn" :class="{ 'pp__btn--on': loop }" @click="loop = !loop" title="循环">🔁</button>
      <span class="pp__time">{{ fmtTime(playback.currentTime) }} / {{ fmtTime(totalDuration) }}</span>
      <input
        class="pp__slider"
        type="range"
        :min="0"
        :max="Math.max(1, totalDuration)"
        :step="0.1"
        :value="playback.currentTime"
        @input="seekTo(($event.target as HTMLInputElement).valueAsNumber)"
      />
    </div>

    <!-- ═══ Timeline preview (virtual scroll) ═══ -->
    <div class="pp__track" ref="trackRef" @scroll="onTrackScroll">
      <!-- Ghost spacer for virtual scroll height -->
      <div class="pp__spacer" :style="{ height: totalHeight + 'px' }" />

      <!-- Visible items -->
      <div class="pp__viewport" :style="{ transform: `translateY(${scrollOffset}px)` }">
        <div
          v-for="(item, i) in visibleItems"
          :key="item.id"
          class="pp__item"
          :class="{
            'pp__item--active': isActive(item),
            'pp__item--past': item.endTime <= playback.currentTime,
            'pp__item--future': item.startTime > playback.currentTime,
          }"
          :style="{ top: item._top + 'px', height: ITEM_H + 'px' }"
          @click="seekTo(item.startTime)"
        >
          <div class="pp__item-badge" :class="`pp__item-badge--${item.type}`">{{ typeBadge(item.type) }}</div>
          <div class="pp__item-content">
            <div class="pp__item-head">
              <span class="pp__item-label">{{ item.label || typeLabel(item.type) }}</span>
              <span class="pp__item-dur">{{ fmtTime(item.startTime) }} – {{ fmtTime(item.endTime) }}</span>
            </div>
            <div class="pp__item-text" v-if="item.text">{{ item.text }}</div>
            <div class="pp__item-detail" v-if="item.detail">
              <span v-if="item.detail.brightness_trend">亮度{{ item.detail.brightness_trend === '变亮' ? '↑' : '↓' }}</span>
              <span v-if="item.detail.scale_trend">{{ item.detail.scale_trend }}</span>
              <span v-if="item.detail.motion_trend">{{ item.detail.motion_trend }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { useTimelineStore } from '../stores/timelineStore';
import { usePlaybackStore } from '../stores/playbackStore';
import type { ModuleType } from '../types/script';

const timeline = useTimelineStore();
const playback = usePlaybackStore();

const ITEM_H = 64;
const BUFFER = 6; // items above/below viewport

// ── Playback state ──
const playing = ref(false);
const loop = ref(false);
let rafId = 0;

const totalDuration = computed(() => {
  if (timeline.modules.length === 0) return 0;
  return Math.max(...timeline.modules.map(m => m.start_time + m.duration));
});

function togglePlay() {
  playing.value = !playing.value;
  if (playing.value) startPlayback();
}

function startPlayback() {
  let last = performance.now();
  function tick(now: number) {
    if (!playing.value) return;
    const dt = (now - last) / 1000;
    last = now;
    const t = playback.currentTime + dt;
    if (t >= totalDuration.value) {
      if (loop.value) {
        playback.seekTo(0);
      } else {
        playback.seekTo(totalDuration.value);
        playing.value = false;
        return;
      }
    } else {
      playback.seekTo(Math.min(t, totalDuration.value));
      // Sync video
      const v = document.querySelector('.preview__video') as HTMLVideoElement | null;
      if (v && Math.abs(v.currentTime - playback.currentTime) > 0.3) {
        v.currentTime = playback.currentTime;
      }
    }
    rafId = requestAnimationFrame(tick);
  }
  rafId = requestAnimationFrame(tick);
}

watch(playing, (p) => {
  if (p) startPlayback();
  else cancelAnimationFrame(rafId);
});

onUnmounted(() => cancelAnimationFrame(rafId));

function seekTo(t: number) {
  playback.seekTo(t);
  const v = document.querySelector('.preview__video') as HTMLVideoElement | null;
  if (v) v.currentTime = t;
}
function stepBack() { seekTo(Math.max(0, playback.currentTime - 1)); }
function stepForward() { seekTo(Math.min(totalDuration.value, playback.currentTime + 1)); }

// ── Module items ──
interface PreviewItem {
  id: string; type: ModuleType; label: string;
  startTime: number; endTime: number;
  text?: string; detail?: Record<string, any>;
  _index: number; _top: number;
}

const items = computed<PreviewItem[]>(() => {
  return timeline.modules.map((m, i) => ({
    id: m.id, type: m.type, label: m.label || '',
    startTime: m.start_time, endTime: m.start_time + m.duration,
    text: (m.params?.text_content || '') as string,
    detail: (m as any).detail || null,
    _index: i, _top: i * ITEM_H,
  }));
});

const totalHeight = computed(() => Math.max(200, items.value.length * ITEM_H));

// ── Virtual scroll ──
const scrollOffset = ref(0);
const trackRef = ref<HTMLDivElement | null>(null);

const visibleItems = computed(() => {
  const h = trackRef.value?.clientHeight || 400;
  const start = Math.max(0, Math.floor(scrollOffset.value / ITEM_H) - BUFFER);
  const end = Math.min(items.value.length, Math.ceil((scrollOffset.value + h) / ITEM_H) + BUFFER);
  return items.value.slice(start, end);
});

function onTrackScroll() {
  if (trackRef.value) scrollOffset.value = trackRef.value.scrollTop;
}

function isActive(item: PreviewItem) {
  return playback.currentTime >= item.startTime && playback.currentTime < item.endTime;
}

// ── Helpers ──
function fmtTime(s: number): string {
  if (!s || s < 0) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

const typeBadge = (t: ModuleType): string => {
  const m: Record<string, string> = { title: 'O', video_segment: 'H', transition: 'T', effect: 'E', subtitle: 'S', audio: 'A' };
  return m[t] || '?';
};

const typeLabel = (t: ModuleType): string => {
  const m: Record<string, string> = { title: '开头', video_segment: '高潮', subtitle: '字幕', transition: '转场', audio: '音频', effect: '特效' };
  return m[t] || t;
};
</script>

<style scoped>
.pp {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-panel);
  overflow: hidden;
}

/* ── Controls ── */
.pp__controls {
  display: flex; align-items: center; gap: 4px;
  padding: 6px 10px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.pp__btn {
  width: 28px; height: 28px; border: none; border-radius: var(--radius-sm);
  background: transparent; color: var(--text-muted); font-size: 12px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all var(--transition);
}
.pp__btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.pp__btn--play { font-size: 14px; }
.pp__btn--on { color: var(--accent); }
.pp__time { font-size: 10px; color: var(--text-muted); font-family: var(--font-mono); white-space: nowrap; min-width: 72px; }
.pp__slider { flex: 1; height: 4px; accent-color: var(--accent); cursor: pointer; margin: 0 4px; }

/* ── Track ── */
.pp__track {
  flex: 1; overflow-y: auto; position: relative;
  scrollbar-width: thin; scrollbar-color: var(--border) transparent;
}
.pp__spacer { width: 1px; }

.pp__viewport {
  position: absolute; left: 0; right: 0;
  will-change: transform;
}
.pp__item {
  position: absolute; left: 0; right: 0;
  display: flex; align-items: flex-start; gap: 8px;
  padding: 6px 10px; border-bottom: 1px solid var(--border);
  cursor: pointer; transition: background var(--transition);
}
.pp__item:hover { background: var(--bg-hover); }
.pp__item--active {
  background: var(--accent-subtle);
  border-left: 3px solid var(--accent);
}
.pp__item--past { opacity: 0.5; }
.pp__item--future { opacity: 0.9; }

.pp__item-badge {
  width: 24px; height: 24px; border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700; flex-shrink: 0; margin-top: 2px;
}
.pp__item-badge--title         { background: #9ca3af33; color: #9ca3af; }
.pp__item-badge--video_segment { background: #ef444433; color: #ef4444; }
.pp__item-badge--transition    { background: #3b82f633; color: #3b82f6; }
.pp__item-badge--effect        { background: #8b5cf633; color: #8b5cf6; }

.pp__item-content { flex: 1; min-width: 0; }
.pp__item-head { display: flex; align-items: center; justify-content: space-between; }
.pp__item-label { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.pp__item-dur { font-size: 9px; color: var(--text-muted); font-family: var(--font-mono); }
.pp__item-text { font-size: 11px; color: var(--text-secondary); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pp__item-detail { display: flex; gap: 6px; margin-top: 2px; font-size: 10px; color: var(--accent); }
</style>
