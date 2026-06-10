<template>
  <div class="gen-preview zone">
    <div class="zone__body">
      <!-- ── Timeline track ── -->
      <div class="gen-preview__track">
        <div
          v-for="(slot, i) in slots"
          :key="i"
          class="gen-preview__slot"
          :class="{
            [`gen-preview__slot--${slot.status}`]: true,
            'gen-preview__slot--has-popup': popupIndex === i,
          }"
          :style="{
            left: slot.startPercent + '%',
            width: slot.widthPercent + '%',
          }"
        >
          <!-- Slot label (click to toggle popup for gaps) -->
          <span
            class="gen-preview__slot-label"
            @click="(slot.status === 'gap' || slot.status === 'fallback') && togglePopup(i)"
          >{{ slot.name }}</span>

          <!-- Delete button (all slots) -->
          <button
            class="gen-preview__slot-del"
            @click.stop="$emit('remove-slot', i)"
            title="删除模块"
          >&times;</button>

          <!-- Popup menu for gap/fallback slots -->
          <div v-if="popupIndex === i" class="gen-preview__popup">
            <button
              class="gen-preview__popup-btn gen-preview__popup-btn--reuse"
              @click.stop="applyFix(i, 'reuse')"
            >素材复用</button>
            <button
              class="gen-preview__popup-btn gen-preview__popup-btn--fallback"
              @click.stop="applyFix(i, 'fallback')"
            >补全填充</button>
            <button
              class="gen-preview__popup-btn gen-preview__popup-btn--cancel"
              @click.stop="popupIndex = null"
            >取消</button>
          </div>
        </div>
      </div>

      <!-- ── Legend ── -->
      <div class="gen-preview__legend">
        <span class="gen-preview__legend-item gen-preview__legend-item--filled">
          <span class="gen-preview__legend-dot"></span>素材充足
        </span>
        <span class="gen-preview__legend-item gen-preview__legend-item--fallback">
          <span class="gen-preview__legend-dot"></span>复用
        </span>
        <span class="gen-preview__legend-item gen-preview__legend-item--gap">
          <span class="gen-preview__legend-dot"></span>硬缺口
        </span>
        <span class="gen-preview__legend-item gen-preview__legend-item--softgap">
          <span class="gen-preview__legend-dot"></span>补全填充
        </span>
      </div>

      <!-- ── Gap details ── -->
      <div class="gen-preview__gaps" v-if="gapSlots.length">
        <div class="gen-preview__gaps-title">缺口详情</div>
        <div
          v-for="(gap, i) in gapSlots"
          :key="i"
          class="gen-preview__gap-item"
        >
          <span class="gen-preview__gap-badge" :class="`gen-preview__gap-badge--${gap.status}`">
            {{ gap.status === 'gap' ? '硬缺口' : '补全' }}
          </span>
          <span class="gen-preview__gap-name">{{ gap.name }}</span>
          <span class="gen-preview__gap-pos">{{ gap.startPercent }}%–{{ gap.startPercent + gap.widthPercent }}%</span>
          <span class="gen-preview__gap-fix">{{ gapFixSuggestion(gap) }}</span>
          <span class="gen-preview__gap-actions">
            <button
              v-if="gap.status === 'gap'"
              class="gen-preview__gap-btn"
              @click="$emit('fill-slot', originalIndex(gap), 'reuse')"
            >复用</button>
            <button
              class="gen-preview__gap-btn"
              @click="$emit('fill-slot', originalIndex(gap), gap.status === 'gap' ? 'fallback' : 'reuse')"
            >{{ gap.status === 'gap' ? '补全' : '转为充足' }}</button>
            <button
              class="gen-preview__gap-btn gen-preview__gap-btn--del"
              @click="$emit('remove-slot', originalIndex(gap))"
            >删除</button>
          </span>
        </div>
      </div>
      <div v-else class="gen-preview__gaps-empty">无缺口，所有槽位素材充足</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';

interface GenSlot {
  name: string;
  startPercent: number;
  widthPercent: number;
  status: 'filled' | 'gap' | 'fallback';
}

const props = defineProps<{
  slots: GenSlot[];
}>();

defineEmits<{
  (e: 'remove-slot', index: number): void;
  (e: 'fill-slot', index: number, fix: 'reuse' | 'fallback'): void;
}>();

const popupIndex = ref<number | null>(null);

const gapSlots = computed(() =>
  props.slots
    .map((s, idx) => ({ ...s, _origIdx: idx }))
    .filter(s => s.status === 'gap' || s.status === 'fallback')
);

function originalIndex(gap: GenSlot & { _origIdx: number }): number {
  return (gap as any)._origIdx;
}

function togglePopup(i: number) {
  popupIndex.value = popupIndex.value === i ? null : i;
}

function applyFix(i: number, fix: 'reuse' | 'fallback') {
  popupIndex.value = null;
  // delegate to parent via fill-slot emit
}

function gapFixSuggestion(gap: GenSlot): string {
  if (gap.status === 'gap') return '该时段缺少素材，建议上传对应内容或从素材库复用相似片段';
  return '已使用现有素材自动补全，可替换为更匹配的素材';
}
</script>

<style scoped>
.gen-preview {
  height: 100%;
  overflow: hidden;
}

/* ── Track ── */
.gen-preview__track {
  position: relative;
  height: 46px;
  margin: 8px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  overflow: visible;
}

.gen-preview__slot {
  position: absolute;
  top: 0;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  overflow: visible;
  min-width: 28px;
}

.gen-preview__slot--filled {
  background: var(--gap-filled);
}
.gen-preview__slot--gap {
  background: transparent;
  border: 1.5px dashed var(--gap-solid);
}
.gen-preview__slot--fallback {
  background: transparent;
  border: 1.5px dashed var(--gap-soft);
}

.gen-preview__slot-label {
  font-size: 8px;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 2px;
  cursor: default;
}
.gen-preview__slot--gap .gen-preview__slot-label,
.gen-preview__slot--fallback .gen-preview__slot-label {
  color: var(--text-secondary);
  cursor: pointer;
}
.gen-preview__slot--gap .gen-preview__slot-label:hover,
.gen-preview__slot--fallback .gen-preview__slot-label:hover {
  color: var(--accent);
}

/* ── Delete button ── */
.gen-preview__slot-del {
  position: absolute;
  top: -3px;
  right: -3px;
  width: 14px;
  height: 14px;
  border: none;
  border-radius: 50%;
  background: rgba(0,0,0,0.65);
  color: #fff;
  font-size: 9px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}
.gen-preview__slot:hover .gen-preview__slot-del {
  opacity: 1;
}
.gen-preview__slot-del:hover {
  background: var(--gap-solid);
}

/* ── Popup menu ── */
.gen-preview__popup {
  position: absolute;
  top: calc(100% + 4px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 4px 0;
  z-index: 20;
  min-width: 90px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.25);
}
.gen-preview__popup-btn {
  display: block;
  width: 100%;
  padding: 4px 12px;
  font-size: 10px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  white-space: nowrap;
}
.gen-preview__popup-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.gen-preview__popup-btn--reuse:hover {
  color: var(--slot-highlight);
}
.gen-preview__popup-btn--fallback:hover {
  color: var(--slot-closing);
}
.gen-preview__popup-btn--cancel {
  color: var(--text-muted);
  border-top: 1px solid var(--border);
  margin-top: 2px;
  padding-top: 5px;
  font-size: 9px;
}
.gen-preview__popup-btn--cancel:hover {
  color: var(--text-primary);
}

/* ── Legend ── */
.gen-preview__legend {
  display: flex;
  gap: 10px;
  padding: 0 10px 6px;
  flex-wrap: wrap;
}
.gen-preview__legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 9px;
  color: var(--text-muted);
}
.gen-preview__legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex-shrink: 0;
}
.gen-preview__legend-item--filled .gen-preview__legend-dot {
  background: var(--gap-filled);
}
.gen-preview__legend-item--fallback .gen-preview__legend-dot {
  background: var(--gap-soft);
}
.gen-preview__legend-item--gap .gen-preview__legend-dot {
  background: var(--gap-solid);
}
.gen-preview__legend-item--softgap .gen-preview__legend-dot {
  border: 1.5px dashed var(--gap-soft);
  background: transparent;
}

/* ── Gap details ── */
.gen-preview__gaps {
  padding: 0 8px 8px;
  overflow-y: auto;
}
.gen-preview__gaps-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  margin-bottom: 4px;
}
.gen-preview__gap-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 10px;
  border-bottom: 1px solid var(--border);
}
.gen-preview__gap-item:last-child {
  border-bottom: none;
}
.gen-preview__gap-badge {
  font-size: 8px;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
  flex-shrink: 0;
}
.gen-preview__gap-badge--gap {
  background: rgba(239, 68, 68, 0.12);
  color: var(--gap-solid);
}
.gen-preview__gap-badge--fallback {
  background: rgba(245, 158, 11, 0.12);
  color: var(--gap-soft);
}
.gen-preview__gap-name {
  color: var(--text-secondary);
  font-weight: 500;
  flex-shrink: 0;
  min-width: 48px;
}
.gen-preview__gap-pos {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 9px;
}
.gen-preview__gap-fix {
  flex: 1;
  color: var(--text-muted);
  font-size: 9px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gen-preview__gap-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.gen-preview__gap-btn {
  padding: 1px 8px;
  font-size: 9px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}
.gen-preview__gap-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.gen-preview__gap-btn--del {
  color: var(--text-muted);
}
.gen-preview__gap-btn--del:hover {
  border-color: var(--gap-solid);
  color: var(--gap-solid);
}

.gen-preview__gaps-empty {
  padding: 12px;
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
}
</style>
