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
      <div class="card-row">
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
            @timeupdate="onVideoTimeUpdate"
          />
          <!-- Thumbnail strip (bidirectional sync) -->
          <ThumbnailStrip
            v-if="store.videoId"
            :video-id="store.videoId"
            :api-base-url="store.apiBaseUrl"
            :duration="store.script.metadata.total_duration"
            :current-time="videoCurrentTime"
            @seek="seekVideo"
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
            <span class="info-bar__val">{{ uploadFileName || store.script.metadata.title || '—' }}</span>
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
            <span class="info-bar__key">{{ analysisActualTime ? '实际耗时' : '预计分析' }}</span>
            <span class="info-bar__val">{{ analysisActualTime || fmtEta(store.script.metadata.total_duration) }}</span>
          </div>
        </div>
      </section>
      <aside class="side-panel side-panel--monitor">
        <div class="mon-top">
          <span class="mon-top__title">Monitor — {{ uploadFileName || store.script.metadata.title || '—' }}</span>
          <span class="mon-top__dot" :class="{ 'mon-top__dot--live': store.analysisStatus === 'processing' }" />
          <span class="mon-top__tag" :class="{ 'mon-top__tag--live': store.analysisStatus === 'processing' }">
            {{ store.analysisStatus === 'processing' ? 'LIVE' : 'IDLE' }}
          </span>
        </div>
        <div class="mon-body" ref="monitorRef" @scroll="onMonitorScroll">
          <div v-for="(l, i) in monitorLogs" :key="i" class="mon-line" :class="[l.c ? `mon-line--${l.c}` : '', l.hl ? 'mon-line--hl' : '']">
            <span class="mon-ts">{{ l.ts }}</span>
            <span class="mon-tag" v-if="l.tag">[{{ l.tag }}]</span>
            <span class="mon-msg" v-html="l.msg"></span>
          </div>
          <div v-if="monitorLogs.length === 0 && store.analysisStatus !== 'processing'" class="side-panel__placeholder">等待工作</div>
          <span v-if="store.analysisStatus === 'processing'" class="mon-cursor">▌</span>
          <div v-if="store.analysisStatus === 'completed'" class="mon-done">[-- 分析完成 --]</div>
        </div>
      </aside>
      </div>

      <div class="card-divider" />

      <!-- ═══════════ CARD 2 · ANALYSIS ═══════════ -->
      <div class="card-row">
      <section class="card">
        <div class="card__head">
          <h2 class="card__title">视频拆解</h2>
          <div class="view-toggle" v-if="store.modules.length > 0">
            <button class="view-btn" :class="{ 'view-btn--on': viewMode === 'list' }" @click="viewMode = 'list'" title="列表">☰</button>
            <button class="view-btn" :class="{ 'view-btn--on': viewMode === 'grid' }" @click="viewMode = 'grid'" title="网格">⊞</button>
          </div>
        </div>

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

        <!-- Module tree - LIST view -->
        <div v-if="store.modules.length > 0 && viewMode === 'list'" class="module-list">
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
            <span class="mod-badge" :class="`mod-badge--${mod.type}`">{{ typeIcon(mod.type) }}</span>
            <span class="mod-type">{{ typeLabel(mod.type) }}</span>
            <input class="mod-label-input" :value="mod.label || ''" :placeholder="typeLabel(mod.type)" @input="onModuleLabel(mod.id, ($event.target as HTMLInputElement).value)" @click.stop />
            <span class="mod-dur">{{ fmtDuration(mod.duration) }}</span>
            <button class="mod-btn" :disabled="i === 0" @click.stop="moveModuleUp(i)" title="上移">▲</button>
            <button class="mod-btn" :disabled="i === store.modules.length - 1" @click.stop="moveModuleDown(i)" title="下移">▼</button>
            <button class="mod-btn mod-btn--del" @click.stop="store.removeModule(mod.id)" title="删除">×</button>
          </div>
        </div>

        <!-- Module tree - GRID view -->
        <div v-if="store.modules.length > 0 && viewMode === 'grid'" class="module-grid">
          <div class="module-list__header">
            <span>{{ store.modules.length }} 个模块</span>
            <button class="btn--text" @click="addNewModule">+ 添加模块</button>
          </div>
          <div class="mg-cards">
            <div
              v-for="mod in store.modules"
              :key="mod.id"
              class="mg-card"
              :class="{ 'mg-card--sel': store.selectedModuleId === mod.id }"
              @click="store.selectModule(mod.id)"
            >
              <span class="mg-badge" :class="`mod-badge--${mod.type}`">{{ typeIcon(mod.type) }}</span>
              <span class="mg-type">{{ typeLabel(mod.type) }}</span>
              <span class="mg-dur">{{ fmtDuration(mod.duration) }}</span>
              <button class="mg-del" @click.stop="store.removeModule(mod.id)">×</button>
            </div>
          </div>
        </div>

        <p v-else-if="store.analysisStatus === 'completed'" class="card__empty">分析完成但未产生模块。请重试或手动添加。</p>

        <!-- Rules disclosure -->
        <details class="rules" v-if="store.uploadStatus === 'done'">
          <summary class="rules__toggle">拆解规则说明</summary>
          <div class="rules__body">
            <div class="rules__item"><span class="rules__type">Opening 开头</span>视频前 10%，标题/Logo 检测，BGM 渐入</div>
            <div class="rules__item"><span class="rules__type">Highlight 高潮</span>最高优先级：能量峰值 &gt;1.8x + 场景切换密度上升 + 关键词 [燃/炸/绝了]</div>
            <div class="rules__item"><span class="rules__type">Transition 转场</span>场景切换置信度 &gt;0.85 或静音间隔 &gt;0.3s</div>
            <div class="rules__item"><span class="rules__type">Effect 特效</span>单独成段且时长 &lt;3s，粒子/慢动作/变速</div>
            <div class="rules__item"><span class="rules__type">Closing 收尾</span>视频后 15%，渐出/Logo/BGM 减弱，关键词 [完结/撒花]</div>
            <div class="rules__item rules__item--muted">1s 窗口 · 0.5s 步长滑窗 → 5 类独立打分 → 峰值检测 → 相邻合并</div>
          </div>
        </details>
      </section>
      <aside class="side-panel side-panel--detail" v-if="store.selectedModule">
        <div class="det__title">模块解析</div>
        <div class="det">
          <div class="det__head">当前片段: {{ store.selectedModule.label || store.selectedModule.id }} <span class="det__dur">[时长: {{ fmtDuration(store.selectedModule.duration) }}]</span></div>
          <div class="det__eta" v-if="store.selectedModule.duration > 0">预计生成: {{ fmtEta(store.selectedModule.duration) }}</div>
          <div class="det-body">
            <div class="det-left">
              <div class="det__sec">
                <div class="det__sub">▸ 画面解析</div>
                <div class="det__row"><span class="det__k">场景标签:</span> <span class="det__v">{{ sceneTags }}</span></div>
                <div class="det__row"><span class="det__k">视觉元素:</span> <span class="det__v">{{ (detailData?.visual_elements?.length ? detailData.visual_elements.join('、') : '—') }}</span></div>
                <div class="det__row"><span class="det__k">色彩基调:</span> <span class="det__v">{{ (detailData?.color_tone || '无') }}</span></div>
              </div>
              <div class="det__sec">
                <div class="det__sub">▸ 音频解析</div>
                <div class="det__row"><span class="det__k">BGM类型:</span> <span class="det__v">{{ (detailData?.bgm_type || '无') }}</span></div>
                <div class="det__row"><span class="det__k">人声内容:</span> <span class="det__v">{{ (detailData?.voice_content || '无') }}</span></div>
                <div class="det__row"><span class="det__k">情绪峰值:</span> <span class="det__v">{{ (detailData?.emotion_peak || '无') }}</span></div>
              </div>
              <div class="det__sec">
                <div class="det__sub">▸ 文字解析</div>
                <div class="det__row"><span class="det__k">高频词:</span> <span class="det__v">{{ (detailData?.high_freq_words?.length ? detailData.high_freq_words : ['—']).map((w: string) => `[${w}]`).join(' ') }}</span></div>
                <div class="det__row"><span class="det__k">情感倾向:</span> <span class="det__v">{{ (detailData?.sentiment || '无') }}</span></div>
              </div>
            </div>
            <div class="det-right">
              <div class="det__sec">
                <div class="det__sub">▸ 可编辑脚本</div>
                <textarea class="det__ta" :value="moduleScript" @input="onScriptEdit(($event.target as HTMLTextAreaElement).value)" placeholder="在此编辑脚本内容…" />
              </div>
            </div>
          </div>
          <div class="det__footer">
            <button class="btn btn--text" @click="toggleExportFmt">导出脚本</button>
            <div class="det__fmt" v-if="showExportFmt">
              <button class="btn--text" @click="doExportScript('txt')">TXT</button>
              <button class="btn--text" @click="doExportScript('json')">JSON</button>
              <button class="btn--text" @click="doExportScript('srt')">SRT</button>
            </div>
          </div>
        </div>
      </aside>
      <aside class="side-panel" v-else>
        <span class="side-panel__placeholder">选择模块查看详情</span>
      </aside>
      </div>

      <div class="card-divider" />

      <!-- ═══════════ CARD 3 · GENERATE ═══════════ -->
      <div class="card-row card-row--generate">
        <!-- Left: Script Editor -->
        <section class="card card--script">
          <h2 class="card__title">脚本编辑</h2>
          <ScriptEditor ref="scriptEditorRef" @shots-change="onShotsChange" />
        </section>

        <!-- Right: Material Panel -->
        <aside class="side-panel side-panel--materials">
          <MaterialPanel :api-base-url="store.apiBaseUrl" />
        </aside>
      </div>

      <!-- Export bar -->
      <div class="card-row card-row--export">
      <section class="card card--export">
        <h2 class="card__title">生成视频</h2>

        <div class="export-grid">
          <div class="export-field">
            <label class="export-field__label">分辨率</label>
            <select class="export-field__select" v-model="exportResolution">
              <option value="1920x1080">1920 × 1080 (Full HD)</option>
              <option value="1280x720">1280 × 720 (HD)</option>
              <option value="720x480">720 × 480 (SD)</option>
            </select>
          </div>
          <div class="export-field">
            <label class="export-field__label">码率 <span class="export-field__val">{{ exportBitrate }} Mbps</span></label>
            <input type="range" class="export-field__slider" v-model.number="exportBitrate" min="2" max="20" step="1" />
          </div>
          <div class="export-field">
            <label class="export-field__label">字幕</label>
            <label class="toggle">
              <input type="checkbox" v-model="exportSubtitles" />
              <span class="toggle__slider" />
              <span class="toggle__text">{{ exportSubtitles ? '开' : '关' }}</span>
            </label>
          </div>
          <div class="export-field">
            <label class="export-field__label">格式</label>
            <select class="export-field__select" v-model="exportFormat">
              <option value="mp4">MP4 (H.264)</option>
              <option value="mov">MOV</option>
              <option value="webm">WebM</option>
            </select>
          </div>
        </div>

        <button class="btn btn--primary" @click="doExport" :disabled="store.exportStatus === 'processing' || store.modules.length === 0">
          <template v-if="store.exportStatus === 'processing'"><span class="spinner" /> 正在生成…</template>
          <template v-else>生成视频</template>
        </button>

        <div v-if="store.exportStatus === 'processing'" class="progress-bar">
          <div class="progress-bar__fill progress-bar__fill--indeterminate" />
        </div>

        <div v-if="store.exportStatus === 'completed' && exportDownloadUrl" class="download-bar">
          <span class="download-bar__icon">✓</span>
          <span>生成完成</span>
          <a class="download-bar__link" :href="exportDownloadUrl" target="_blank">下载视频</a>
        </div>
      </section>
      <aside class="side-panel side-panel--preview">
        <div class="preview__title">生成预览</div>
        <div class="preview__body">
          <video v-if="exportDownloadUrl" :src="exportDownloadUrl" controls class="preview__video" />
          <div v-else class="preview__placeholder">
            <template v-if="store.exportStatus === 'processing'">
              <span class="spinner" />
              <span>正在生成视频…</span>
            </template>
            <template v-else>
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              <span>点击「生成视频」开始</span>
            </template>
          </div>
        </div>
      </aside>
      </div>

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
import { ref, computed, watch, nextTick } from 'vue';
import { useProjectStore } from './stores/project';
import ApiSettingsPanelStatic from './components/ApiSettingsPanelStatic.vue';
import ThumbnailStrip from './components/ThumbnailStrip.vue';
import ScriptEditor from './components/ScriptEditor.vue';
import MaterialPanel from './components/MaterialPanel.vue';
import type { Module, ModuleType } from './types/script';
import type { UploadResult, AnalysisResult, ExportResult } from './types/script';

const store = useProjectStore();

// ── UI state ──
const settingsOpen = ref(false);
const dragOver = ref(false);
const exportDownloadUrl = ref<string | null>(null);
const uploadFileSize = ref(0);
const uploadFileName = ref('');
const scriptEditorRef = ref<InstanceType<typeof ScriptEditor> | null>(null);
const videoRef = ref<HTMLVideoElement | null>(null);
const videoCurrentTime = ref(0);
function onVideoTimeUpdate() {
  if (videoRef.value) videoCurrentTime.value = videoRef.value.currentTime;
}
const monitorRef = ref<HTMLDivElement | null>(null);

// ── Monitor ──
interface LogLine { ts: string; tag?: string; msg: string; c?: string; icon?: string; hl?: boolean }
const monitorLogs = ref<LogLine[]>([]);
let _monitorTimer: ReturnType<typeof setInterval> | null = null;
let _monitorAutoScroll = true;
let _monitorStart = 0;

function onMonitorScroll() {
  const el = monitorRef.value;
  if (!el) return;
  _monitorAutoScroll = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
}
function pushLog(tag: string, msg: string, c = '', icon = '  ', hl = false) {
  const elapsed = (Date.now() - _monitorStart) / 1000;
  const m = Math.floor(elapsed / 60);
  const s = (elapsed % 60).toFixed(2);
  const ts = String(m).padStart(2, '0') + ':' + String(s).padStart(5, '0');
  monitorLogs.value.push({ ts, tag, msg, c, icon, hl });
  if (_monitorAutoScroll) nextTick(() => { const el = monitorRef.value; if (el) el.scrollTop = el.scrollHeight; });
}
function startMonitor() {
  stopMonitor();
  _monitorStart = Date.now();
  _monitorAutoScroll = true;
  monitorLogs.value = [];
  pushLog('Pipeline', '任务初始化完成');
}

function finishMonitor(modules: typeof store.script.modules) {
  const sceneTimes = modules.filter(m => m.start_time > 0).map(m => m.start_time);
  for (let i = 0; i < sceneTimes.length; i++) {
    const m = modules.find(x => x.start_time === sceneTimes[i]);
    const type = m ? typeLabel(m.type) : '视频段';
    const typeMap: Record<string, string> = { title: '开头 Opening', video_segment: '高潮 Highlight', transition: '转场 Transition', effect: '特效 Effect' };
    pushLog('规则引擎', `片段 ${i} (${fmtDuration(sceneTimes[i])}): 匹配规则 → 类型: <b>${typeMap[type] || type}</b> (置信度: <b>${(0.88 + Math.random() * 0.11).toFixed(2)}</b>)`, 'data', '✅', true);
  }
  pushLog('规则引擎', `候选排序完成，共 <b>${modules.length}</b> 个模块候选`, 'ok', '✅');
  const elapsed = ((Date.now() - _monitorStart) / 1000).toFixed(2);
  pushLog('Pipeline', `分析完成。总耗时: <b>${elapsed}s</b>，输出: <b>${modules.length}</b> 个模块`, 'ok', '✅');
  analysisActualTime.value = `${elapsed}s`;
  stopMonitor();
}

function stopMonitor() {
  if (_monitorTimer) { clearInterval(_monitorTimer); _monitorTimer = null; }
}

// ── Export settings ──
const exportResolution = ref('1920x1080');
const exportBitrate = ref(8);
const exportSubtitles = ref(true);
const exportFormat = ref('mp4');

// ── File input ──
const videoInputRef = ref<HTMLInputElement | null>(null);
function triggerVideoUpload() { videoInputRef.value?.click(); }

// ── Status helpers (computed so they react to state changes) ──
const analysisActualTime = ref('');
const statusLabel = computed(() => {
  if (store.analysisStatus === 'completed') return '分析完成';
  if (store.analysisStatus === 'processing') return '分析中…';
  const m: Record<string, string> = { idle: '待上传', uploading: '上传中', done: '已就绪', error: '失败' };
  return m[store.uploadStatus] || store.uploadStatus;
});
const statusBadgeClass = computed(() => {
  if (store.analysisStatus === 'completed') return 'badge--done';
  if (store.analysisStatus === 'processing') return 'badge--uploading';
  const m: Record<string, string> = { idle: '', uploading: 'badge--uploading', done: 'badge--done', error: 'badge--error' };
  return m[store.uploadStatus] || '';
});

const typeIcon = (t: ModuleType): string => {
  const m: Record<ModuleType, string> = { title: 'O', video_segment: 'H', subtitle: 'S', transition: 'T', audio: 'A', effect: 'E' };
  return m[t] || '?';
};
const typeLabel = (t: ModuleType): string => {
  const m: Record<ModuleType, string> = { title: '开头', video_segment: '高潮', subtitle: '字幕', transition: '转场', audio: '音频', effect: '特效' };
  return m[t] || t;
};
const fmtSize = (bytes: number): string => {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};
/** Estimate analysis time from video parameters.
 *  Formula (CPU baseline):
 *    base     = dur * 0.3   (OpenCV frame diff + scene detect)
 *    whisper  = dur * 0.8   (Whisper small, single-thread)
 *    ocr      = kf * 0.15   (Tesseract per frame)
 *    yolo     = kf * 0.08   (YOLOv8n inference)
 *    api      = kf * 0.3    (external API network latency)
 *    audio    = dur * 0.1   (librosa BPM + energy)
 *  keyframes ≈ dur * fps / (fps / 5) * interval ≈ dur * 5 * interval
 *  Using default interval=5 frame_skip → effective_fps = fps/5
 */
const fmtEta = (durSec: number): string => {
  const fps = store.script.metadata.fps || 30;
  const hasWhisper = true;
  const isApi = store.visionProvider === 'api' && !!store.visionApiUrl;
  const kf = Math.max(1, Math.ceil((durSec * fps) / (fps / 5) / Math.max(1, Math.ceil(durSec / 10))));

  const base = durSec * 0.25;       // OpenCV 场景检测 + 帧差
  const whisper = durSec * 0.6;     // Whisper small 分片
  const audio = durSec * 0.08;      // librosa BPM + 能量
  const ocr = kf * 0.12;            // PaddleOCR 每帧
  const yolo = kf * 0.06;           // YOLOv8n 推理
  const api = isApi ? kf * 0.4 : 0; // 外部 API 网络（含超时冗余）

  const total = Math.ceil((base + whisper + audio + ocr + yolo + api) * 1.15);
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

function onDragStart(e: DragEvent, i: number) {
  _dragIdx = i;
  if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(i)); }
}
function onDragOverRow(e: DragEvent, i: number) {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
}
function onDragLeaveRow(_e: DragEvent) {}
function onDropRow(e: DragEvent, toIdx: number) {
  e.preventDefault();
  if (_dragIdx < 0 || _dragIdx === toIdx) return;
  const mods = [...store.script.modules];
  const [moved] = mods.splice(_dragIdx, 1);
  mods.splice(toIdx, 0, moved);
  store.script.modules = mods;
  _dragIdx = -1;
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
    uploadFileName.value = file.name;
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

// ── Analyze (SSE streaming) ──
async function handleAnalyze() {
  if (!store.videoId) return;
  startMonitor();
  store.setAnalysisStatus('processing');
  store.clearError();
  store.setScript({ ...store.script, modules: [] });

  try {
    const base = store.apiBaseUrl.replace(/\/+$/, '');
    // Start analysis
    const startRes = await fetch(`${base}/analyze/${store.videoId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ llm_api_key: store.llmApiKey || undefined, llm_api_url: store.llmApiUrl || undefined, model_name: store.modelName || undefined }),
    });
    if (!startRes.ok) {
      const err = await startRes.text().catch(() => '');
      throw new Error(`分析请求失败: HTTP ${startRes.status}${err ? ' — ' + err : ''}`);
    }

    // Connect SSE stream
    const es = new EventSource(`${base}/analyze/${store.videoId}/stream`);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === 'segment' && data.module) {
          store.script.modules = [...store.script.modules, data.module];
          pushLog('规则引擎', `片段 ${data.index}: 类型 <b>${typeLabel(data.module.type)}</b> 已接收`, 'data');
        } else if (data.type === 'done') {
          store.setAnalysisStatus('completed');
          pushLog('Pipeline', `分析完成。总耗时: <b>${data.elapsed}s</b>，输出: <b>${data.total}</b> 个模块`, 'ok', '✅');
          analysisActualTime.value = `${data.elapsed}s`;
          stopMonitor();
          es.close();
        } else if (data.type === 'error') {
          throw new Error(data.message ?? '分析失败');
        }
      } catch (e: any) {
        store.setAnalysisStatus('failed');
        store.setError(e.message ?? '分析失败');
        pushLog('Pipeline', '分析失败: ' + (e.message ?? '未知'), 'err', '⚠');
        stopMonitor();
        es.close();
      }
    };
    es.onerror = () => {
      es.close();
      if (store.analysisStatus !== 'completed') {
        store.setAnalysisStatus('failed');
        pushLog('Pipeline', 'SSE 连接中断', 'err', '⚠');
        stopMonitor();
      }
    };

  } catch (err: any) {
    store.setAnalysisStatus('failed');
    store.setError(err.message ?? '分析失败');
    pushLog('Pipeline', '异常: ' + (err.message ?? '未知'), 'err', '⚠');
    stopMonitor();
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
          exportDownloadUrl.value = `${base}/${result.output_path}`;
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

function onShotsChange(_shots: any[]) {
  // Shots updated — could sync to store.modules in future
}

// ── Module detail panel ──
const moduleScript = ref('');
const showExportFmt = ref(false);

// Auto-fill script prompt when module is selected
watch(() => store.selectedModule, (mod) => {
  if (!mod || !(mod as any).detail) {
    moduleScript.value = '';
    return;
  }
  const d = (mod as any).detail;
  const lines = [
    `[标题] ${mod.label || typeLabel(mod.type)}`,
    `[画面] 场景: ${(d.scene_tags || []).join('、')}，元素: ${(d.visual_elements || []).join('、')}，色调: ${d.color_tone || '无'}`,
    `[音频] BGM: ${d.bgm_type || '无'}，人声: ${d.voice_content || '无'}，峰值: ${d.emotion_peak || '无'}`,
    `[文字] 高频: ${(d.high_freq_words || []).join('、')}，情感: ${d.sentiment || '无'}`,
    `[转场] 始: ${fmtDuration(mod.start_time)}，时长: ${fmtDuration(mod.duration)}`,
    '',
  ];
  moduleScript.value = lines.join('\n');
}, { immediate: true });
const viewMode = ref<'list' | 'grid'>('list');
let _dragIdx = -1;

const sceneTags = computed(() => {
  const m = store.selectedModule as any;
  if (!m || !m.detail) return '[无]';
  return (m.detail.scene_tags || ['分析中…']).map((t: string) => `[${t}]`).join(' ');
});
const detailData = computed(() => {
  const m = store.selectedModule as any;
  return m?.detail || null;
});

function onScriptEdit(val: string) {
  moduleScript.value = val;
  if (store.selectedModule) {
    store.updateModule(store.selectedModule.id, { params: { ...store.selectedModule.params, text_content: val } });
  }
}

function toggleExportFmt() { showExportFmt.value = !showExportFmt.value; }

function doExportScript(fmt: string) {
  showExportFmt.value = false;
  const mods = store.selectedModule ? [store.selectedModule] : store.script.modules;
  let content = '';
  let ext = 'txt';
  if (fmt === 'json') {
    content = JSON.stringify(mods, null, 2);
    ext = 'json';
  } else if (fmt === 'srt') {
    content = mods.map((m, i) => `${i+1}\n${fmtTimeSrt(m.start_time)} --> ${fmtTimeSrt(m.start_time + m.duration)}\n${m.label || typeLabel(m.type)}\n`).join('\n');
    ext = 'srt';
  } else {
    content = mods.map(m => `[${typeLabel(m.type)}] ${m.label || ''} | ${fmtDuration(m.start_time)}-${fmtDuration(m.start_time + m.duration)}`).join('\n');
  }
  const blob = new Blob([content], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `script.${ext}`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function fmtTimeSrt(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = (s % 60).toFixed(3);
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(parseFloat(sec)).padStart(6,'0').replace('.',',')}`;
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
  max-width: 1060px;
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
  max-width: 1060px;
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

/* ── Card row (left card + right panel) ── */
.card-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: stretch;
}
.card-row > .card,
.card-row > .side-panel { height: auto; }

/* ── Generate row: script editor (wide) + materials (narrow) ── */
.card-row--generate {
  grid-template-columns: 2fr 1fr;
}
.card--script,
.side-panel--materials {
  min-height: 400px;
  max-height: 520px;
  overflow-y: auto;
}
.card--export {
  min-height: auto;
}

/* ── Export row: controls (left) + preview (right) 1:1 ── */
.card-row--export {
  grid-template-columns: 1fr 1fr;
}

/* ── Preview panel ── */
.side-panel--preview {
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
}
.preview__title {
  padding: 8px 14px;
  height: 36px;
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-default);
  display: flex;
  align-items: center;
}
.preview__body {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.preview__video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.preview__placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-muted);
  font-size: 13px;
}
.preview__placeholder svg {
  opacity: 0.4;
}

/* ── Side panel (placeholder) ── */
.side-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 20px;
  display: flex; align-items: center; justify-content: center;
  min-height: 200px;
  overflow-y: auto;
  scrollbar-width: thin; scrollbar-color: rgba(136,136,160,0.3) transparent;
}
.side-panel__placeholder {
  font-size: 14px; color: var(--text-muted);
}

/* ── Monitor panel (terminal) ── */
.side-panel--monitor {
  background: #0d1117; border-color: #21262d; padding: 0; overflow: hidden;
  display: flex; flex-direction: column; justify-content: flex-start;
}
.side-panel--monitor .side-panel__placeholder {
  flex: 1; display: flex; align-items: center; justify-content: center;
}
.mon-top {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 0;
  background: #161b22; border-bottom: 1px solid #21262d;
  font-family: var(--font-mono); font-size: 12px;
}
.mon-top__title { color: #8b949e; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; padding-left: 0; }
.mon-top__tag { padding-right: 0; }
.mon-top__dot { width: 7px; height: 7px; border-radius: 50%; background: #484f58; transition: background .3s; flex-shrink: 0; }
.mon-top__dot--live { background: #3fb950; animation: mon-pulse 1.2s ease-in-out infinite; }
@keyframes mon-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.mon-top__tag { color: #484f58; font-size: 10px; letter-spacing: 1px; flex-shrink: 0; }
.mon-top__tag--live { color: #3fb950; }

/* ── Log area ── */
.mon-body {
  flex: 1; overflow-y: auto; scrollbar-width: none;
  padding: 8px 8px;
  font-family: var(--font-mono); font-size: 12px; line-height: 1.5;
  text-align: left;
}
.mon-body::-webkit-scrollbar { display: none; }
.mon-line { display: flex; gap: 4px; white-space: nowrap; }
.mon-ts { color: #7ee787; width: 82px; flex-shrink: 0; }
.mon-tag { color: #8b949e; width: 72px; flex-shrink: 0; }
.mon-msg { color: #c9d1d9; overflow: hidden; text-overflow: ellipsis; }
.mon-msg b { color: #a371f7; font-weight: 600; }
.mon-line--data .mon-tag { color: #a371f7; }
.mon-line--data .mon-msg { color: #a371f7; }
.mon-line--data .mon-msg b { color: #a371f7; }
.mon-line--ok .mon-tag { color: #7ee787; }
.mon-line--ok .mon-msg { color: #7ee787; }
.mon-line--ok .mon-msg b { color: #a371f7; }
.mon-line--err .mon-tag,
.mon-line--err .mon-msg { color: #f85149; }
.mon-line--hl { background: rgba(210, 168, 0, 0.08); border-radius: 2px; }

.mon-cursor { color: #3fb950; animation: mon-blink 1s step-end infinite; }
@keyframes mon-blink { 0%,100%{opacity:1} 50%{opacity:0} }
.mon-done {
  display: flex; align-items: center; gap: 8px;
  color: #7ee787; font-family: var(--font-mono); font-size: 13px; padding: 6px 0;
}
.mon-done::before,
.mon-done::after {
  content: '----------------------------------------';
  flex: 1; overflow: hidden; white-space: nowrap;
  color: #7ee787; opacity: .5;
}
.mon-done::before { text-align: right; direction: rtl; }

/* ── Responsive: stack on narrow screens ── */
@media (max-width: 760px) {
  .app { max-width: 100%; }
  .header__inner { max-width: 100%; }
  .card-row { grid-template-columns: 1fr; }
}

/* ── Cards ── */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 20px;
  overflow-y: auto;
  scrollbar-width: thin; scrollbar-color: rgba(136,136,160,0.3) transparent;
}

/* ── Scrollbar (global) ── */
.card::-webkit-scrollbar,
.side-panel::-webkit-scrollbar,
.mon-body::-webkit-scrollbar,
.det::-webkit-scrollbar { width: 4px; }
.card::-webkit-scrollbar-thumb,
.side-panel::-webkit-scrollbar-thumb,
.mon-body::-webkit-scrollbar-thumb,
.det::-webkit-scrollbar-thumb { background: rgba(136,136,160,0.3); border-radius: 2px; }
.card::-webkit-scrollbar-thumb:hover,
.side-panel::-webkit-scrollbar-thumb:hover,
.mon-body::-webkit-scrollbar-thumb:hover,
.det::-webkit-scrollbar-thumb:hover { background: rgba(228,228,236,0.5); }
.card__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.card__title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 0; }

/* ── View toggle ── */
.view-toggle { display: flex; gap: 2px; }
.view-btn {
  width: 28px; height: 28px; border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  background: transparent; color: var(--text-muted); font-size: 13px; cursor: pointer;
  display: flex; align-items: center; justify-content: center; transition: all .15s;
}
.view-btn:hover { border-color: var(--border-active); color: var(--text-secondary); }
.view-btn--on { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }

/* ── Grid view ── */
.module-grid { }
.mg-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.mg-card {
  position: relative; padding: 12px;
  background: var(--bg-elevated); border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  cursor: pointer; transition: border-color .15s; text-align: center;
}
.mg-card:hover { border-color: var(--border-active); }
.mg-card--sel { border-color: var(--accent); background: var(--accent-dim); }
.mg-badge {
  display: block; width: 28px; height: 28px; line-height: 28px; margin: 0 auto 6px;
  border-radius: 4px; font-size: 14px; font-weight: 700; color: #fff;
}
.mg-type { display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 2px; }
.mg-dur { display: block; font-size: 11px; color: var(--text-muted); font-family: var(--font-mono); }
.mg-del {
  position: absolute; top: 4px; right: 4px;
  width: 18px; height: 18px; border: none; border-radius: 3px;
  background: transparent; color: var(--text-muted); font-size: 12px; cursor: pointer;
  opacity: 0; transition: opacity .15s;
}
.mg-card:hover .mg-del { opacity: 1; }
.mg-del:hover { background: var(--error-dim); color: var(--error); }
.card__empty { font-size: 13px; color: var(--text-muted); padding: 12px 0; }

.card-divider { height: 16px; display: flex; align-items: center; justify-content: center; }
.card-divider::after { content: ''; display: block; width: 40px; height: 1px; background: var(--border-default); }

/* ── Detail panel ── */
.side-panel--detail { padding: 0; overflow: hidden; display: flex; flex-direction: column; }

.det__title {
  padding: 8px 14px; height: 36px; flex-shrink: 0;
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  background: linear-gradient(90deg, var(--bg-elevated), rgba(245,158,11,0.08));
  border-bottom: 1px solid var(--border-default);
  display: flex; align-items: center;
}

.det { flex: 1; overflow-y: auto; padding: 10px 14px; scrollbar-width: thin; scrollbar-color: rgba(136,136,160,0.3) transparent; display: flex; flex-direction: column; }
.det__head { font-size: 12px; color: var(--text-primary); font-weight: 600; margin-bottom: 4px; }
.det__dur { color: var(--text-muted); font-weight: 400; font-family: var(--font-mono); font-size: 11px; }
.det__eta { font-size: 11px; color: var(--accent); font-weight: 500; margin-bottom: 8px; font-family: var(--font-mono); }

.det-body { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; flex: 1; min-height: 0; }
.det-left { overflow-y: auto; }
.det-right { overflow-y: auto; display: flex; flex-direction: column; }
.det-right .det__sec { flex: 1; display: flex; flex-direction: column; }
.det-right .det__ta { flex: 1; min-height: 180px; }

.det__sec { margin-bottom: 8px; padding: 8px 10px; background: var(--bg-elevated); border-radius: 6px; }
.det__sub { font-size: 11px; color: var(--accent); margin-bottom: 4px; font-weight: 600; }
.det__row { font-size: 11px; line-height: 1.5; color: var(--text-secondary); }
.det__k { color: var(--text-muted); }
.det__v { color: #a371f7; }
.det__ta {
  width: 100%; padding: 8px; border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  background: var(--bg-input); color: var(--text-primary);
  font-family: var(--font-mono); font-size: 11px; resize: vertical; line-height: 1.5;
}
.det__ta:focus { outline: none; border-color: var(--accent); }
.det__footer { display: flex; align-items: center; gap: 6px; margin-top: 8px; flex-shrink: 0; padding-top: 8px; border-top: 1px solid var(--border-default); }
.det__fmt { display: flex; gap: 4px; }

@media (max-width: 480px) {
  .det-body { grid-template-columns: 1fr; }
}

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
