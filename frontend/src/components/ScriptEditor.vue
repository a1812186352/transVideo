<template>
  <div class="script-editor">
    <div class="se-header">
      <span class="se-header__title">脚本编辑</span>
      <button class="se-btn" @click="parseShots" :disabled="!rawText.trim()">
        解析为分镜 ({{ shots.length }})
      </button>
    </div>

    <!-- Raw text area -->
    <textarea
      v-if="!parsed"
      class="se-textarea"
      :value="rawText"
      @input="onRawInput"
      placeholder="在此粘贴或编写视频脚本&#10;&#10;支持 Markdown 格式，用空行分隔段落&#10;每段 = 一个分镜&#10;&#10;示例：&#10;镜头一：开场全景，城市天际线&#10;阳光洒在玻璃幕墙上&#10;&#10;镜头二：推近到主角面部特写&#10;背景虚化，暖色调&#10;&#10;镜头三：快速剪辑动作场景&#10;配合激昂 BGM"
      rows="14"
    ></textarea>

    <!-- Parsed shot timeline -->
    <div v-if="parsed" class="se-shots">
      <div class="se-shots__toolbar">
        <span class="se-shots__count">{{ shots.length }} 个分镜</span>
        <button class="se-btn se-btn--sm" @click="unparse">返回编辑</button>
      </div>
      <div
        v-for="(shot, i) in shots"
        :key="i"
        class="se-shot"
        :class="{ 'se-shot--drag-over': dragOverShot === i }"
        @dragover.prevent="onShotDragOver(i)"
        @dragleave="onShotDragLeave"
        @drop.prevent="onShotDrop(i, $event)"
      >
        <div class="se-shot__head">
          <span class="se-shot__num">#{{ i + 1 }}</span>
          <span class="se-shot__dur">{{ shot.duration || '—' }}</span>
          <button class="se-shot__del" @click="removeShot(i)" title="删除分镜">×</button>
        </div>
        <textarea
          class="se-shot__text"
          :value="shot.text"
          @input="onShotText(i, ($event.target as HTMLTextAreaElement).value)"
          rows="3"
          :placeholder="`分镜 ${i + 1} 提示词…`"
        ></textarea>
        <div v-if="shot.ref_material_ids.length" class="se-shot__refs">
          <span
            v-for="rid in shot.ref_material_ids"
            :key="rid"
            class="se-shot__ref-tag"
          >{{ rid.slice(0, 6) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

export interface Shot {
  index: number;
  text: string;
  duration: string;
  ref_material_ids: string[];
}

const rawText = ref('');
const parsed = ref(false);
const shots = ref<Shot[]>([]);
const dragOverShot = ref<number | null>(null);

const emit = defineEmits<{
  shotsChange: [shots: Shot[]];
}>();

function onRawInput(e: Event) {
  rawText.value = (e.target as HTMLTextAreaElement).value;
}

function parseShots() {
  // Split by double newline, filter noise
  const paragraphs = rawText.value
    .split(/\n\s*\n/)
    .map(s => s.trim())
    .filter(s => s.length > 1 && !/^[#*\-=\s\d.]+$/.test(s));

  shots.value = paragraphs.map((text, i) => ({
    index: i,
    text,
    duration: '',
    ref_material_ids: [],
  }));
  parsed.value = true;
  emit('shotsChange', shots.value);
}

function unparse() {
  parsed.value = false;
}

function removeShot(i: number) {
  shots.value.splice(i, 1);
  emit('shotsChange', shots.value);
}

function onShotText(i: number, val: string) {
  shots.value[i].text = val;
  emit('shotsChange', shots.value);
}

function onShotDragOver(i: number) {
  dragOverShot.value = i;
}

function onShotDragLeave() {
  dragOverShot.value = null;
}

function onShotDrop(shotIdx: number, e: DragEvent) {
  dragOverShot.value = null;
  const data = e.dataTransfer?.getData('application/x-material-id');
  if (data) {
    const ids = shots.value[shotIdx].ref_material_ids;
    if (!ids.includes(data)) ids.push(data);
    emit('shotsChange', shots.value);
  }
}

// Expose for parent
function setRawText(text: string) {
  rawText.value = text;
}

function getShots(): Shot[] {
  return parsed.value ? shots.value : [];
}

defineExpose({ setRawText, getShots, parseShots });
</script>

<style scoped>
.script-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 300px;
}
.se-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.se-header__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.se-btn {
  padding: 5px 12px;
  border: 1px solid var(--accent-amber);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--accent-amber);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.se-btn:hover:not(:disabled) {
  background: var(--accent-amber-dim);
}
.se-btn:disabled {
  opacity: 0.4;
  cursor: default;
}
.se-btn--sm {
  padding: 3px 8px;
  font-size: 10px;
}
.se-textarea {
  flex: 1;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
  font-family: var(--font-mono);
  resize: vertical;
}
.se-textarea:focus {
  outline: none;
  border-color: var(--accent-amber);
}
.se-textarea::placeholder {
  color: var(--text-muted);
  font-size: 12px;
}
.se-shots {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
}
.se-shots__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.se-shots__count {
  font-size: 11px;
  color: var(--text-muted);
}
.se-shot {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  padding: 8px;
  transition: border-color 0.15s, background 0.15s;
}
.se-shot--drag-over {
  border-color: var(--accent-amber);
  background: rgba(255, 183, 77, 0.06);
}
.se-shot__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.se-shot__num {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-amber);
  min-width: 24px;
}
.se-shot__dur {
  font-size: 10px;
  color: var(--text-muted);
}
.se-shot__del {
  margin-left: auto;
  width: 18px; height: 18px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.se-shot__del:hover {
  background: rgba(255, 77, 77, 0.15);
  color: #ff4d4d;
}
.se-shot__text {
  width: 100%;
  padding: 6px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.5;
  font-family: var(--font-mono);
  resize: vertical;
}
.se-shot__text:focus {
  outline: none;
  border-color: var(--accent-amber);
}
.se-shot__refs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.se-shot__ref-tag {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(74, 158, 255, 0.12);
  color: #4a9eff;
}
</style>
