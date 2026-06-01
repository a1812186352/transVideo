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
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" opacity="0.3">
          <polygon points="5 3 19 12 5 21 5 3" />
        </svg>
        <span>拖入视频或点击上传按钮</span>
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

const store = useProjectStore();

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
  background: var(--bg-surface);
  position: relative;
  overflow: hidden;
  padding: 16px;
}

/* ── Dropzone ── */
.preview__dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  width: 80%;
  max-width: 400px;
  aspect-ratio: 16/9;
  border: 2px dashed var(--border);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition);
  justify-content: center;
}
.preview__dropzone:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-subtle);
}

/* ── Video player ── */
.preview__player {
  position: relative;
  width: 100%;
  max-width: 100%;
  aspect-ratio: 16/9;
  background: #000;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
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
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
  padding: 6px 8px;
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.preview__strip-inner {
  display: flex;
  gap: 4px;
  min-width: max-content;
}
.preview__thumb {
  flex-shrink: 0;
  width: 120px;
  height: 68px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color var(--transition);
  background: var(--bg-surface);
}
.preview__thumb:hover {
  border-color: var(--text-muted);
}
.preview__thumb--active {
  border-color: var(--accent);
}
.preview__thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
</style>
