<template>
  <div class="timeline">
    <!-- ═══ Header with zoom + undo ═══ -->
    <div class="timeline__header">
      <span>时间轴 · 模块编排</span>
      <div class="timeline__header-right">
        <button class="tl-btn" @click="undoStore.canUndo && handleUndo()" :disabled="!undoStore.canUndo" title="撤销 Ctrl+Z">↩</button>
        <button class="tl-btn" @click="undoStore.canRedo && handleRedo()" :disabled="!undoStore.canRedo" title="重做 Ctrl+Shift+Z">↪</button>
        <span class="tl-zoom">{{ Math.round(pxPerSec) }}px/s</span>
        <button class="tl-btn" @click="zoomOut" title="缩小">−</button>
        <button class="tl-btn" @click="zoomIn" title="放大">+</button>
      </div>
    </div>

    <!-- ═══ Track (scrollable + droppable) ═══ -->
    <div
      class="timeline__track"
      ref="scrollRef"
      @wheel.prevent="onWheel"
      @drop.prevent="onTrackDrop"
      @dragover.prevent
    >
      <!-- Snapping alignment guides -->
      <div v-if="snapGuide !== null" class="tl-snap" :style="{ left: snapGuide + 'px' }" />

      <template v-for="(mod, i) in timeline.modules" :key="mod.id">
        <div
          class="timeline__card"
          :class="[`timeline__card--${mod.type}`, { 'timeline__card--sel': timeline.selectedModuleId === mod.id }]"
          :style="{ minWidth: CARD_MIN + 'px', width: Math.max(CARD_MIN, mod.duration * pxPerSec) + 'px' }"
          draggable="true"
          @dragstart="onDragStart(i, $event)"
          @dragover.prevent="onDragOver(i, $event)"
          @dragend="onDragEnd"
          @click.stop="onCardClick(mod)"
        >
          <!-- Keyframe thumbnail -->
          <img v-if="thumbUrl(mod)" :src="thumbUrl(mod) || ''" class="tl-thumb" alt="" />
          <div class="tl-card-body">
            <div class="timeline__card-top">
              <span class="timeline__card-type">{{ typeLabel(mod.type) }}</span>
              <span class="timeline__card-dur">{{ fmtDuration(mod.duration) }}</span>
            </div>
            <div class="timeline__card-btm" v-if="tsLabel(mod)">
              <span class="timeline__ts">{{ tsLabel(mod) }}</span>
            </div>
          </div>
        </div>
      </template>
      <!-- Empty state hint -->
      <div v-if="!timeline.modules.length" class="tl-empty">拖入素材到时间轴创建模块</div>
    </div>

    <!-- Progress bar -->
    <div class="timeline__progress">
      <div class="timeline__progress-fill" :style="{ width: progressPct + '%' }" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useProjectStore } from '../stores/project';
import { useTimelineStore } from '../stores/timelineStore';
import { usePlaybackStore } from '../stores/playbackStore';
import { useDragStateStore } from '../stores/dragStateStore';
import { useUndoStore } from '../stores/undoStore';
import { computePlacement } from '../lib/placementPolicy';
import type { Module, ModuleType } from '../types/script';

const store = useProjectStore();
const timeline = useTimelineStore();
const playback = usePlaybackStore();
const drag = useDragStateStore();
const undoStore = useUndoStore();

// ── Zoom ──
const ZOOM_MIN = 10;
const ZOOM_MAX = 500;
const CARD_MIN = 40;
const pxPerSec = ref(60); // default: 60px per second

function zoomIn() { pxPerSec.value = Math.min(ZOOM_MAX, pxPerSec.value * 1.3); }
function zoomOut() { pxPerSec.value = Math.max(ZOOM_MIN, pxPerSec.value / 1.3); }
function onWheel(e: WheelEvent) {
  if (e.ctrlKey || e.metaKey) {
    if (e.deltaY < 0) zoomIn(); else zoomOut();
  }
}

// ── Snap guide (visual) ──
const snapGuide = ref<number | null>(null);

// ── Drag reorder ──
const scrollRef = ref<HTMLDivElement | null>(null);
let dragIdx = -1;

function onCardClick(mod: Module) {
  timeline.selectModule(mod.id);
  playback.seekTo(mod.start_time);
}

watch(() => playback.currentTime, (t) => {
  const video = document.querySelector('.preview__video') as HTMLVideoElement | null;
  if (video && Math.abs(video.currentTime - t) > 0.5) video.currentTime = t;
});

function onDragStart(i: number, e: DragEvent) {
  dragIdx = i;
  const card = (e.target as HTMLElement).closest('.timeline__card') as HTMLElement;
  drag.startDrag(timeline.modules[i].id, i, e.clientX, e.clientY, card?.offsetWidth || 80);
  e.dataTransfer!.effectAllowed = 'move';
  e.dataTransfer?.setData('text/plain', String(i));
}

const SNAP_THRESHOLD_PX = 12;

function onDragOver(toIdx: number, e: DragEvent) {
  if (dragIdx < 0) return;
  drag.updatePosition(e.clientX, e.clientY);

  const track = scrollRef.value;
  if (!track) return;
  const rect = track.getBoundingClientRect();
  const relX = e.clientX - rect.left + track.scrollLeft;

  // Calculate snap to module boundaries + playhead
  let snapX: number | null = null;
  const totalW = track.scrollWidth;
  for (const m of timeline.modules) {
    const left = (m.start_time / store.metadata.total_duration) * totalW;
    const right = ((m.start_time + m.duration) / store.metadata.total_duration) * totalW;
    if (Math.abs(relX - left) < SNAP_THRESHOLD_PX) snapX = left;
    if (Math.abs(relX - right) < SNAP_THRESHOLD_PX) snapX = right;
  }
  // Snap to playhead
  const ph = (playback.currentTime / store.metadata.total_duration) * totalW;
  if (Math.abs(relX - ph) < SNAP_THRESHOLD_PX) snapX = ph;

  snapGuide.value = snapX;
  const finalX = snapX !== null ? snapX : relX;

  const slots = timeline.modules.map((m, idx) => ({ index: idx, id: m.id, startTime: m.start_time, duration: m.duration, isDragging: idx === dragIdx }));
  const mod = timeline.modules[dragIdx];
  const result = computePlacement(finalX, slots, dragIdx, mod.duration, totalW / Math.max(1, store.metadata.total_duration || 60), store.metadata.total_duration || 60);
  drag.setTarget(result.insertIndex, 0, result.startTime);
}

function onDragEnd() {
  snapGuide.value = null;
  const tgt = drag.targetIndex;
  if (dragIdx >= 0 && tgt >= 0 && tgt !== dragIdx) {
    undoStore.snapshot(timeline.modules);
    const mods = [...timeline.modules];
    const [moved] = mods.splice(dragIdx, 1);
    moved.start_time = drag.ghostTime;
    mods.splice(tgt, 0, moved);
    timeline.setModules(mods);
  }
  drag.endDrag();
  dragIdx = -1;
}

// ── Material drop ──
function onTrackDrop(e: DragEvent) {
  const matId = e.dataTransfer?.getData('application/x-material-id');
  if (matId) {
    undoStore.snapshot(timeline.modules);
    timeline.addModule({
      id: crypto.randomUUID(),
      type: 'video_segment' as ModuleType,
      label: matId.slice(0, 8),
      start_time: 0, duration: 5, track_index: 0, params: {}, children: [],
    });
  }
}

// ── Undo / Redo ──
function handleUndo() { const p = undoStore.undo(timeline.modules); if (p) timeline.setModules(p); }
function handleRedo() { const n = undoStore.redo(timeline.modules); if (n) timeline.setModules(n); }

// ── Label helpers ──
const typeLabel = (t: ModuleType): string => ({
  title: '开头', video_segment: '高潮', subtitle: '字幕',
  transition: '转场', audio: '音频', effect: '特效',
}[t] || t);

const fmtDuration = (s: number): string => s ? `${Math.round(s)}s` : '—';

const progressPct = computed(() => {
  if (!playback.currentTime || !store.metadata.total_duration) return 0;
  return Math.min(100, (playback.currentTime / store.metadata.total_duration) * 100);
});

// ── Card helpers ──
const detailOf = (mod: any): any => mod?.detail || mod?.analysis || mod?.params || null;

function tsLabel(mod: any): string | null {
  const d = detailOf(mod);
  if (d?.original_start == null && d?.original_end == null) return null;
  const s = d?.original_start != null ? fmtHMS(d.original_start) : '—';
  const e = d?.original_end != null ? fmtHMS(d.original_end) : '—';
  return `${s} → ${e}`;
}

function fmtHMS(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

// ── Thumbnail ──
function thumbUrl(mod: any): string | null {
  const d = detailOf(mod);
  const keyframes = d?.keyframes;
  if (keyframes && Array.isArray(keyframes) && keyframes[0]) return keyframes[0];
  const kfPath = d?.keyframe_url;
  if (kfPath) return kfPath;
  // Generate from API: fallback
  if (!store.videoId) return null;
  const t = mod.start_time;
  return `${store.apiBaseUrl.replace(/\/+$/, '')}/video/${store.videoId}/thumbnail?time=${t.toFixed(2)}`;
}
</script>

<style scoped>
.timeline { display: flex; flex-direction: column; height: 100%; }

/* ── Header ── */
.timeline__header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 12px; font-size: 10px; font-weight: 600;
  color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.3px;
  border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.timeline__header-right { display: flex; align-items: center; gap: 4px; }
.tl-btn {
  width: 22px; height: 22px; border: none; border-radius: 3px;
  background: transparent; color: var(--text-muted); font-size: 11px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.tl-btn:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); }
.tl-btn:disabled { opacity: 0.3; }
.tl-zoom { font-size: 9px; font-family: var(--font-mono); color: var(--text-muted); min-width: 44px; text-align: right; }

/* ── Track ── */
.timeline__track {
  flex: 1; display: flex; align-items: center; position: relative;
  padding: 0 12px; gap: 2px; overflow-x: auto;
  scrollbar-width: thin; scrollbar-color: var(--border) transparent;
}

/* ── Snap guide ── */
.tl-snap {
  position: absolute; top: 0; bottom: 0; width: 1px;
  background: var(--accent); z-index: 5; pointer-events: none;
}
.tl-empty {
  width: 100%; text-align: center; font-size: 11px; color: var(--text-muted);
}

/* ── Card ── */
.timeline__card {
  flex-shrink: 0; border-radius: var(--radius-sm);
  border: 1px solid var(--border); background: var(--bg-surface);
  display: flex; align-items: center; gap: 4px;
  font-size: 11px; font-weight: 500; color: var(--text-secondary);
  cursor: pointer; transition: all var(--transition);
  padding: 3px 6px; overflow: hidden;
}
.timeline__card:hover { background: var(--bg-hover); box-shadow: var(--shadow-sm); }
.timeline__card--sel { border-color: var(--accent); }

/* Type left border */
.timeline__card--title       { border-left: 3px solid #9ca3af; }
.timeline__card--subtitle    { border-left: 3px solid #9ca3af; }
.timeline__card--audio       { border-left: 3px solid #9ca3af; }
.timeline__card--transition  { border-left: 3px solid #3b82f6; }
.timeline__card--effect      { border-left: 3px solid #8b5cf6; }
.timeline__card--video_segment { border-left: 3px solid #ef4444; }

/* ── Thumbnail ── */
.tl-thumb { width: 32px; height: 32px; object-fit: cover; border-radius: 3px; flex-shrink: 0; background: var(--bg-root); }

/* ── Card body ── */
.tl-card-body { flex: 1; min-width: 0; overflow: hidden; }
.timeline__card-top { display: flex; align-items: center; gap: 4px; }
.timeline__card-type { font-size: 10px; font-weight: 500; color: var(--text-secondary); white-space: nowrap; }
.timeline__card-dur { font-size: 9px; color: var(--text-muted); }

.timeline__card-btm { overflow: hidden; max-width: 100%; }
.timeline__ts { font-size: 8px; color: var(--text-muted); font-family: var(--font-mono); white-space: nowrap; }

/* ── Progress ── */
.timeline__progress { height: 3px; background: var(--border); flex-shrink: 0; }
.timeline__progress-fill { height: 100%; background: var(--accent); border-radius: 0 2px 2px 0; transition: width 0.3s ease; }
</style>
