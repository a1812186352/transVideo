<template>
  <div class="script-timeline">
    <!-- ── Module description rows ── -->
    <div class="script-timeline__list" v-if="modules.length">
      <div
        v-for="(mod, i) in modules"
        :key="i"
        class="script-timeline__row"
        @click="emit('seek', mod.startTime)"
      >
        <span class="script-timeline__dot" :class="`script-timeline__dot--${mod.type}`"></span>
        <span class="script-timeline__label">{{ mod.name }}</span>
        <span class="script-timeline__time">{{ fmtTime(mod.startTime) }}–{{ fmtTime(mod.endTime) }}</span>
        <span class="script-timeline__desc">{{ mod.description }}</span>
        <button class="script-timeline__expand" @click.stop="toggleDetail(i)" :title="expanded[i] ? '收起详情' : '展开详情'">⋯</button>
      </div>
      <!-- Expanded technical detail rows -->
      <div v-for="(mod, i) in modules" :key="'d'+i" v-show="expanded[i]"
           class="script-timeline__detail" @click="emit('seek', mod.startTime)">
        <div v-if="mod.motion" class="st-detail__row">动效: {{ mod.motion }}</div>
        <div v-if="mod.emotionPeak" class="st-detail__row">情绪: {{ mod.emotionPeak }}</div>
        <div v-if="mod.sceneTags?.length" class="st-detail__row">场景: {{ mod.sceneTags.join(' · ') }}</div>
        <div v-if="mod.visualElements?.length" class="st-detail__row">视觉: {{ mod.visualElements.slice(0,3).join(' · ') }}</div>
        <div v-if="mod.voiceContent" class="st-detail__row">配音: {{ mod.voiceContent.slice(0,40) }}{{ mod.voiceContent.length > 40 ? '…' : '' }}</div>
        <div v-if="mod.ocrTexts?.length" class="st-detail__row">文字: {{ mod.ocrTexts.slice(0,3).join(' · ') }}</div>
        <div v-if="mod.bgmType" class="st-detail__row">BGM: {{ mod.bgmType }} <span v-if="mod.bpm">({{ mod.bpm }} BPM)</span></div>
      </div>
    </div>
    <div v-else class="script-timeline__empty">未解析到模块</div>

    <!-- ── Mini timeline (draggable visual) ── -->
    <div class="script-timeline__track" v-if="modules.length">
      <div
        v-for="(mod, i) in modules"
        :key="i"
        class="script-timeline__seg"
        :class="`script-timeline__seg--${mod.type}`"
        :style="segStyle(mod)"
        :title="`${mod.name}: ${mod.description}`"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

export interface ScriptModule {
  name: string;
  startTime: number;
  endTime: number;
  description: string;
  type: 'opening' | 'highlight' | 'transition' | 'closing' | 'effect' | 'unclassified';
  /** Raw detail fields for expandable technical view */
  motion?: string;
  visualElements?: string[];
  ocrTexts?: string[];
  voiceContent?: string;
  sceneTags?: string[];
  emotionPeak?: string;
  energyCurve?: number[];
  bpm?: number;
  bgmType?: string;
}

const props = defineProps<{
  modules: ScriptModule[];
}>();

const emit = defineEmits<{
  (e: 'seek', time: number): void;
}>();

const expanded = ref<Record<number, boolean>>({});

function toggleDetail(i: number) {
  expanded.value[i] = !expanded.value[i];
}

const totalDuration = (): number => {
  if (!props.modules.length) return 1;
  return Math.max(...props.modules.map(m => m.endTime));
};

function segStyle(mod: ScriptModule) {
  const dur = totalDuration();
  const left = (mod.startTime / dur) * 100;
  const width = ((mod.endTime - mod.startTime) / dur) * 100;
  return {
    left: `${left}%`,
    width: `${Math.max(width, 1.5)}%`,
  };
}

function fmtTime(s: number): string {
  const sec = Math.floor(s);
  const ms = Math.round((s - sec) * 10);
  return `${sec}.${ms}s`;
}
</script>

<style scoped>
.script-timeline {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── Module row list ── */
.script-timeline__list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.script-timeline__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  font-size: 11px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background var(--transition);
}
.script-timeline__row:hover { background: var(--bg-hover); }
.script-timeline__row:last-child {
  border-bottom: none;
}

/* ── Colored dot ── */
.script-timeline__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.script-timeline__dot--opening    { background: var(--slot-opening); }
.script-timeline__dot--highlight  { background: var(--slot-highlight); }
.script-timeline__dot--transition { background: var(--slot-transition); }
.script-timeline__dot--closing    { background: var(--slot-closing); }
.script-timeline__dot--effect     { background: var(--slot-effect); }

/* ── Label ── */
.script-timeline__label {
  font-weight: 600;
  color: var(--text-primary);
  width: 64px;
  flex-shrink: 0;
}

/* ── Time range ── */
.script-timeline__time {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  width: 60px;
  flex-shrink: 0;
  white-space: nowrap;
}

/* ── Description ── */
.script-timeline__desc {
  flex: 1;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Empty state ── */
.script-timeline__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--text-muted);
}

/* ── Mini timeline track ── */
.script-timeline__track {
  position: relative;
  height: 24px;
  margin: 6px 8px 8px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
}

.script-timeline__seg {
  position: absolute;
  top: 3px;
  bottom: 3px;
  border-radius: 3px;
  opacity: 0.8;
}

.script-timeline__seg--opening    { background: var(--slot-opening); }
.script-timeline__seg--highlight  { background: var(--slot-highlight); }
.script-timeline__seg--transition { background: var(--slot-transition); }
.script-timeline__seg--closing    { background: var(--slot-closing); }
.script-timeline__seg--effect     { background: var(--slot-effect); }

/* ── Expand button ── */
.script-timeline__expand {
  flex-shrink: 0; width: 20px; height: 20px; border: none; border-radius: 50%;
  background: transparent; color: var(--text-muted); font-size: 14px; line-height: 1;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background var(--transition);
}
.script-timeline__expand:hover { background: var(--bg-hover); color: var(--text-primary); }

/* ── Detail row ── */
.script-timeline__detail {
  padding: 4px 10px 4px 26px; font-size: 10px; color: var(--text-muted);
  background: var(--bg-root); border-bottom: 1px solid var(--border);
  cursor: pointer; transition: background var(--transition);
}
.script-timeline__detail:hover { background: var(--bg-hover); }
.st-detail__row { padding: 1px 0; font-family: var(--font-mono); }
</style>
