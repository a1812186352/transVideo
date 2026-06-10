<template>
  <div class="template-panel zone">
    <div class="zone__body">
      <div class="template-panel__list">
        <button
          v-for="tpl in templates"
          :key="tpl.id"
          class="template-panel__item"
          :class="{ 'template-panel__item--active': selectedId === tpl.id }"
          @click="selectTemplate(tpl)"
        >
          <span class="template-panel__icon">{{ tpl.icon }}</span>
          <span class="template-panel__name">{{ tpl.name }}</span>
        </button>
      </div>

      <!-- ── 结构迁移按钮：选定模板后出现 ── -->
      <div v-if="selectedId" class="template-panel__action">
        <button class="template-panel__migrate-btn" @click="emitMigrate">
          结构迁移
        </button>
        <span class="template-panel__migrate-hint">
          将当前模板结构应用到视频拆解结果
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';

interface Template {
  id: string;
  icon: string;
  name: string;
}

const templates: Template[] = [
  { id: 'fast-mix', icon: '\u26A1', name: '快节奏混剪' },
  { id: 'live-sale', icon: '\uD83C\uDFA4', name: '口播带货' },
  { id: 'product-review', icon: '\uD83D\uDD0D', name: '产品测评' },
  { id: 'vlog-story', icon: '\uD83C\uDFAC', name: 'Vlog 叙事' },
  { id: 'other', icon: '\uD83D\uDCCB', name: '其他' },
];

const emit = defineEmits<{
  (e: 'select', templateName: string): void;
  (e: 'migrate'): void;
}>();

const selectedId = ref<string | null>(null);

function selectTemplate(tpl: Template) {
  selectedId.value = tpl.id;
  emit('select', tpl.name);
}

function emitMigrate() {
  if (selectedId.value) {
    emit('migrate');
  }
}
</script>

<style scoped>
.template-panel {
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.template-panel__list {
  display: flex;
  flex-direction: row;
  gap: 4px;
  padding: 6px;
  flex: 0 0 auto;
  overflow-x: auto;
}

.template-panel__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: all var(--transition);
  text-align: center;
  flex-shrink: 0;
}

.template-panel__item:hover {
  border-color: var(--accent);
  background: var(--bg-hover);
  color: var(--text-primary);
}

.template-panel__item--active {
  border-color: var(--accent);
  background: var(--accent-subtle);
  color: var(--accent);
  font-weight: 600;
}

.template-panel__icon {
  font-size: 20px;
  line-height: 1;
}

.template-panel__name {
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

/* ── Migrate action ── */
.template-panel__action {
  padding: 8px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.template-panel__migrate-btn {
  width: 100%;
  height: 32px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.template-panel__migrate-btn:hover {
  box-shadow: 0 0 14px rgba(91, 141, 239, 0.2);
}

.template-panel__migrate-hint {
  display: block;
  text-align: center;
  font-size: 9px;
  color: var(--text-muted);
  margin-top: 4px;
}
</style>
