<template>
  <div class="timeline">
    <div class="timeline__modules" ref="scrollRef">
      <div
        v-for="(mod, i) in store.modules"
        :key="mod.id"
        class="timeline__card"
        :class="[`timeline__card--${mod.type}`, { 'timeline__card--sel': store.selectedModuleId === mod.id }]"
        :style="{ flex: mod.duration || 1 }"
        draggable="true"
        @dragstart="onDragStart(i, $event)"
        @dragover.prevent="onDragOver(i, $event)"
        @dragend="onDragEnd"
        @click="store.selectModule(mod.id)"
      >
        <span class="timeline__card-type">{{ typeLabel(mod.type) }}</span>
        <span class="timeline__card-dur">{{ fmtDuration(mod.duration) }}</span>
      </div>
    </div>

    <!-- Progress bar -->
    <div class="timeline__progress">
      <div class="timeline__progress-fill" :style="{ width: progressPct + '%' }" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useProjectStore } from '../stores/project';
import type { ModuleType } from '../types/script';

const store = useProjectStore();

// ── Drag reorder ──
const scrollRef = ref<HTMLDivElement | null>(null);
let dragIdx = -1;

function onDragStart(i: number, e: DragEvent) {
  dragIdx = i;
  e.dataTransfer?.setData('text/plain', String(i));
  e.dataTransfer!.effectAllowed = 'move';
}
function onDragOver(toIdx: number, _e: DragEvent) {
  if (dragIdx < 0 || dragIdx === toIdx) return;
  const mods = [...store.modules];
  const [moved] = mods.splice(dragIdx, 1);
  mods.splice(toIdx, 0, moved);
  dragIdx = toIdx;
  store.script.modules = mods;
}
function onDragEnd() {
  dragIdx = -1;
}

// ── Type label ──
const typeLabel = (t: ModuleType): string => {
  const m: Record<ModuleType, string> = {
    title: '开头',
    video_segment: '高潮',
    subtitle: '字幕',
    transition: '转场',
    audio: '音频',
    effect: '特效',
  };
  return m[t] || t;
};

// ── Duration format ──
const fmtDuration = (s: number): string => {
  if (!s || s <= 0) return '—';
  const sec = Math.round(s);
  return `${sec}s`;
};

// ── Progress ──
const progressPct = computed(() => {
  if (!store.currentTime || !store.script.metadata.total_duration) return 0;
  return Math.min(100, (store.currentTime / store.script.metadata.total_duration) * 100);
});
</script>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 4px 8px;
  gap: 4px;
}

/* ── Module cards row ── */
.timeline__modules {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  flex: 1;
  align-items: stretch;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
  padding: 2px 0;
}

/* ── Module card ── */
.timeline__card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  padding: 4px 8px;
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--border);
  cursor: pointer;
  user-select: none;
  transition: all var(--transition);
  box-shadow: var(--shadow-sm);
}
.timeline__card:hover {
  background: var(--bg-hover);
}
.timeline__card--sel {
  border-color: var(--accent);
  box-shadow: var(--shadow-md);
}

/* Type color accents on left border */
.timeline__card--transition { border-left-color: #58a6ff; }
.timeline__card--effect     { border-left-color: #bc8cff; }
.timeline__card--video_segment { border-left-color: #f0b429; }
.timeline__card--title,
.timeline__card--subtitle,
.timeline__card--audio    { border-left-color: var(--text-muted); }

/* ── Card content ── */
.timeline__card-type {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
}
.timeline__card-dur {
  font-size: 9px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  white-space: nowrap;
}

/* ── Progress bar ── */
.timeline__progress {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  flex-shrink: 0;
}
.timeline__progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.3s ease;
}
</style>
