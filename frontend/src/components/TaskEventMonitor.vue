<template>
  <div class="monitor">
    <div class="monitor__header">
      <span class="monitor__title">任务状态</span>
      <span v-if="connectionLabel" class="monitor__conn" :class="'monitor__conn--' + connType">
        <span class="monitor__dot" /> {{ connectionLabel }}
      </span>
    </div>

    <!-- Tasks -->
    <div class="monitor__tasks">
      <div class="monitor__task" v-if="showAnalysis">
        <div class="monitor__task-icon">
          <span v-if="analysisStatus === 'processing'" class="monitor__spinner" />
          <span v-else-if="analysisStatus === 'completed'" class="monitor__check">✓</span>
          <span v-else-if="analysisStatus === 'failed'" class="monitor__cross">✗</span>
          <span v-else class="monitor__idle">○</span>
        </div>
        <div class="monitor__task-body">
          <div class="monitor__task-name">
            视频分析
            <span class="monitor__task-status" :class="'monitor__task-status--' + analysisStatus">
              {{ analysisLabel }}
            </span>
          </div>
          <div class="monitor__task-bar" v-if="analysisStatus === 'processing'">
            <div class="monitor__task-bar-fill monitor__task-bar-fill--indeterminate" />
          </div>
        </div>
      </div>

      <div class="monitor__task" v-if="showExport">
        <div class="monitor__task-icon">
          <span v-if="exportStatus === 'processing'" class="monitor__spinner" />
          <span v-else-if="exportStatus === 'completed'" class="monitor__check">✓</span>
          <span v-else-if="exportStatus === 'failed'" class="monitor__cross">✗</span>
          <span v-else class="monitor__idle">○</span>
        </div>
        <div class="monitor__task-body">
          <div class="monitor__task-name">
            视频导出
            <span class="monitor__task-status" :class="'monitor__task-status--' + exportStatus">
              {{ exportLabel }}
            </span>
          </div>
          <div class="monitor__task-bar" v-if="exportStatus === 'processing'">
            <div
              class="monitor__task-bar-fill"
              :style="{ width: exportProgress + '%' }"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useProjectStore } from '../stores/project';
import { useWorkbenchStore } from '../stores/workbench';

const store = useProjectStore();
const ws = useWorkbenchStore();

const analysisStatus = computed(() => store.analysisStatus);
const exportStatus = computed(() => store.exportStatus);
const exportProgress = computed(() => ws.exportProgress);
const showAnalysis = computed(() => store.videoId != null);
const showExport = computed(() => store.videoId != null);

const analysisLabel = computed(() => {
  const m: Record<string, string> = {
    idle: '等待', processing: '进行中', completed: '完成', failed: '失败',
  };
  return m[analysisStatus.value] || analysisStatus.value;
});
const exportLabel = computed(() => {
  const m: Record<string, string> = {
    idle: '等待', queued: '排队', processing: '进行中', completed: '完成', failed: '失败',
  };
  return m[exportStatus.value] || exportStatus.value;
});

// ── Connection state (derived from task status) ──
const isActive = computed(() =>
  analysisStatus.value === 'processing' || exportStatus.value === 'processing'
);
const connectionLabel = computed(() => {
  if (!isActive.value) return '';
  if (store.videoId) return '实时推送';
  return '';
});
const connType = computed(() => {
  if (isActive.value) return 'live';
  return '';
});
</script>

<style scoped>
.monitor {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.monitor__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.monitor__title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.monitor__conn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 500;
}
.monitor__conn--live { color: #1a7f37; }
.monitor__conn--fallback { color: #d29922; }
.monitor__dot {
  width: 6px;
  height: 6px;
  border-radius: 10px;
}
.monitor__conn--live .monitor__dot { background: #1a7f37; }
.monitor__conn--fallback .monitor__dot { background: #d29922; animation: pulse 1.5s ease infinite; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.monitor__tasks { padding: 4px 0; }

.monitor__task {
  display: flex;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
}
.monitor__task:last-child { border-bottom: none; }

.monitor__task-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  margin-top: 1px;
}
.monitor__spinner {
  width: 12px; height: 12px;
  border: 2px solid var(--accent-subtle);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.monitor__check { color: #1a7f37; font-weight: 700; }
.monitor__cross { color: #da3633; font-weight: 700; }
.monitor__idle { color: var(--text-muted); }

.monitor__task-body { flex: 1; min-width: 0; }
.monitor__task-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}
.monitor__task-status {
  font-size: 10px;
  font-weight: 400;
}
.monitor__task-status--processing { color: var(--accent); }
.monitor__task-status--completed { color: #1a7f37; }
.monitor__task-status--failed { color: #da3633; }

.monitor__task-bar {
  height: 3px;
  background: var(--border);
  border-radius: 2px;
  margin-top: 4px;
  overflow: hidden;
}
.monitor__task-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.3s ease;
}
.monitor__task-bar-fill--indeterminate {
  width: 30%;
  animation: slide 1.5s ease infinite;
}
@keyframes slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}
</style>
