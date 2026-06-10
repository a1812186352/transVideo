<template>
  <div class="mat-slot">
    <div class="mat-slot__grid">
      <div
        v-for="slot in slots"
        :key="slot.id"
        class="mat-slot__item"
        :class="{
          'mat-slot__item--filled': slot.file,
          'mat-slot__item--empty': !slot.file,
          'mat-slot__item--dragover': dragOverId === slot.id,
        }"
        @click="!slot.file && triggerUpload(slot.id)"
        @dragover.prevent="dragOverId = slot.id"
        @dragleave="dragOverId = null"
        @drop.prevent="onDrop(slot.id, $event)"
      >
        <!-- Filled state -->
        <template v-if="slot.file">
          <div class="mat-slot__thumb">
            <img v-if="slot.file.thumbnail" :src="slot.file.thumbnail" :alt="slot.file.filename" />
            <svg v-else width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
          </div>
          <span class="mat-slot__name">{{ slot.file.filename }}</span>
          <button class="mat-slot__remove" @click.stop="$emit('remove-slot', slot.id)" title="移除">
            &times;
          </button>
        </template>
        <!-- Empty state -->
        <template v-else>
          <svg class="mat-slot__plus" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span class="mat-slot__hint">上传素材</span>
        </template>
      </div>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept="image/*,video/*"
      hidden
      @change="onFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

interface SlotFile {
  filename: string;
  thumbnail?: string;
}

export interface MaterialSlot {
  id: string;
  label: string;
  file?: SlotFile | null;
}

defineProps<{
  slots: MaterialSlot[];
}>();

const emit = defineEmits<{
  (e: 'upload-slot', slotId: string, file: File): void;
  (e: 'remove-slot', slotId: string): void;
}>();

const dragOverId = ref<string | null>(null);
const pendingSlotId = ref<string | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);

function triggerUpload(slotId: string) {
  pendingSlotId.value = slotId;
  fileInput.value?.click();
}

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file && pendingSlotId.value) {
    emit('upload-slot', pendingSlotId.value, file);
  }
  input.value = '';
  pendingSlotId.value = null;
}

function onDrop(slotId: string, e: DragEvent) {
  dragOverId.value = null;
  const file = e.dataTransfer?.files?.[0];
  if (file) emit('upload-slot', slotId, file);
}
</script>

<style scoped>
.mat-slot {
  height: 100%;
  overflow: hidden;
}

.mat-slot__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  padding: 6px;
  height: 100%;
  align-content: start;
}

.mat-slot__item {
  position: relative;
  aspect-ratio: 16 / 11;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  transition: all 0.15s;
  overflow: hidden;
}

.mat-slot__item--empty {
  border: 1.5px dashed var(--border);
  background: transparent;
  color: var(--text-muted);
}
.mat-slot__item--empty:hover,
.mat-slot__item--dragover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-subtle);
}

.mat-slot__item--filled {
  border: 1px solid var(--border);
  background: var(--bg-surface);
  cursor: default;
}
.mat-slot__item--filled:hover {
  border-color: var(--text-muted);
}

.mat-slot__plus {
  opacity: 0.5;
  flex-shrink: 0;
}

.mat-slot__hint {
  font-size: 10px;
  color: var(--text-muted);
}

.mat-slot__thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.mat-slot__thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.mat-slot__thumb svg {
  color: var(--text-muted);
}

.mat-slot__name {
  position: absolute;
  bottom: 4px;
  left: 6px;
  right: 24px;
  font-size: 9px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  background: rgba(0,0,0,0.55);
  padding: 1px 4px;
  border-radius: 3px;
}

.mat-slot__remove {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: rgba(0,0,0,0.55);
  color: #fff;
  font-size: 11px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}
.mat-slot__item:hover .mat-slot__remove {
  opacity: 1;
}
.mat-slot__remove:hover {
  background: var(--gap-solid);
}
</style>
