<template>
  <div class="timeline">
    <div class="timeline__header">时间轴 · 模块编排</div>
    <div class="timeline__track" ref="scrollRef">
      <template v-for="(mod, i) in store.modules" :key="mod.id">
        <!-- ═══ Trend marker between cards ═══ -->
        <div v-if="i > 0" class="trend">
          <span v-if="brightnessTrend(mod)" class="trend__icon" :title="'亮度: ' + brightnessTrend(mod)">
            {{ brightnessTrend(mod) === '变亮' ? '☀' : '🌙' }}
          </span>
          <span v-if="scaleTrend(mod)" class="trend__icon" :title="'缩放: ' + scaleTrend(mod)">
            {{ scaleTrend(mod) === '扩散' ? '↗' : '↙' }}
          </span>
          <span v-if="movementTrend(mod)" class="trend__bar" :class="movementTrend(mod) === '动效增强' ? 'trend__bar--up' : 'trend__bar--down'" />
        </div>

        <!-- ═══ Module card ═══ -->
        <div
          class="timeline__card"
          :class="[`timeline__card--${mod.type}`, { 'timeline__card--sel': store.selectedModuleId === mod.id }]"
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
          <div class="timeline__card-btm" v-if="motionSummary(mod as any)">
            <span class="timeline__motion-text">{{ motionSummary(mod as any) }}</span>
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
import type { Module, ModuleType } from '../types/script';

const store = useProjectStore();

// ── Drag reorder ──
const scrollRef = ref<HTMLDivElement | null>(null);
let dragIdx = -1;

function onCardClick(mod: Module) {
  store.selectModule(mod.id);
  store.seekTo(mod.start_time);
}

watch(() => store.currentTime, (t) => {
  const video = document.querySelector('.preview__video') as HTMLVideoElement | null;
  if (video && Math.abs(video.currentTime - t) > 0.5) {
    video.currentTime = t;
  }
});

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
function onDragEnd() { dragIdx = -1; }

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
  if (!store.currentTime || !store.script.metadata.total_duration) return 0;
  return Math.min(100, (store.currentTime / store.script.metadata.total_duration) * 100);
});

/* ═══════════════════════════════════
   Motion trend helpers
   ═══════════════════════════════════ */
// Read the PREVIOUS module's detail for the gap between module[i-1] and module[i]
function detailOf(mod: any): any {
  return mod?.detail || mod?.analysis || mod?.params || null;
}

function brightnessTrend(mod: any): string | null {
  const d = detailOf(mod);
  const mt = d?.motion_trend;
  return mt?.brightness_trend || null;
}
function scaleTrend(mod: any): string | null {
  const d = detailOf(mod);
  const mt = d?.motion_trend;
  return mt?.scale_trend || null;
}
function movementTrend(mod: any): string | null {
  const d = detailOf(mod);
  const mt = d?.motion_trend;
  return mt?.movement_trend || null;
}

function motionSummary(mod: any): string | null {
  const d = detailOf(mod);
  const parts: string[] = [];
  const md = d?.motion_description;
  if (md?.label) parts.push(md.label);
  for (const k of ['brightness_trend', 'scale_trend', 'movement_trend']) {
    const v = d?.motion_trend?.[k];
    if (!v) continue;
    if (k === 'brightness_trend') parts.push('亮度' + (v === '变亮' ? '↑' : '↓'));
    else if (k === 'scale_trend') parts.push(v);
    else if (k === 'movement_trend') parts.push(v);
  }
  // object_transitions as dict
  const ot = d?.object_transitions;
  if (ot) {
    if (ot.fade_in_count > 0) parts.push(`物体淡入×${ot.fade_in_count}`);
    if (ot.fade_out_count > 0) parts.push(`物体淡出×${ot.fade_out_count}`);
  }
  return parts.length ? parts.join(' + ') : null;
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

/* ── Trend marker between cards ── */
.trend {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  padding: 0 2px;
  height: 100%;
}
.trend__icon {
  font-size: 9px;
  line-height: 1;
  opacity: 0.5;
  transition: opacity var(--transition);
}
.trend:hover .trend__icon {
  opacity: 1;
}
.trend__bar {
  width: 3px;
  height: 24px;
  border-radius: 2px;
  flex-shrink: 0;
  transition: opacity var(--transition);
}
.trend__bar--up {
  background: linear-gradient(to top, var(--accent) 0%, transparent 100%);
  opacity: 0.4;
}
.trend__bar--down {
  background: linear-gradient(to bottom, var(--accent) 0%, transparent 100%);
  opacity: 0.4;
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

/* ── Card bottom row (motion summary) ── */
.timeline__card-btm {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.timeline__motion-text {
  font-size: 9px;
  color: var(--accent);
  opacity: 0.8;
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
