<template>
  <div class="gen">
    <div class="gen__body">
      <!-- ═══ Preview player ═══ -->
      <div class="gen__preview">
        <video v-if="exportDownloadUrl" :src="exportDownloadUrl" controls class="gen__video" />
        <div v-else class="gen__preview-placeholder">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.3">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          <span>视频实时预览</span>
        </div>
      </div>

      <!-- ═══ Status & ETA ═══ -->
      <div class="gen__info">
        <div class="gen__status">
          <span class="gen__status-dot" :class="statusDotClass" />
          <span>{{ statusLabel }}</span>
        </div>
        <div class="gen__eta" v-if="totalDuration > 0 && exportStatus !== 'completed'">
          预计耗时：{{ ws.fmtEta(totalDuration) }}
        </div>
      </div>

      <div class="gen__divider" />

      <!-- ═══ Export settings ═══ -->
      <div class="gen__settings">
        <div class="gen__field">
          <span class="gen__field-label">分辨率</span>
          <select class="gen__select" v-model="exportResolution">
            <option value="1920x1080">1080p</option>
            <option value="1280x720">720p</option>
            <option value="720x480">SD</option>
          </select>
        </div>
        <div class="gen__field">
          <span class="gen__field-label">帧率</span>
          <select class="gen__select" v-model="exportFps">
            <option :value="24">24fps</option>
            <option :value="30">30fps</option>
            <option :value="60">60fps</option>
          </select>
        </div>
      </div>

      <div class="gen__divider" />

      <!-- ═══ Generate button ═══ -->
      <button
        class="gen__btn"
        :class="{ 'gen__btn--processing': exportStatus === 'processing', 'gen__btn--done': exportStatus === 'completed' }"
        :disabled="exportStatus === 'processing' || store.modules.length === 0"
        @click="doExport"
      >
        <template v-if="exportStatus === 'idle' || exportStatus === 'queued' || exportStatus === 'failed'">
          ▶ 生成视频
        </template>
        <template v-else-if="exportStatus === 'processing'">
          <span class="gen__progress" :style="{ width: exportProgress + '%' }" />
          <span class="gen__btn-text">生成中 {{ exportProgress }}%…</span>
        </template>
        <template v-else-if="exportStatus === 'completed'">
          ✓ 查看视频
        </template>
      </button>

      <div class="gen__divider" />

      <!-- ═══ History ═══ -->
      <div class="gen__history">
        <div class="gen__history-title">历史产出</div>
        <div v-if="history.length" class="gen__history-list">
          <div v-for="item in history" :key="item.name" class="gen__history-item">
            <span class="gen__history-name">{{ item.name }}</span>
            <span class="gen__history-size">{{ item.size }}</span>
            <div class="gen__history-actions">
              <button class="gen__history-btn" @click="downloadItem(item)" title="下载">⬇</button>
              <button class="gen__history-btn gen__history-btn--del" @click="deleteItem(item)" title="删除">×</button>
            </div>
          </div>
        </div>
        <div v-else class="gen__history-empty">暂无生成记录</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useProjectStore } from '../stores/project';
import { useWorkbenchStore } from '../stores/workbench';

const store = useProjectStore();
const ws = useWorkbenchStore();

// ── Export state (from workbench store) ──
const exportDownloadUrl = computed(() => ws.exportDownloadUrl);
const exportResolution = computed({
  get: () => ws.exportResolution,
  set: (v) => ws.exportResolution = v,
});
const exportFps = ref(30);
const exportProgress = ref(0);

const exportStatus = computed(() => store.exportStatus);
const totalDuration = computed(() => store.script.metadata.total_duration || 0);

// ── Status helpers ──
const statusLabel = computed(() => {
  const m: Record<string, string> = {
    idle: '等待生成',
    queued: '排队中',
    processing: '正在生成',
    completed: '生成完成',
    failed: '生成失败',
  };
  return m[store.exportStatus] || store.exportStatus;
});
const statusDotClass = computed(() => {
  const m: Record<string, string> = {
    idle: 'gen__status-dot--idle',
    processing: 'gen__status-dot--processing',
    completed: 'gen__status-dot--done',
    failed: 'gen__status-dot--fail',
  };
  return m[store.exportStatus] || '';
});

// ── History ──
interface HistoryItem { name: string; size: string; url?: string; }
const history = ref<HistoryItem[]>([]);

// ── Export: delegate to workbench store ──
function doExport() {
  ws.handleExport();
  // Track progress via polling (handled in store, but we animate locally)
  exportProgress.value = 0;
  const iv = setInterval(() => {
    if (store.exportStatus === 'completed' || store.exportStatus === 'failed') {
      exportProgress.value = store.exportStatus === 'completed' ? 100 : 0;
      // Add to local history when done
      if (store.exportStatus === 'completed' && ws.exportDownloadUrl) {
        const name = ws.exportDownloadUrl.split('/').pop() || 'output.mp4';
        history.value.unshift({ name, size: '—', url: ws.exportDownloadUrl });
      }
      clearInterval(iv);
    } else {
      exportProgress.value = Math.min(95, exportProgress.value + Math.random() * 8);
    }
  }, 2000);
}

function downloadItem(item: HistoryItem) {
  if (item.url) window.open(item.url, '_blank');
}
function deleteItem(item: HistoryItem) {
  history.value = history.value.filter(h => h.name !== item.name);
}
</script>

<style scoped>
.gen {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.gen__body {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

/* ── Preview ── */
.gen__preview {
  width: 100%;
  aspect-ratio: 16/9;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  margin-bottom: 10px;
}
.gen__video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.gen__preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  color: var(--text-muted);
  font-size: 11px;
}

/* ── Status ── */
.gen__info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.gen__status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
}
.gen__status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
}
.gen__status-dot--processing { background: #f0b429; animation: pulse 1.2s ease-in-out infinite; }
.gen__status-dot--done { background: #3fb950; }
.gen__status-dot--fail { background: #f85149; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.gen__eta {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

/* ── Divider ── */
.gen__divider {
  height: 1px;
  background: var(--border);
  margin: 8px 0;
}

/* ── Settings ── */
.gen__settings {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gen__field {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.gen__field-label {
  font-size: 11px;
  color: var(--text-secondary);
}
.gen__select {
  padding: 3px 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 11px;
  outline: none;
  cursor: pointer;
}
.gen__select:focus {
  border-color: var(--accent);
}

/* ── Generate button ── */
.gen__btn {
  position: relative;
  width: 100%;
  padding: 9px 0;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition);
  overflow: hidden;
}
.gen__btn:hover:not(:disabled) {
  background: var(--accent-hover);
}
.gen__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.gen__btn--processing {
  background: var(--bg-surface);
  color: var(--text-primary);
  border: 1px solid var(--border);
}
.gen__btn--done {
  background: #1a7f37;
}
.gen__btn--done:hover {
  background: #238636;
}
.gen__progress {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: var(--accent);
  opacity: 0.15;
  transition: width 0.5s ease;
}
.gen__btn-text {
  position: relative;
  z-index: 1;
}

/* ── History ── */
.gen__history-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.gen__history-list {
  max-height: 120px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.gen__history-item {
  display: flex;
  align-items: center;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  font-size: 10px;
  transition: background var(--transition);
}
.gen__history-item:hover {
  background: var(--bg-hover);
}
.gen__history-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}
.gen__history-size {
  color: var(--text-muted);
  margin: 0 6px;
  flex-shrink: 0;
}
.gen__history-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}
.gen__history-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
  padding: 1px 4px;
  border-radius: 2px;
  transition: background var(--transition);
}
.gen__history-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.gen__history-btn--del:hover {
  color: #f85149;
}
.gen__history-empty {
  font-size: 11px;
  color: var(--text-muted);
  padding: 6px 0;
}
</style>
