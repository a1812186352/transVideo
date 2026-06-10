<template>
  <div class="mat-grid">
    <!-- 空状态 -->
    <div v-if="!gaps.length" class="mat-grid__empty">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <polyline points="21 15 16 10 5 21" />
      </svg>
      <p>请先完成视频分析以获取素材需求</p>
    </div>

    <!-- 3 列网格 -->
    <div v-else class="mat-grid__grid">
      <div
        v-for="gap in gaps"
        :key="gap.key"
        class="mat-grid__cell"
        :class="{
          'mat-grid__cell--missing': gap.status === 'missing' && !gap.file,
          'mat-grid__cell--insufficient': gap.status === 'insufficient',
          'mat-grid__cell--matched': gap.status === 'matched' && gap.file,
        }"
        @click="!gap.file && openPicker(gap.key, gap.accept)"
        @dragover.prevent="dragKey = gap.key"
        @dragleave="dragKey = null"
        @drop.prevent="onDrop(gap.key, $event)"
      >
        <!-- 不足角标 -->
        <span v-if="gap.status === 'insufficient'" class="mat-grid__badge">!</span>
        <!-- 已匹配勾 -->
        <span v-if="gap.status === 'matched' && gap.file" class="mat-grid__check">✓</span>

        <!-- 缩略图区 -->
        <div class="mat-grid__thumb">
          <template v-if="gap.file">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <polygon v-if="gap.accept.includes('video')" points="5 3 19 12 5 21 5 3" />
              <rect v-else-if="gap.accept.includes('audio')" x="3" y="3" width="18" height="18" rx="2" />
              <polyline v-else points="3 15 8 10 13 15 18 8 21 11" />
            </svg>
          </template>
          <template v-else>
            <svg class="mat-grid__plus" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </template>
        </div>

        <!-- 标签 -->
        <span class="mat-grid__label">{{ gap.label }}</span>

        <!-- 文件名 -->
        <span v-if="gap.file" class="mat-grid__fname">{{ gap.file.name }}</span>

        <!-- 提示 -->
        <span v-if="!gap.file" class="mat-grid__hint">{{ gap.reason }}</span>

        <!-- 上传/替换按钮 -->
        <button
          class="mat-grid__btn"
          @click.stop="openPicker(gap.key, gap.accept)"
        >{{ gap.file ? '替换' : '上传' }}</button>

        <!-- 删除（仅已上传） -->
        <button
          v-if="gap.file"
          class="mat-grid__remove"
          @click.stop="material.removeFile(gap.key)"
          title="移除"
        >&times;</button>
      </div>
    </div>

    <!-- 隐藏文件输入 -->
    <input
      ref="fileInput"
      type="file"
      hidden
      @change="onFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useMaterialStore } from '../../stores/material';

const material = useMaterialStore();
const gaps = computed(() => material.gaps);

const fileInput = ref<HTMLInputElement | null>(null);
const dragKey = ref<string | null>(null);
const pendingKey = ref<string | null>(null);
const pendingAccept = ref<string>('');

function openPicker(key: string, accept: string) {
  pendingKey.value = key;
  pendingAccept.value = accept;
  if (fileInput.value) {
    fileInput.value.accept = accept;
    fileInput.value.click();
  }
}

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file && pendingKey.value) {
    material.uploadFile(pendingKey.value, file);
  }
  input.value = '';
  pendingKey.value = null;
}

function onDrop(key: string, e: DragEvent) {
  dragKey.value = null;
  const file = e.dataTransfer?.files?.[0];
  if (file) material.uploadFile(key, file);
}
</script>

<style scoped>
.mat-grid {
  height: 100%;
  overflow-y: auto;
  padding: 8px;
}

/* ── Empty state ── */
.mat-grid__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 10px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
  padding: 20px;
}

/* ── 3-column grid ── */
.mat-grid__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

/* ── Cell ── */
.mat-grid__cell {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  overflow: hidden;
  min-height: 110px;
}

/* States */
.mat-grid__cell--missing {
  border: 1.5px dashed var(--border);
  background: transparent;
  color: var(--text-muted);
}
.mat-grid__cell--missing:hover,
.mat-grid__cell--missing.mat-grid__cell--dragover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-subtle);
}

.mat-grid__cell--insufficient {
  border: 1.5px dashed var(--warning, #f59e0b);
  background: rgba(245, 158, 11, 0.04);
}
.mat-grid__cell--insufficient:hover {
  border-color: var(--warning, #f59e0b);
}

.mat-grid__cell--matched {
  border: 1px solid var(--border);
  background: var(--bg-surface);
}
.mat-grid__cell--matched:hover {
  border-color: var(--text-muted);
}

/* ── Plus icon ── */
.mat-grid__plus {
  opacity: 0.5;
}

/* ── Thumbnail zone ── */
.mat-grid__thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  flex: 1;
  min-height: 40px;
}
.mat-grid__thumb svg {
  color: var(--text-muted);
}

/* ── Labels ── */
.mat-grid__label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-primary);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.mat-grid__fname {
  font-size: 9px;
  color: var(--text-secondary);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.mat-grid__hint {
  font-size: 9px;
  color: var(--text-muted);
  text-align: center;
  line-height: 1.3;
}

/* ── Badges ── */
.mat-grid__badge {
  position: absolute;
  top: 4px;
  left: 4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--warning, #f59e0b);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.mat-grid__check {
  position: absolute;
  top: 4px;
  left: 4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--success, #10b981);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

/* ── Buttons ── */
.mat-grid__btn {
  font-size: 10px;
  padding: 2px 10px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  margin-top: auto;
}
.mat-grid__btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.mat-grid__remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: rgba(0,0,0,0.5);
  color: #fff;
  font-size: 11px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
  z-index: 1;
}
.mat-grid__cell:hover .mat-grid__remove {
  opacity: 1;
}
.mat-grid__remove:hover {
  background: var(--gap-solid, #ef4444);
}
</style>
