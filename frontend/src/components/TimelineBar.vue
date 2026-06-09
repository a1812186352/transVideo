<template>
  <div class="timeline">
    <div class="timeline__header">时间轴 · 模块编排</div>
    <div class="timeline__track" ref="scrollRef">
      <template v-for="(mod, i) in timeline.modules" :key="mod.id">
        <!-- ═══ Module card ═══ -->
        <div
          class="timeline__card"
          :class="[`timeline__card--${mod.type}`, { 'timeline__card--sel': timeline.selectedModuleId === mod.id }]"
          :style="{ flex: mod.duration || 1 }"
          draggable="true"
          @dragstart="onDragStart(i, $event)"
          @dragover.prevent="onDragOver(i, $event)"
          @dragend="onDragEnd"
          @click="onCardClick(mod)"
        >
          <div class="timeline__card-top">
            <span class="timeline__card-type">{{ typeLabel(mod.type) }}</span>
            <span class="timeline__card-dur">{{ fmtDuration(mod.duration) }}</span>
          </div>
          <!-- Bottom row: original timestamps + content tags -->
          <div class="timeline__card-btm" v-if="tsLabel(mod)">
            <span class="timeline__ts">{{ tsLabel(mod) }}</span>
            <span class="timeline__tags" v-if="contentTags(mod)">{{ contentTags(mod) }}</span>
          </div>
        </div>
      </template>
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
import { computePlacement } from '../lib/placementPolicy';
import type { Module, ModuleType } from '../types/script';

const store = useProjectStore();
const timeline = useTimelineStore();
const playback = usePlaybackStore();
const drag = useDragStateStore();



// ── Drag reorder with snap + collision ──
const scrollRef = ref<HTMLDivElement | null>(null);
let dragIdx = -1;

function onCardClick(mod: Module) {
  // Select the primary module
  timeline.selectModule(mod.id);
  playback.seekTo(mod.start_time);
}

watch(() => playback.currentTime, (t) => {
  const video = document.querySelector('.preview__video') as HTMLVideoElement | null;
  if (video && Math.abs(video.currentTime - t) > 0.5) {
    video.currentTime = t;
  }
});

function onDragStart(i: number, e: DragEvent) {
  dragIdx = i;
  const card = (e.target as HTMLElement).closest('.timeline__card') as HTMLElement;
  const w = card?.offsetWidth || 80;
  drag.startDrag(timeline.modules[i].id, i, e.clientX, e.clientY, w);

  e.dataTransfer!.effectAllowed = 'move';
  e.dataTransfer?.setData('text/plain', String(i));
}

function onDragOver(toIdx: number, e: DragEvent) {
  if (dragIdx < 0 || dragIdx === toIdx) return;
  drag.updatePosition(e.clientX, e.clientY);

  const track = scrollRef.value;
  if (!track) return;
  const rect = track.getBoundingClientRect();
  const relX = e.clientX - rect.left + track.scrollLeft;
  const pxPerSec = track.scrollWidth / Math.max(1, store.metadata.total_duration || 60);

  const slots = timeline.modules.map((m, idx) => ({
    index: idx,
    id: m.id,
    startTime: m.start_time,
    duration: m.duration,
    isDragging: idx === dragIdx,
  }));

  const mod = timeline.modules[dragIdx];
  const result = computePlacement(
    relX, slots, dragIdx, mod.duration,
    pxPerSec, store.metadata.total_duration || 60,
  );

  drag.setTarget(result.insertIndex, 0, result.startTime);
}

function onDragEnd() {
  const tgt = drag.targetIndex;
  if (dragIdx >= 0 && tgt >= 0 && tgt !== dragIdx) {
    const mods = [...timeline.modules];
    const [moved] = mods.splice(dragIdx, 1);
    moved.start_time = drag.ghostTime;
    mods.splice(tgt, 0, moved);
    timeline.modules = mods;
  }
  drag.endDrag();
  dragIdx = -1;
}

const typeLabel = (t: ModuleType): string => {
  const m: Record<ModuleType, string> = {
    title: '开头', video_segment: '高潮', subtitle: '字幕',
    transition: '转场', audio: '音频', effect: '特效',
  };
  return m[t] || t;
};

const fmtDuration = (s: number): string => {
  if (!s || s <= 0) return '—';
  return `${Math.round(s)}s`;
};

const progressPct = computed(() => {
  if (!playback.currentTime || !store.metadata.total_duration) return 0;
  return Math.min(100, (playback.currentTime / store.metadata.total_duration) * 100);
});

/* ═══════════════════════════════════
   Card bottom-row helpers
   ═══════════════════════════════════ */
const detailOf = (mod: any): any => mod?.detail || mod?.analysis || mod?.params || null;

/** Original video timestamp label (HH:MM:SS → HH:MM:SS) */
function tsLabel(mod: any): string | null {
  const d = detailOf(mod);
  const oStart = d?.original_start;
  const oEnd = d?.original_end;
  if (oStart == null && oEnd == null) return null;
  const s = oStart != null ? fmtHMS(oStart) : '—';
  const e = oEnd != null ? fmtHMS(oEnd) : '—';
  return `${s} → ${e}`;
}

/** Content tags from the dual-layer classification */
function contentTags(mod: any): string | null {
  const d = detailOf(mod);
  const tags = d?.content_tags;
  if (!tags || !Array.isArray(tags) || !tags.length) return null;
  return tags.slice(0, 3).join(' · ');
}

function fmtHMS(s: number): string {
  if (!s || s <= 0) return '0:00';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}
</script>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
}
.timeline__header {
  display: flex; align-items: center;
  padding: 4px 12px;
  font-size: 10px; font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.3px;
  border-bottom: 1px solid var(--border); flex-shrink: 0;
}

/* ── Module cards row ── */
.timeline__track {
  flex: 1; display: flex; align-items: center;
  padding: 0 12px; gap: 0; overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

/* ── Module card ── */
.timeline__card {
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  justify-content: center;
  font-size: 11px; font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer; transition: all var(--transition);
  flex-shrink: 0; min-width: 60px; padding: 4px 10px;
  gap: 1px;
}
.timeline__card:hover { background: var(--bg-hover); box-shadow: var(--shadow-sm); }
.timeline__card--sel { border-color: var(--accent); }

/* Type color accents on left border */
.timeline__card--title       { border-left: 3px solid #9ca3af; }
.timeline__card--subtitle    { border-left: 3px solid #9ca3af; }
.timeline__card--audio       { border-left: 3px solid #9ca3af; }
.timeline__card--transition  { border-left: 3px solid #3b82f6; }
.timeline__card--effect      { border-left: 3px solid #8b5cf6; }
.timeline__card--video_segment { border-left: 3px solid #ef4444; }



/* ── Card top row (type + dur) ── */
.timeline__card-top {
  display: flex;
  align-items: center;
  gap: 4px;
}
.timeline__card-type {
  font-size: 11px; font-weight: 500;
  color: var(--text-secondary); white-space: nowrap;
}
.timeline__card-dur {
  font-size: 10px; color: var(--text-muted);
}

/* ── Card bottom row (timestamps + tags) ── */
.timeline__card-btm {
  display: flex;
  align-items: center;
  overflow: hidden;
  max-width: 100%;
}
.timeline__ts {
  font-size: 9px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  white-space: nowrap;
}
.timeline__tags {
  font-size: 8px;
  color: var(--accent);
  opacity: 0.8;
  margin-left: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Progress bar ── */
.timeline__progress { height: 3px; background: var(--border); flex-shrink: 0; }
.timeline__progress-fill {
  height: 100%; width: 35%;
  background: var(--accent);
  border-radius: 0 2px 2px 0;
  transition: width 0.3s ease;
}
</style>
