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

      <!-- Video info bar -->
      <div v-if="videoId" class="preview__info">
        <span class="preview__info-title">{{ uploadFileName || store.metadata.title || '—' }}</span>
        <span class="preview__info-meta">
          {{ store.metadata.resolution.width }}×{{ store.metadata.resolution.height }}
          · {{ fmtDuration(store.metadata.total_duration) }}
          · {{ store.metadata.fps }}fps
        </span>
      </div>

      <!-- Video player: :key 强制 videoId 变更时重建 -->
      <div v-if="videoId" class="preview__player">
        <video
          :key="videoId"
          ref="videoRef"
          class="preview__video"
          :src="videoSrc"
          controls
          preload="auto"
          @timeupdate="onTimeUpdate"
          @loadedmetadata="onLoadedMeta"
        />
        <!-- Loading overlay (analysis in progress) -->
        <div v-if="analyzing" class="preview__overlay">
          <div class="preview__spinner" />
          <span class="preview__step">{{ currentStep }}</span>
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
import { ref, computed, watch, nextTick } from 'vue';
import { useProjectStore } from '../stores/project';
import { useTimelineStore } from '../stores/timelineStore';
import { usePlaybackStore } from '../stores/playbackStore';
import { frameCache } from '../lib/frameCache';
import { useWorkbenchStore } from '../stores/workbench';

const store = useProjectStore();
const timeline = useTimelineStore();
const playback = usePlaybackStore();
const ws = useWorkbenchStore();

const emit = defineEmits<{
  upload: [file: File];
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
  return `${base}/upload/video/${store.videoId}`;
});
const analyzing = computed(() => store.analysisStatus === 'processing');
const currentStep = computed(() => {
  // Show latest monitor log message as step indicator
  return '正在分析…';
});
const uploadFileName = computed(() => ws.uploadFileName);
const totalDuration = computed(() => store.metadata.total_duration || 0);

const fmtDuration = (s: number): string => {
  if (!s || s <= 0) return '—';
  const min = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  const pad = (n: number) => String(n).padStart(2, '0');
  return min > 0 ? `${min}:${pad(sec)}` : `0:${pad(sec)}`;
};

// ── Thumbnails (generated from video metadata) ──
interface Thumb { time: number; src: string; }
const thumbnails = ref<Thumb[]>([]);

watch(videoId, async (id) => {
  if (!id) {
    thumbnails.value = [];
    frameCache.clear();
    return;
  }
  frameCache.configure(
    store.apiBaseUrl.replace(/\/+$/, ''),
    id,
    store.metadata.fps || 30
  );
  await nextTick();
  generateThumbnails(id);
});

async function generateThumbnails(id: string) {
  const dur = store.metadata.total_duration || 60;
  const count = Math.min(20, Math.floor(dur / 2));
  const interval = Math.max(0.5, dur / count);
  const base = store.apiBaseUrl.replace(/\/+$/, '');
  try {
    const res = await fetch(`${base}/upload/video/${id}/thumbnails?interval=${interval}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data: { timestamp: number; data_uri: string }[] = await res.json();
    thumbnails.value = data.map(t => ({ time: t.timestamp, src: t.data_uri }));
  } catch (e) {
    console.warn('Failed to load thumbnails:', e);
    thumbnails.value = [];
  }
}

// ── Video controls ──
function onTimeUpdate() {
  if (videoRef.value) currentTime.value = videoRef.value.currentTime;
}
function onLoadedMeta() {
  // 视频元数据加载完成后，同步实际分辨率到 store（若后端未返回）
  const v = videoRef.value;
  if (v && (!store.metadata.resolution.width || !store.metadata.resolution.height)) {
    if (v.videoWidth && v.videoHeight) {
      store.metadata.resolution.width = v.videoWidth;
      store.metadata.resolution.height = v.videoHeight;
    }
  }
}
function seekTo(time: number) {
  if (videoRef.value) videoRef.value.currentTime = time;
  playback.seekTo(time);
  frameCache.preload(time, store.metadata.total_duration || 60);
}
function triggerUpload() {
  // Clicking the dropzone triggers the TopBar file input
  (document.querySelector('.topbar__upload') as HTMLButtonElement)?.click();
}

function onDrop(e: DragEvent) {
  dragOver.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file && file.type.startsWith('video/')) {
    emit('upload', file);
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
  flex-direction: column;
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
/* ── Info bar (above player) ── */
.preview__info {
  width: 100%;
  max-width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0 4px;
  flex-shrink: 0;
}
.preview__info-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview__info-meta {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  flex-shrink: 0;
  margin-left: 12px;
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
  max-width: 100%;
  flex: 1;
  min-height: 0;
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
  background: #000;
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
  width: 100%; max-width: 100%;
  display: flex; gap: 4px; overflow-x: auto; padding: 6px 0;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.preview__strip::-webkit-scrollbar { height: 6px; }
.preview__strip::-webkit-scrollbar-thumb { background: var(--text-muted); border-radius: 3px; }
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


</style>
