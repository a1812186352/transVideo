<template>
  <div class="tr">
    <div class="tr__head">
      <span class="tr__title">批量文本替换</span>
      <button class="tr__close" @click="$emit('close')">×</button>
    </div>

    <!-- ═══ Pattern input ═══ -->
    <div class="tr__field">
      <label class="tr__label">查找</label>
      <div class="tr__input-row">
        <input
          ref="findInput"
          v-model="findPattern"
          class="tr__input"
          :class="{ 'tr__input--error': regexError }"
          placeholder="文本或正则表达式"
          @input="onPatternChange"
        />
        <button class="tr__toggle" :class="{ 'tr__toggle--on': useRegex }" @click="useRegex = !useRegex">
          .*
        </button>
      </div>
      <span v-if="regexError" class="tr__hint tr__hint--error">{{ regexError }}</span>
    </div>

    <!-- ═══ Replace input ═══ -->
    <div class="tr__field">
      <label class="tr__label">替换为</label>
      <input v-model="replaceWith" class="tr__input" placeholder="替换内容（支持 $1 $2 捕获组）" />
    </div>

    <!-- ═══ Module type filter ═══ -->
    <div class="tr__field">
      <label class="tr__label">范围</label>
      <select v-model="filterType" class="tr__select">
        <option value="all">全部模块</option>
        <option value="title">开头</option>
        <option value="video_segment">高潮</option>
        <option value="transition">转场</option>
        <option value="effect">特效</option>
        <option value="subtitle">字幕</option>
      </select>
    </div>

    <!-- ═══ Preview count ═══ -->
    <div class="tr__preview" v-if="previewCount >= 0">
      <span class="tr__preview-dot" :class="{ 'tr__preview-dot--on': previewCount > 0 }" />
      <span>影响 <b>{{ previewCount }}</b> 个模块</span>
    </div>

    <!-- ═══ Actions ═══ -->
    <div class="tr__actions">
      <button class="tr__btn tr__btn--sec" :disabled="!undoStore.canUndo" @click="handleUndo">↩ 撤销</button>
      <button class="tr__btn tr__btn--sec" :disabled="!undoStore.canRedo" @click="handleRedo">↪ 重做</button>
      <button
        class="tr__btn tr__btn--pri"
        :disabled="!findPattern || previewCount === 0"
        @click="handleReplace"
      >替换全部</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useTimelineStore } from '../stores/timelineStore';
import { useUndoStore } from '../stores/undoStore';
import type { Module } from '../types/script';

defineEmits<{ close: [] }>();

const timeline = useTimelineStore();
const undoStore = useUndoStore();

// ── Form state ──
const findInput = ref<HTMLInputElement | null>(null);
const findPattern = ref('');
const replaceWith = ref('');
const useRegex = ref(false);
const filterType = ref('all');
const regexError = ref('');
const lastReplacedModules = ref<Module[] | null>(null);

// ── Computed ──
// These are already computed from Pinia store
const canUndo = undoStore.canUndo;
const canRedo = undoStore.canRedo;

const previewCount = computed(() => {
  if (!findPattern.value) return 0;
  const regex = buildRegex();
  if (!regex) return 0;
  const targetModules = getTargetModules();
  let count = 0;
  for (const mod of targetModules) {
    const text = getModuleText(mod);
    if (text && regex.test(text)) count++;
  }
  return count;
});

// ── Helpers ──
function buildRegex(): RegExp | null {
  regexError.value = '';
  if (!findPattern.value) return null;
  if (useRegex.value) {
    try { return new RegExp(findPattern.value, 'g'); }
    catch (e: any) { regexError.value = e.message; return null; }
  }
  // Plain text: escape special chars
  const escaped = findPattern.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  try { return new RegExp(escaped, 'g'); }
  catch (e: any) { regexError.value = e.message; return null; }
}

function getTargetModules(): Module[] {
  if (filterType.value === 'all') return timeline.modules;
  return timeline.modules.filter(m => m.type === filterType.value);
}

function getModuleText(mod: Module): string {
  return (mod.params?.text_content as string) ||
         (mod.label as string) ||
         ((mod as any).detail?.text_content as string) || '';
}

function setModuleText(mod: Module, text: string) {
  if (mod.params?.text_content !== undefined) {
    mod.params = { ...mod.params, text_content: text };
  } else {
    mod.params = { ...mod.params, text_content: text } as any;
  }
}

function onPatternChange() {
  regexError.value = '';
  if (useRegex.value) {
    try { new RegExp(findPattern.value); }
    catch (e: any) { regexError.value = e.message; }
  }
}

// ── Replace ──
function handleReplace() {
  const regex = buildRegex();
  if (!regex) return;
  const targetModules = getTargetModules();
  if (targetModules.length === 0) return;

  // Save snapshot for undo
  undoStore.snapshot(timeline.modules);

  let replacedCount = 0;
  const updated = [...timeline.modules];

  for (let i = 0; i < updated.length; i++) {
    const mod = updated[i];
    const targetMod = targetModules.find(m => m.id === mod.id);
    if (!targetMod) continue;

    const text = getModuleText(mod);
    if (!text) continue;

    // Reset lastIndex for global regex
    regex.lastIndex = 0;
    const newText = text.replace(regex, replaceWith.value);
    if (newText !== text) {
      replacedCount++;
      const clone = { ...mod, params: { ...mod.params } };
      setModuleText(clone, newText);
      updated[i] = clone;
    }
  }

  if (replacedCount > 0) {
    timeline.modules = updated;
    lastReplacedModules.value = updated;
  }
}

function handleUndo() {
  const prev = undoStore.undo(timeline.modules);
  if (prev) timeline.modules = prev;
}

function handleRedo() {
  const next = undoStore.redo(timeline.modules);
  if (next) timeline.modules = next;
}
</script>

<style scoped>
.tr {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  width: 360px;
  max-height: 90vh;
  overflow-y: auto;
}
.tr__head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid var(--border);
}
.tr__title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.tr__close {
  width: 22px; height: 22px; border: none; border-radius: var(--radius-sm);
  background: transparent; color: var(--text-muted); font-size: 14px; cursor: pointer;
}
.tr__close:hover { background: var(--bg-hover); color: var(--text-primary); }

.tr__field { padding: 10px 14px 4px; }
.tr__label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.3px; display: block; margin-bottom: 4px; }

.tr__input-row { display: flex; gap: 4px; }
.tr__input {
  flex: 1; padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-surface); color: var(--text-primary); font-size: 12px;
  font-family: var(--font-mono); outline: none;
}
.tr__input:focus { border-color: var(--accent); }
.tr__input--error { border-color: #f85149; }

.tr__toggle {
  padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-surface); color: var(--text-muted); font-size: 11px;
  font-family: var(--font-mono); cursor: pointer; transition: all var(--transition);
}
.tr__toggle--on { border-color: var(--accent); color: var(--accent); background: var(--accent-subtle); }

.tr__select {
  width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-surface); color: var(--text-primary); font-size: 12px; cursor: pointer; outline: none;
}

.tr__hint { font-size: 9px; display: block; margin-top: 3px; }
.tr__hint--error { color: #f85149; }

.tr__preview {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px; font-size: 11px; color: var(--text-secondary);
}
.tr__preview-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); }
.tr__preview-dot--on { background: var(--accent); }
.tr__preview b { color: var(--accent); }

.tr__actions {
  display: flex; gap: 6px; padding: 10px 14px; border-top: 1px solid var(--border);
}
.tr__btn {
  padding: 5px 10px; border: none; border-radius: var(--radius-sm);
  font-size: 11px; font-weight: 500; cursor: pointer; transition: all var(--transition);
}
.tr__btn:disabled { opacity: 0.4; cursor: not-allowed; }
.tr__btn--pri {
  flex: 1; background: var(--accent); color: #fff;
}
.tr__btn--pri:hover:not(:disabled) { background: var(--accent-hover); }
.tr__btn--sec {
  background: var(--bg-surface); color: var(--text-secondary); border: 1px solid var(--border);
}
.tr__btn--sec:hover:not(:disabled) { background: var(--bg-hover); }
</style>
