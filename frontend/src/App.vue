<template>
  <div class="app">
    <!-- ==== HEADER ==== -->
    <header class="header">
      <div class="header__inner">
        <div class="header__left">
          <span class="header__logo">◈</span>
          <span class="header__title">transVideo</span>
          <span class="header__badge">v0.5</span>
        </div>
        <div class="header__right">
          <!-- pipeline dots -->
          <div class="header__steps">
            <span class="hstep" :class="{ 'hstep--on': store.uploadStatus === 'done' }" />
            <span class="hstep__line" :class="{ 'hstep__line--on': store.analysisStatus === 'completed' }" />
            <span class="hstep" :class="{ 'hstep--on': store.analysisStatus === 'completed' }" />
            <span class="hstep__line" :class="{ 'hstep__line--on': store.exportStatus === 'completed' }" />
            <span class="hstep" :class="{ 'hstep--on': store.exportStatus === 'completed' }" />
          </div>
          <button class="header__btn" @click="settingsOpen = !settingsOpen" :class="{ 'header__btn--on': settingsOpen }" title="设置">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
      </div>
    </header>

    <!-- ==== ERROR ==== -->
    <div v-if="store.errorMessage" class="error-bar" @click="store.clearError()">
      <span>{{ store.errorMessage }}</span>
      <span class="error-bar__dismiss">×</span>
    </div>

    <!-- Hidden inputs -->
    <input ref="videoInputRef" type="file" accept="video/*" hidden @change="onVideoSelected" />

    <!-- ==== CARDS ==== -->
    <main class="main">
      <!-- ═══════════ CARD 1 · UPLOAD ═══════════ -->
      <section class="card">
        <h2 class="card__title">上传视频</h2>

        <!-- Drop zone (only when idle / error / uploading) -->
        <div
          v-if="store.uploadStatus !== 'done'"
          class="dropzone"
          :class="{ 'dropzone--dragover': dragOver }"
          @click="triggerVideoUpload"
          @dragover.prevent="dragOver = true"
          @dragleave="dragOver = false"
          @drop.prevent="onDrop"
        >
          <svg class="dropzone__icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <span class="dropzone__label">{{ store.uploadStatus === 'uploading' ? '正在上传…' : '拖拽或点击上传视频' }}</span>
          <span class="dropzone__hint" v-if="store.uploadStatus !== 'uploading'">支持 .mp4 .mov .webm，最大 2GB</span>
        </div>

        <!-- Video player (replaces dropzone after upload) -->
        <div v-if="store.uploadStatus === 'done' && store.videoId" class="player">
          <video
            ref="videoRef"
            class="player__video"
            :src="videoSrc"
            controls
            preload="metadata"
          />
          <!-- Timeline markers -->
          <div v-if="markers.length > 0" class="markers">
            <span class="markers__label">分析节点：</span>
            <button
              v-for="m in markers"
              :key="m.time"
              class="marker"
              :class="`marker--${m.type}`"
              @click="seekVideo(m.time)"
              :title="m.label"
            >
              <span class="marker__dot" />
              {{ fmtDuration(m.time) }}
            </button>
          </div>
        </div>

        <!-- Info bar (after upload) -->
        <div class="info-bar" v-if="store.uploadStatus === 'done'">
          <div class="info-bar__item">
            <span class="info-bar__key">文件</span>
            <span class="info-bar__val">{{ store.script.metadata.title || '—' }}</span>
          </div>
          <div class="info-bar__item">
            <span class="info-bar__key">大小</span>
            <span class="info-bar__val">{{ fmtSize(uploadFileSize) }}</span>
          </div>
          <div class="info-bar__item">
            <span class="info-bar__key">时长</span>
            <span class="info-bar__val">{{ fmtDuration(store.script.metadata.total_duration) }}</span>
          </div>
          <div class="info-bar__item">
            <span class="info-bar__key">帧率</span>
            <span class="info-bar__val">{{ store.script.metadata.fps }} fps</span>
          </div>
          <div class="info-bar__item">
            <span class="info-bar__key">分辨率</span>
            <span class="info-bar__val">{{ store.script.metadata.resolution.width }} × {{ store.script.metadata.resolution.height }}</span>
          </div>
          <div class="info-bar__item">
            <span class="info-bar__key">状态</span>
            <span class="info-bar__val" :class="statusBadgeClass">{{ statusLabel }}</span>
          </div>
          <div class="info-bar__item info-bar__item--wide" v-if="store.script.metadata.total_duration > 0">
            <span class="info-bar__key">预计分析</span>
            <span class="info-bar__val">{{ fmtEta(store.script.metadata.total_duration) }}</span>
          </div>
        </div>
      </section>

      <div class="card-divider" />

      <!-- ═══════════ CARD 2 · ANALYSIS ═══════════ -->
      <section class="card">
        <h2 class="card__title">脚本生成</h2>

        <!-- Analyze button -->
        <button class="btn btn--primary" @click="handleAnalyze" :disabled="!store.videoId || store.analysisStatus === 'processing'">
          <template v-if="store.analysisStatus === 'processing'">
            <span class="spinner" /> 正在分析…
          </template>
          <template v-else>开始分析</template>
        </button>

        <!-- Analysis progress -->
        <div v-if="store.analysisStatus === 'processing'" class="progress-bar">
          <div class="progress-bar__fill progress-bar__fill--indeterminate" />
        </div>

        <!-- Module tree -->
        <div v-if="store.modules.length > 0" class="module-list">
          <div class="module-list__header">
            <span>{{ store.modules.length }} 个模块</span>
            <button class="btn--text" @click="addNewModule">+ 添加模块</button>
          </div>

          <div
            v-for="(mod, i) in store.modules"
            :key="mod.id"
            class="module-row"
            :class="{ 'module-row--sel': store.selectedModuleId === mod.id }"
            @click="store.selectModule(mod.id)"
          >
            <!-- Type badge -->
            <span class="mod-badge" :class="`mod-badge--${mod.type}`">{{ typeIcon(mod.type) }}</span>

            <!-- Type label -->
            <span class="mod-type">{{ typeLabel(mod.type) }}</span>

            <!-- Editable label -->
            <input
              class="mod-label-input"
              :value="mod.label || ''"
              :placeholder="typeLabel(mod.type)"
              @input="onModuleLabel(mod.id, ($event.target as HTMLInputElement).value)"
              @click.stop
            />

            <!-- Duration -->
            <span class="mod-dur">{{ fmtDuration(mod.duration) }}</span>

            <!-- Reorder -->
            <button class="mod-btn" :disabled="i === 0" @click.stop="moveModuleUp(i)" title="上移">▲</button>
            <button class="mod-btn" :disabled="i === store.modules.length - 1" @click.stop="moveModuleDown(i)" title="下移">▼</button>

            <!-- Delete -->
            <button class="mod-btn mod-btn--del" @click.stop="store.removeModule(mod.id)" title="删除">×</button>
          </div>
        </div>

        <p v-else-if="store.analysisStatus === 'completed'" class="card__empty">分析完成但未产生模块。请重试或手动添加。</p>

        <!-- Rules disclosure -->
        <details class="rules" v-if="store.uploadStatus === 'done'">
          <summary class="rules__toggle">拆解规则说明</summary>
          <div class="rules__body">
            <div class="rules__item"><span class="rules__type">Hook 片头</span>位于视频前 8 秒</div>
            <div class="rules__item"><span class="rules__type">Talking Head 口播</span>单段连续语音超过 45 秒</div>
            <div class="rules__item"><span class="rules__type">Montage 快剪</span>窗口内出现 2 次以上场景切换</div>
            <div class="rules__item"><span class="rules__type">Conversion 转化</span>画面文字包含 ¥ / 购买 / 扫码 / 咨询等关键词</div>
            <div class="rules__item"><span class="rules__type">Outro 片尾</span>位于视频后 20% 且能量下降</div>
            <div class="rules__item rules__item--muted">不匹配任何规则 → 标记为 Unclassified</div>
          </div>
        </details>
      </section>

      <div class="card-divider" />

      <!-- ═══════════ CARD 3 · EXPORT ═══════════ -->
      <section class="card">
        <h2 class="card__title">生成视频</h2>

        <div class="export-grid">
          <!-- Resolution -->
          <div class="export-field">
            <label class="export-field__label">分辨率</label>
            <select class="export-field__select" v-model="exportResolution">
              <option value="1920x1080">1920 × 1080 (Full HD)</option>
              <option value="1280x720">1280 × 720 (HD)</option>
              <option value="720x480">720 × 480 (SD)</option>
            </select>
          </div>

          <!-- Bitrate -->
          <div class="export-field">
            <label class="export-field__label">码率 <span class="export-field__val">{{ exportBitrate }} Mbps</span></label>
            <input type="range" class="export-field__slider" v-model.number="exportBitrate" min="2" max="20" step="1" />
          </div>

          <!-- Subtitles -->
          <div class="export-field">
            <label class="export-field__label">字幕</label>
            <label class="toggle">
              <input type="checkbox" v-model="exportSubtitles" />
              <span class="toggle__slider" />
              <span class="toggle__text">{{ exportSubtitles ? '开' : '关' }}</span>
            </label>
          </div>

          <!-- Format -->
          <div class="export-field">
            <label class="export-field__label">格式</label>
            <select class="export-field__select" v-model="exportFormat">
              <option value="mp4">MP4 (H.264)</option>
              <option value="mov">MOV</option>
              <option value="webm">WebM</option>
            </select>
          </div>
        </div>

        <!-- Generate button -->
        <button class="btn btn--primary" @click="doExport" :disabled="store.exportStatus === 'processing' || store.modules.length === 0">
          <template v-if="store.exportStatus === 'processing'">
            <span class="spinner" /> 正在生成…
          </template>
          <template v-else>生成视频</template>
        </button>

        <!-- Export progress -->
        <div v-if="store.exportStatus === 'processing'" class="progress-bar">
          <div class="progress-bar__fill progress-bar__fill--indeterminate" />
        </div>

        <!-- Download link -->
        <div v-if="store.exportStatus === 'completed' && exportDownloadUrl" class="download-bar">
          <span class="download-bar__icon">✓</span>
          <span>生成完成</span>
          <a class="download-bar__link" :href="exportDownloadUrl" target="_blank">下载视频</a>
        </div>
      </section>

      <!-- bottom spacer -->
      <div class="main__spacer" />
    </main>

    <!-- ==== SETTINGS MODAL ==== -->
    <div v-if="settingsOpen" class="modal-overlay" @click.self="settingsOpen = false">
      <div class="modal">
        <div class="modal__header">
          <h2>设置</h2>
          <button class="modal__close" @click="settingsOpen = false">×</button>
        </div>
        <div class="modal__body">
          <ApiSettingsPanelStatic />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useProjectStore } from './stores/project';
import ApiSettingsPanelStatic from './components/ApiSettingsPanelStatic.vue';
import type { Module, ModuleType } from './types/script';
import type { UploadResult, AnalysisResult, ExportResult } from './types/script';

const store = useProjectStore();

// ── UI state ──
const settingsOpen = ref(false);
const dragOver = ref(false);
const exportDownloadUrl = ref<string | null>(null);
const uploadFileSize = ref(0);
const videoRef = ref<HTMLVideoElement | null>(null);
// ── Export settings ──
const exportResolution = ref('1920x1080');
const exportBitrate = ref(8);
const exportSubtitles = ref(true);
const exportFormat = ref('mp4');

// ── File input ──
const videoInputRef = ref<HTMLInputElement | null>(null);
function triggerVideoUpload() { videoInputRef.value?.click(); }

// ── Status helpers (computed so they react to state changes) ──
const statusLabel = computed(() => {
  const m: Record<string, string> = { idle: '待上传', uploading: '上传中', done: '已就绪', error: '失败' };
  return m[store.uploadStatus] || store.uploadStatus;
});
const statusBadgeClass = computed(() => {
  const m: Record<string, string> = { idle: '', uploading: 'badge--uploading', done: 'badge--done', error: 'badge--error' };
  return m[store.uploadStatus] || '';
});

const typeIcon = (t: ModuleType): string => {
  const m: Record<ModuleType, string> = { title: 'T', video_segment: 'V', subtitle: 'S', transition: '~', audio: 'A', effect: 'E' };
  return m[t] || '?';
};
const typeLabel = (t: ModuleType): string => {
  const m: Record<ModuleType, string> = { title: '标题', video_segment: '视频', subtitle: '字幕', transition: '转场', audio: '音频', effect: '特效' };
  return m[t] || t;
};
const fmtSize = (bytes: number): string => {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};
const fmtEta = (s: number): string => {
  const total = Math.ceil(s * 1.5);  // ~1.5x realtime on CPU (Whisper bottleneck)
  if (total < 60) return `约 ${total} 秒`;
  const min = Math.floor(total / 60);
  const sec = total % 60;
  return sec > 0 ? `约 ${min} 分 ${sec} 秒` : `约 ${min} 分钟`;
};
const fmtDuration = (s: number): string => {
  if (!s || s <= 0) return '—';
  const min = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${min}:${sec.toString().padStart(2, '0')}`;
};

// ── Module CRUD ──
let _modSeq = 0;
function addNewModule() {
  _modSeq++;
  const mod: Module = {
    id: `mod-${Date.now()}-${_modSeq}`,
    type: 'video_segment',
    label: '',
    start_time: 0,
    duration: 5,
    track_index: 0,
    children: [],
  };
  store.addModule(mod);
  store.selectModule(mod.id);
}

function onModuleLabel(id: string, val: string) {
  store.updateModule(id, { label: val });
}

function moveModuleUp(i: number) {
  if (i <= 0) return;
  const mods = [...store.script.modules];
  [mods[i - 1], mods[i]] = [mods[i], mods[i - 1]];
  store.script.modules = mods;
}
function moveModuleDown(i: number) {
  if (i >= store.script.modules.length - 1) return;
  const mods = [...store.script.modules];
  [mods[i], mods[i + 1]] = [mods[i + 1], mods[i]];
  store.script.modules = mods;
}

// ── Upload ──
function onDrop(e: DragEvent) {
  dragOver.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (!file) return;
  doUpload(file);
}

async function onVideoSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  await doUpload(file);
  input.value = '';
}

async function doUpload(file: File) {
  uploadFileSize.value = file.size;
  store.setUploadStatus('uploading');
  store.clearError();

  try {
    const fd = new FormData();
    fd.append('file', file);

    const base = store.apiBaseUrl.replace(/\/+$/, '');
    const res = await fetch(`${base}/upload/`, { method: 'POST', body: fd });

    if (!res.ok) {
      const err = await res.text().catch(() => '');
      throw new Error(`上传失败: HTTP ${res.status}${err ? ' — ' + err : ''}`);
    }

    const data: UploadResult = await res.json();
    store.setVideoId(data.video_id);
    store.setUploadStatus('done');
    uploadFileSize.value = data.size_bytes || file.size;
    store.setMetadata({
      source_video_id: data.video_id,
      title: file.name,
      total_duration: data.duration ?? 0,
      fps: data.fps ?? 30,
      resolution: { width: data.width ?? 1920, height: data.height ?? 1080 },
    });
  } catch (err: any) {
    store.setUploadStatus('error');
    store.setError(err.message ?? '上传失败');
  }
}

// ── Analyze ──
async function handleAnalyze() {
  if (!store.videoId) return;
  store.setAnalysisStatus('processing');
  store.clearError();

  try {
    const base = store.apiBaseUrl.replace(/\/+$/, '');
    const startRes = await fetch(`${base}/analyze/${store.videoId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ llm_api_key: store.llmApiKey || undefined, llm_api_url: store.llmApiUrl || undefined, model_name: store.modelName || undefined }),
    });

    if (!startRes.ok) {
      const err = await startRes.text().catch(() => '');
      throw new Error(`分析请求失败: HTTP ${startRes.status}${err ? ' — ' + err : ''}`);
    }

    for (let i = 0; i < 300; i++) {
      await sleep(2000);
      const pollRes = await fetch(`${base}/analyze/${store.videoId}`);
      if (!pollRes.ok) throw new Error(`轮询失败: HTTP ${pollRes.status}`);

      const result: AnalysisResult = await pollRes.json();
      if (result.status === 'completed' && result.script) {
        store.setScript(result.script);
        store.setAnalysisStatus('completed');
        return;
      }
      if (result.status === 'failed') throw new Error(result.error ?? '分析失败');
    }
    throw new Error('分析超时');
  } catch (err: any) {
    store.setAnalysisStatus('failed');
    store.setError(err.message ?? '分析失败');
  }
}

// ── Export ──
async function doExport() {
  if (!store.videoId || store.modules.length === 0) return;
  store.setExportStatus('processing');
  store.clearError();
  exportDownloadUrl.value = null;

  // Apply export settings to store metadata
  const [w, h] = exportResolution.value.split('x').map(Number);
  store.setMetadata({ resolution: { width: w, height: h } });

  try {
    const base = store.apiBaseUrl.replace(/\/+$/, '');
    // Inject export params into script
    const scriptToSend = {
      ...store.script,
      metadata: {
        ...store.script.metadata,
        resolution: { width: w, height: h },
      },
    };

    const startRes = await fetch(`${base}/export/${store.videoId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(scriptToSend),
    });

    if (!startRes.ok) {
      const err = await startRes.text().catch(() => '');
      throw new Error(`导出请求失败: HTTP ${startRes.status}${err ? ' — ' + err : ''}`);
    }

    for (let i = 0; i < 600; i++) {
      await sleep(2000);
      const pollRes = await fetch(`${base}/export/${store.videoId}`);
      if (!pollRes.ok) throw new Error(`轮询失败: HTTP ${pollRes.status}`);

      const result: ExportResult = await pollRes.json();
      if (result.status === 'completed') {
        store.setExportStatus('completed');
        if (result.output_path) {
          exportDownloadUrl.value = `${base}${result.output_path}`;
          window.open(exportDownloadUrl.value, '_blank');
        }
        return;
      }
      if (result.status === 'failed') throw new Error(result.error ?? '导出失败');
    }
    throw new Error('导出超时');
  } catch (err: any) {
    store.setExportStatus('failed');
    store.setError(err.message ?? '导出失败');
  }
}

// ── Video ──
const videoSrc = computed(() => {
  if (!store.videoId) return '';
  const base = store.apiBaseUrl.replace(/\/+$/, '');
  return `${base}/upload/video/${store.videoId}`;
});

const markers = computed(() => {
  return store.script.modules
    .filter(m => m.start_time > 0)
    .map(m => ({ time: m.start_time, type: m.type, label: typeLabel(m.type) }))
    .sort((a, b) => a.time - b.time)
    .filter((m, i, arr) => i === 0 || m.time - arr[i - 1].time > 0.5);  // dedup close markers
});

function seekVideo(time: number) {
  if (!videoRef.value) return;
  videoRef.value.currentTime = time;
  videoRef.value.play();
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }
</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');

* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --bg-root: #08080f;
  --bg-surface: #0d0d1a;
  --bg-panel: #111122;
  --bg-elevated: #161630;
  --bg-input: #0a0a18;
  --border-default: #1e1e38;
  --border-active: #2a2a50;
  --accent: #f59e0b;
  --accent-dim: rgba(245, 158, 11, 0.12);
  --text-primary: #e4e4ec;
  --text-secondary: #8888a0;
  --text-muted: #555570;
  --success: #22c55e;
  --success-dim: rgba(34, 197, 94, 0.12);
  --error: #ef4444;
  --error-dim: rgba(239, 68, 68, 0.12);
  --font-mono: 'JetBrains Mono', 'Consolas', 'Fira Code', monospace;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg-root);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
}

#app { min-height: 100vh; }
</style>

<style scoped>
.app {
  max-width: 720px;
  margin: 0 auto;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ── Header ── */
.header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--bg-root);
  border-bottom: 1px solid var(--border-default);
}
.header__inner {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 44px;
  padding: 0 16px;
}
.header__left { display: flex; align-items: center; gap: 8px; }
.header__logo { font-size: 16px; color: var(--accent); }
.header__title { font-size: 14px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.2px; }
.header__badge { font-size: 10px; padding: 1px 6px; border-radius: 10px; background: var(--accent-dim); color: var(--accent); font-family: var(--font-mono); }
.header__right { display: flex; align-items: center; gap: 12px; }

.header__steps { display: flex; align-items: center; gap: 0; }
.hstep { width: 5px; height: 5px; border-radius: 50%; background: var(--border-default); transition: background 0.3s; }
.hstep--on { background: #06b6d4; box-shadow: 0 0 6px #06b6d4; }
.hstep__line { width: 20px; height: 1px; background: var(--border-default); transition: background 0.3s; }
.hstep__line--on { background: #06b6d4; }

.header__btn {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px;
  border: 1px solid transparent; border-radius: var(--radius-sm);
  background: transparent; color: var(--text-muted); cursor: pointer;
  transition: all 0.15s ease;
}
.header__btn:hover { color: var(--text-secondary); border-color: var(--border-default); }
.header__btn:active { transform: scale(0.94); }
.header__btn--on { color: var(--accent); border-color: var(--border-active); background: var(--accent-dim); }

/* ── Error ── */
.error-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 16px;
  background: var(--error-dim); border-bottom: 1px solid rgba(239,68,68,0.2);
  color: #fca5a5; font-size: 12px; cursor: pointer;
}
.error-bar__dismiss { font-size: 16px; color: #f87171; }

/* ── Main ── */
.main { flex: 1; padding: 16px; display: flex; flex-direction: column; gap: 0; }
.main__spacer { height: 32px; }

/* ── Cards ── */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 20px;
}
.card__title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 16px; }
.card__empty { font-size: 13px; color: var(--text-muted); padding: 12px 0; }

.card-divider { height: 16px; display: flex; align-items: center; justify-content: center; }
.card-divider::after { content: ''; display: block; width: 40px; height: 1px; background: var(--border-default); }

/* ── Dropzone ── */
.dropzone {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
  height: 120px;
  border: 2px dashed var(--border-default); border-radius: var(--radius-md);
  cursor: pointer; transition: border-color 0.2s, background 0.2s;
  color: var(--text-muted);
}
.dropzone:hover { border-color: var(--border-active); background: rgba(255,255,255,0.02); }
.dropzone--dragover { border-color: var(--accent); background: var(--accent-dim); }
.dropzone__icon { opacity: 0.5; }
.dropzone__label { font-size: 14px; }
.dropzone__hint { font-size: 11px; color: var(--text-muted); }

/* ── Video player ── */
.player { margin-top: 0; }
.player__video {
  width: 100%; height: auto; max-height: 420px; min-height: 240px;
  border-radius: var(--radius-sm); background: #000; outline: none;
}

/* ── Timeline markers ── */
.markers {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-top: 8px; padding: 8px 12px;
  background: var(--bg-elevated); border-radius: var(--radius-sm);
}
.markers__label { font-size: 11px; color: var(--text-muted); margin-right: 4px; }
.marker {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px; border: 1px solid var(--border-default); border-radius: 12px;
  background: transparent; color: var(--text-secondary);
  font-size: 11px; font-family: var(--font-mono); cursor: pointer;
  transition: all 0.15s ease;
}
.marker:hover { border-color: var(--accent); color: var(--accent); }
.marker__dot {
  width: 6px; height: 6px; border-radius: 50%;
}
.marker--title .marker__dot { background: #f59e0b; }
.marker--video_segment .marker__dot { background: #3b82f6; }
.marker--subtitle .marker__dot { background: #10b981; }
.marker--transition .marker__dot { background: #8b5cf6; }
.marker--effect .marker__dot { background: #ec4899; }

/* ── ETA ── */
.eta {
  font-size: 13px; color: var(--text-secondary); margin-bottom: 12px;
}
.eta__hint { font-size: 11px; color: var(--text-muted); }

/* ── Rules disclosure ── */
.rules { margin-top: 16px; }
.rules__toggle {
  font-size: 12px; color: var(--text-muted); cursor: pointer;
  user-select: none; padding: 4px 0;
}
.rules__toggle:hover { color: var(--text-secondary); }
.rules__body { padding: 8px 0 0 12px; display: flex; flex-direction: column; gap: 6px; }
.rules__item { font-size: 12px; color: var(--text-secondary); }
.rules__type { color: var(--accent); font-weight: 600; margin-right: 4px; }
.rules__item--muted { color: var(--text-muted); font-size: 11px; }

/* ── Info bar ── */
.info-bar {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
  margin-top: 16px; padding: 12px;
  background: var(--bg-elevated); border-radius: var(--radius-sm);
}
.info-bar__item { display: flex; flex-direction: column; gap: 2px; }
.info-bar__key { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
.info-bar__val { font-size: 12px; color: var(--text-secondary); font-family: var(--font-mono); }
.badge--uploading { color: #06b6d4; }
.badge--done { color: var(--success); }
.badge--error { color: var(--error); }

/* ── Buttons ── */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 10px 20px; border: none; border-radius: var(--radius-sm);
  font-size: 13px; font-weight: 600; cursor: pointer;
  transition: all 0.15s ease;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn--primary { background: var(--accent); color: #0d0d1a; }
.btn--primary:hover:not(:disabled) { filter: brightness(1.15); }
.btn--text {
  background: none; border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  color: var(--text-secondary); font-size: 11px; padding: 3px 10px; cursor: pointer;
}
.btn--text:hover { border-color: var(--border-active); color: var(--text-primary); }

/* ── Spinner ── */
.spinner {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid rgba(0,0,0,0.2); border-top-color: #0d0d1a;
  border-radius: 50%; animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Progress ── */
.progress-bar {
  margin-top: 12px; height: 3px; border-radius: 2px; background: var(--border-default); overflow: hidden;
}
.progress-bar__fill--indeterminate {
  width: 40%; height: 100%; background: var(--accent); border-radius: 2px;
  animation: prog-indet 1.5s ease-in-out infinite;
}
@keyframes prog-indet {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

/* ── Module list ── */
.module-list { margin-top: 16px; }
.module-list__header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px; font-size: 12px; color: var(--text-muted);
}

.module-row {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; border-radius: var(--radius-sm);
  border: 1px solid transparent; transition: border-color 0.15s;
}
.module-row:hover { border-color: var(--border-default); }
.module-row--sel { border-color: var(--accent); background: var(--accent-dim); }

.mod-badge {
  width: 20px; height: 20px; border-radius: 3px; display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 700; color: #fff; flex-shrink: 0;
}
.mod-badge--title { background: #f59e0b; }
.mod-badge--video_segment { background: #3b82f6; }
.mod-badge--subtitle { background: #10b981; }
.mod-badge--transition { background: #8b5cf6; }
.mod-badge--audio { background: #ef4444; }
.mod-badge--effect { background: #ec4899; }

.mod-type { font-size: 11px; color: var(--text-secondary); width: 36px; flex-shrink: 0; }
.mod-label-input {
  flex: 1; background: var(--bg-input); border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  padding: 4px 8px; color: var(--text-primary); font-size: 12px; font-family: inherit;
}
.mod-label-input:focus { outline: none; border-color: var(--accent); }
.mod-dur { font-size: 11px; font-family: var(--font-mono); color: var(--text-muted); width: 36px; text-align: right; }

.mod-btn {
  width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  background: transparent; color: var(--text-muted); font-size: 10px; cursor: pointer;
  transition: all 0.12s;
}
.mod-btn:hover:not(:disabled) { border-color: var(--border-active); color: var(--text-primary); }
.mod-btn:disabled { opacity: 0.3; cursor: default; }
.mod-btn--del:hover:not(:disabled) { border-color: var(--error); color: var(--error); }

/* ── Export grid ── */
.export-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.export-field { display: flex; flex-direction: column; gap: 6px; }
.export-field__label { font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 8px; }
.export-field__val { color: var(--text-secondary); font-family: var(--font-mono); font-size: 11px; }
.export-field__select {
  padding: 6px 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  background: var(--bg-input); color: var(--text-primary); font-size: 12px; font-family: inherit;
}
.export-field__select:focus { outline: none; border-color: var(--accent); }
.export-field__slider { accent-color: var(--accent); width: 100%; }

/* ── Toggle ── */
.toggle { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.toggle input { display: none; }
.toggle__slider {
  width: 36px; height: 20px; border-radius: 10px; background: var(--border-default); position: relative; transition: background 0.2s;
}
.toggle__slider::after {
  content: ''; position: absolute; top: 2px; left: 2px;
  width: 16px; height: 16px; border-radius: 50%; background: #555;
  transition: transform 0.2s, background 0.2s;
}
.toggle input:checked + .toggle__slider { background: var(--accent-dim); }
.toggle input:checked + .toggle__slider::after { transform: translateX(16px); background: var(--accent); }
.toggle__text { font-size: 12px; color: var(--text-secondary); }

/* ── Download ── */
.download-bar {
  display: flex; align-items: center; gap: 8px; margin-top: 12px; padding: 12px;
  background: var(--success-dim); border: 1px solid rgba(34,197,94,0.25); border-radius: var(--radius-sm);
  font-size: 13px; color: var(--text-primary);
}
.download-bar__icon { color: var(--success); font-weight: 700; font-size: 16px; }
.download-bar__link { color: var(--accent); font-weight: 600; margin-left: auto; }

/* ── Modal ── */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal {
  width: 400px; max-height: 80vh; overflow-y: auto;
  background: var(--bg-panel); border: 1px solid var(--border-default);
  border-radius: var(--radius-lg); box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}
.modal__header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--border-default);
}
.modal__header h2 { font-size: 16px; font-weight: 600; }
.modal__close {
  width: 28px; height: 28px; border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  background: transparent; color: var(--text-muted); font-size: 16px; cursor: pointer;
  display: flex; align-items: center; justify-content: center; transition: all 0.15s ease;
}
.modal__close:hover { color: var(--text-primary); border-color: var(--border-active); background: var(--bg-elevated); }
.modal__body { padding: 16px 20px; }
</style>
（内容由AI生成，仅供参考）
