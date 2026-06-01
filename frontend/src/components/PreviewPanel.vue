<template>
  <div class="preview">
    <!-- ═══ Video player area ═══ -->
    <div class="preview__stage">
      <!-- No video: dropzone -->
      <div
        v-if="!videoId"
        class="preview__dropzone"
        @click="triggerUpload"
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop.prevent="onDrop"
      >
        <div class="preview__play-icon"></div>
        <span>拖入视频开始分析</span>
      </div>

      <!-- Video player -->
      <div v-else class="preview__player">
        <video
          ref="videoRef"
          class="preview__video"
          :src="videoSrc"
          controls
          preload="metadata"
          @timeupdate="onTimeUpdate"
        />
        <!-- Loading overlay (analysis in progress) -->
        <div v-if="analyzing" class="preview__overlay">
          <div class="preview__spinner" />
          <span class="preview__step">{{ currentStep }}</span>
        </div>
        <!-- Analyze button (shown after upload, before/during/after analysis) -->
        <div v-if="showAnalyzeBtn" class="preview__actions">
          <button
            class="preview__analyze-btn"
            :class="{
              'preview__analyze-btn--processing': store.analysisStatus === 'processing',
              'preview__analyze-btn--done': store.analysisStatus === 'completed',
              'preview__analyze-btn--fail': store.analysisStatus === 'failed',
            }"
            :disabled="store.analysisStatus === 'processing'"
            @click.stop="ws.handleAnalyze()"
          >
            <template v-if="store.analysisStatus === 'idle'">▶ 开始分析</template>
            <template v-else-if="store.analysisStatus === 'processing'">
              <span class="preview__spinner-sm" /> 分析中…
            </template>
            <template v-else-if="store.analysisStatus === 'completed'">✓ 分析完成</template>
            <template v-else-if="store.analysisStatus === 'failed'">↻ 重试分析</template>
          </button>
          <div v-if="store.analysisStatus === 'completed'" class="preview__eta">
            实际耗时: {{ ws.analysisActualTime || '—' }}
          </div>
          <div v-else-if="store.analysisStatus === 'idle' && totalDuration > 0" class="preview__eta">
            预计分析: {{ ws.fmtEta(totalDuration) }}
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ Thumbnail strip ═══ -->
    <div v-if="videoId" class="preview__strip">
      <div class="preview__strip-inner">
        <div
          v-for="(t, i) in thumbnails"
          :key="i"
          class="preview__thumb"
          :class="{ 'preview__thumb--active': Math.abs(t.time - currentTime) < 0.5 }"
          @click="seekTo(t.time)"
        >
          <img :src="t.src" :alt="`t${i}`" loading="lazy" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useProjectStore } from '../stores/project';
import { useWorkbenchStore } from '../stores/workbench';

const store = useProjectStore();
const ws = useWorkbenchStore();

const emit = defineEmits<{
  upload: [];
}>();

// ── State ──
const videoRef = ref<HTMLVideoElement | null>(null);
const currentTime = ref(0);
const dragOver = ref(false);

// ── Computed ──
const videoId = computed(() => store.videoId);
const videoSrc = computed(() => {
  if (!store.videoId) return '';
  const base = store.apiBaseUrl.replace(/\/+$/, '');
  return `${base}/video/${store.videoId}/stream`;
});
const analyzing = computed(() => store.analysisStatus === 'processing');
const currentStep = computed(() => {
  // Show latest monitor log message as step indicator
  return '正在分析…';
});
const showAnalyzeBtn = computed(() =>
  store.videoId && (store.analysisStatus === 'idle' || store.analysisStatus === 'processing' || store.analysisStatus === 'completed' || store.analysisStatus === 'failed')
);
const totalDuration = computed(() => store.script.metadata.total_duration || 0);

// ── Thumbnails (generated from video metadata) ──
interface Thumb { time: number; src: string; }
const thumbnails = ref<Thumb[]>([]);

watch(videoId, (id) => {
  if (!id) { thumbnails.value = []; return; }
  generateThumbnails(id);
});

function generateThumbnails(id: string) {
  const dur = store.script.metadata.total_duration || 60;
  const count = Math.min(20, Math.floor(dur / 2));
  const base = store.apiBaseUrl.replace(/\/+$/, '');
  const thumbs: Thumb[] = [];
  for (let i = 0; i < count; i++) {
    const t = (dur / count) * i;
    thumbs.push({ time: t, src: `${base}/video/${id}/thumbnail?time=${t.toFixed(1)}` });
  }
  thumbnails.value = thumbs;
}

// ── Video controls ──
function onTimeUpdate() {
  if (videoRef.value) currentTime.value = videoRef.value.currentTime;
}
function seekTo(time: number) {
  if (videoRef.value) videoRef.value.currentTime = time;
  store.seekTo(time);
}
function triggerUpload() { emit('upload'); }

function onDrop(e: DragEvent) {
  dragOver.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file && file.type.startsWith('video/')) {
    // parent handles upload via emit + event
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    const input = document.createElement('input');
    input.type = 'file';
    input.files = dataTransfer.files;
    input.dispatchEvent(new Event('change'));
    emit('upload');
  }
}
</script>

<style scoped>
.preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── Video stage ── */
.preview__stage {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-root);
  position: relative;
  overflow: hidden;
  padding: 16px 24px;
}

/* ── Dropzone ── */
.preview__dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  max-width: 720px;
  aspect-ratio: 16/9;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition);
}
.preview__dropzone:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.preview__dropzone:hover .preview__play-icon {
  border-color: var(--accent);
}
.preview__play-icon {
  width: 40px; height: 40px; border-radius: 50%;
  border: 2px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  transition: border-color var(--transition);
}
.preview__play-icon::after {
  content: ''; display: block;
  width: 0; height: 0;
  border-left: 10px solid var(--accent);
  border-top: 6px solid transparent;
  border-bottom: 6px solid transparent;
  margin-left: 3px;
}

/* ── Video player ── */
.preview__player {
  position: relative;
  width: 100%;
  max-width: 720px;
  aspect-ratio: 16/9;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.preview__video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

/* ── Loading overlay ── */
.preview__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(0, 0, 0, 0.55);
  z-index: 10;
}
.preview__spinner {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(255,255,255,0.15);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.preview__step {
  font-size: 12px;
  color: rgba(255,255,255,0.8);
  font-family: var(--font-mono);
}

/* ── Thumbnail strip ── */
.preview__strip {
  width: 100%; max-width: 720px; margin: 10px auto 0;
  display: flex; gap: 4px; overflow-x: auto; padding: 6px 0;
}
.preview__strip-inner {
  display: flex;
  gap: 4px;
  min-width: max-content;
}
.preview__thumb {
  width: 100px; height: 56px; flex-shrink: 0;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
  transition: all var(--transition);
}
.preview__thumb:hover { border-color: var(--accent); }
.preview__thumb--active { border-color: var(--accent); background: var(--accent-subtle); }
.preview__thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* ── Analyze action bar ── */
.preview__actions {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: linear-gradient(transparent, rgba(0,0,0,0.7));
  z-index: 5;
}
.preview__analyze-btn {
  padding: 7px 18px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition);
  white-space: nowrap;
}
.preview__analyze-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}
.preview__analyze-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.preview__analyze-btn--processing {
  background: var(--bg-surface);
  color: var(--text-primary);
  border: 1px solid var(--border);
}
.preview__analyze-btn--done {
  background: #1a7f37;
}
.preview__analyze-btn--fail {
  background: #da3633;
}
.preview__spinner-sm {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.2);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  vertical-align: middle;
  margin-right: 4px;
}
.preview__eta {
  font-size: 10px;
  color: rgba(255,255,255,0.7);
  font-family: var(--font-mono);
  white-space: nowrap;
}
</style>
