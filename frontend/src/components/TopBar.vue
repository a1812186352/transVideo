<template>
  <header class="topbar">
    <!-- Left: Logo -->
    <div class="topbar__logo">
      <span class="topbar__dot"></span>
      transVideo
    </div>

    <!-- Center: Upload button + hidden input -->
    <div class="topbar__center">
      <button class="topbar__upload" @click="triggerUpload">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <span>上传视频</span>
      </button>
      <input ref="fileInput" type="file" accept="video/*" hidden @change="onFileSelected" />
    </div>

    <!-- Right: Actions -->
    <div class="topbar__actions">
      <div class="topbar__theme">
        <button class="topbar__theme-btn" :class="{ active: !isDark }" @click="setTheme('light')">浅色</button>
        <button class="topbar__theme-btn" :class="{ active: isDark }" @click="setTheme('dark')">深色</button>
      </div>
      <button class="topbar__btn topbar__btn--gear" @click="openSettings" title="设置">⚙</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';

const emit = defineEmits<{
  upload: [file: File];
  settings: [];
}>();

const fileInput = ref<HTMLInputElement | null>(null);
const isDark = ref(true);

onMounted(() => {
  isDark.value = document.documentElement.getAttribute('data-theme') !== 'light';
});

function triggerUpload() {
  fileInput.value?.click();
}

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) {
    emit('upload', file);
    input.value = '';
  }
}

function setTheme(theme: string) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
  (globalThis as any).__theme = theme;
  isDark.value = theme === 'dark';
}

function openSettings() {
  emit('settings');
}
</script>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  height: 48px;
  padding: 0 20px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  gap: 16px;
  flex-shrink: 0;
}

/* ── Logo ── */
.topbar__logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  color: var(--accent);
  user-select: none;
  flex-shrink: 0;
}
.topbar__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}

/* ── Center ── */
.topbar__center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ── Upload button ── */
.topbar__upload {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 20px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--transition);
}
.topbar__upload:hover {
  background: var(--accent-hover);
}
.topbar__upload svg { flex-shrink: 0; }

/* ── Actions ── */
.topbar__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

/* ── Segmented theme toggle ── */
.topbar__theme {
  display: flex;
  align-items: center;
  gap: 2px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  padding: 2px;
  border: 1px solid var(--border);
}
.topbar__theme-btn {
  border: none;
  background: transparent;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
  border-radius: 3px;
  color: var(--text-muted);
  transition: all var(--transition);
}
.topbar__theme-btn.active {
  background: var(--bg-panel);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}
.topbar__theme-btn:hover:not(.active) {
  color: var(--text-secondary);
}

/* ── Settings gear ── */
.topbar__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 14px;
  cursor: pointer;
  transition: all var(--transition);
}
.topbar__btn:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}
.topbar__btn--gear:hover {
  transform: rotate(90deg);
}
</style>
