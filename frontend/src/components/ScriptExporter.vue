<template>
  <div class="exporter">
    <div class="exporter__header">
      <span class="exporter__title">导出脚本</span>
      <button class="exporter__close" @click="emit('close')">×</button>
    </div>

    <!-- Format selector -->
    <div class="exporter__section">
      <div class="exporter__section-title">导出格式</div>
      <div class="exporter__formats">
        <button
          v-for="f in formats"
          :key="f.key"
          class="exporter__fmt"
          :class="{ 'exporter__fmt--active': selected === f.key }"
          @click="selected = f.key"
        >
          <span class="exporter__fmt-icon">{{ f.icon }}</span>
          <span class="exporter__fmt-label">{{ f.label }}</span>
          <span class="exporter__fmt-ext">.{{ f.ext }}</span>
        </button>
      </div>
    </div>

    <!-- Summary -->
    <div class="exporter__section">
      <div class="exporter__section-title">脚本概览</div>
      <div class="exporter__summary">
        <span>共 <b>{{ script.metadata.block_count }}</b> 个模块</span>
        <span>总时长 <b>{{ fmtHMS(script.metadata.total_duration) }}</b></span>
      </div>
      <div class="exporter__types" v-if="typeEntries.length">
        <span v-for="[k, v] in typeEntries" :key="k" class="exporter__type-chip">
          {{ structureLabel(k) }} ×{{ v }}
        </span>
      </div>
    </div>

    <!-- Preview -->
    <div class="exporter__section">
      <div class="exporter__section-title">预览</div>
      <div class="exporter__preview" ref="previewRef">
        <pre>{{ previewText }}</pre>
      </div>
    </div>

    <!-- Actions -->
    <div class="exporter__actions">
      <button class="exporter__btn exporter__btn--secondary" @click="copyToClipboard">
        📋 复制
      </button>
      <button class="exporter__btn exporter__btn--primary" @click="doDownload">
        ⬇ 下载 {{ filename }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useTimelineStore } from '../stores/timelineStore';
import { useProjectStore } from '../stores/project';
import {
  composeScript, exportScript, downloadScript, type ExportFormat,
} from '../utils/scriptGenerator';

const timeline = useTimelineStore();
const project = useProjectStore();
const emit = defineEmits<{ close: [] }>();

const selected = ref<ExportFormat>('markdown');

const formats: { key: ExportFormat; icon: string; label: string; ext: string }[] = [
  { key: 'json',     icon: '{ }', label: 'JSON',       ext: 'json' },
  { key: 'markdown', icon: 'MD',  label: 'Markdown',   ext: 'md'   },
  { key: 'html',     icon: '<>',  label: 'HTML',       ext: 'html' },
  { key: 'srt',      icon: 'CC',  label: '字幕 SRT',   ext: 'srt'  },
  { key: 'plain',    icon: 'T',   label: '纯文本',     ext: 'txt'  },
];

const script = computed(() => composeScript(timeline.modules, project.metadata.title));

const { content: previewText, ext: __ } = computed(() =>
  exportScript(script.value, selected.value)
).value as any;

// recompute preview when format changes
const previewComputed = computed(() => {
  const { content } = exportScript(script.value, selected.value);
  // trim to ~600 chars for preview
  return content.length > 600 ? content.slice(0, 600) + '\n…' : content;
});

const filename = computed(() => {
  const { ext } = exportScript(script.value, selected.value);
  const name = project.metadata.title || 'script';
  return `${name}.${ext}`;
});

const typeEntries = computed(() =>
  Object.entries(script.value.metadata.structure_summary)
);

function structureLabel(s: string): string {
  const m: Record<string, string> = {
    opening: '开头', highlight: '高潮', transition: '转场',
    effect: '特效', closing: '结尾', content: '内容',
  };
  return m[s] || s;
}

async function copyToClipboard() {
  try {
    const { content } = exportScript(script.value, selected.value);
    await navigator.clipboard.writeText(content);
  } catch { /* ignore */ }
}

function doDownload() {
  const { content } = exportScript(script.value, selected.value);
  downloadScript(content, filename.value);
  emit('close');
}

const fmtHMS = (s: number): string => {
  if (!s || s <= 0) return '0:00';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  const p = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${p(m)}:${p(sec)}` : `${m}:${p(sec)}`;
};
</script>

<style scoped>
.exporter {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.exporter__header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.exporter__title { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.exporter__close {
  border: none; background: none; color: var(--text-muted); font-size: 16px;
  cursor: pointer; padding: 0 4px; line-height: 1;
}

/* ── Sections ── */
.exporter__section {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.exporter__section-title {
  font-size: 10px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 6px;
}

/* ── Format grid ── */
.exporter__formats {
  display: flex; gap: 4px; flex-wrap: wrap;
}
.exporter__fmt {
  display: flex; gap: 4px; align-items: center;
  padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-surface); cursor: pointer; transition: all var(--transition);
  font-size: 11px;
}
.exporter__fmt:hover { border-color: var(--accent); }
.exporter__fmt--active { border-color: var(--accent); background: var(--accent-subtle); color: var(--accent); }
.exporter__fmt-icon { font-weight: 700; font-size: 11px; }
.exporter__fmt-label { font-weight: 500; }
.exporter__fmt-ext { color: var(--text-muted); font-size: 10px; font-family: var(--font-mono); }

/* ── Summary ── */
.exporter__summary { display: flex; gap: 16px; font-size: 11px; color: var(--text-secondary); }
.exporter__types { display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }
.exporter__type-chip {
  font-size: 10px; padding: 1px 8px; border-radius: 8px;
  background: var(--accent-subtle); color: var(--accent);
}

/* ── Preview ── */
.exporter__preview {
  max-height: 160px; overflow: auto;
  background: var(--bg-root); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 8px;
  scrollbar-width: thin; scrollbar-color: var(--border) transparent;
}
.exporter__preview pre {
  margin: 0; font-size: 10px; font-family: var(--font-mono);
  color: var(--text-secondary); white-space: pre-wrap; word-break: break-all;
}

/* ── Actions ── */
.exporter__actions {
  display: flex; gap: 8px; padding: 8px 12px; margin-top: auto; flex-shrink: 0;
  border-top: 1px solid var(--border);
}
.exporter__btn {
  flex: 1; padding: 6px 0; border: none; border-radius: var(--radius-sm);
  font-size: 12px; font-weight: 500; cursor: pointer; transition: all var(--transition);
}
.exporter__btn--primary { background: var(--accent); color: #fff; }
.exporter__btn--primary:hover { background: var(--accent-hover); }
.exporter__btn--secondary { background: var(--bg-surface); color: var(--text-secondary); border: 1px solid var(--border); }
.exporter__btn--secondary:hover { border-color: var(--accent); color: var(--accent); }
</style>
