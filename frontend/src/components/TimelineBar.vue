<template>
  <div class="timeline">
    <div class="timeline__header">时间轴 · 模块编排</div>
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
.timeline__modules {
  flex: 1; display: flex; align-items: center;
  padding: 0 12px; gap: 6px; overflow-x: auto;
}

/* ── Module card ── */
.timeline__card {
  height: 40px; border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-surface);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer; transition: all var(--transition);
  flex-shrink: 0; min-width: 60px; padding: 0 12px;
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

/* ── Card content ── */
.timeline__card-type {
  font-size: 11px; font-weight: 500;
  color: var(--text-secondary); white-space: nowrap;
}
.timeline__card-dur {
  font-size: 10px; color: var(--text-muted);
  margin-left: 4px;
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
