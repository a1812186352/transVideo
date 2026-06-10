<template>
  <div class="eb">
    <slot v-if="!error" />
    <div v-else class="eb__fallback">
      <span class="eb__icon">⚠</span>
      <span class="eb__title">{{ title }} 加载失败</span>
      <span class="eb__msg">{{ errorMsg }}</span>
      <button class="eb__btn" @click="retry">刷新重试</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue';

defineProps<{ title?: string }>();

const error = ref(false);
const errorMsg = ref('');

onErrorCaptured((err) => {
  error.value = true;
  errorMsg.value = (err as Error)?.message || '未知错误';
  return false; // prevent propagation
});

function retry() {
  error.value = false;
  errorMsg.value = '';
  window.location.reload();
}
</script>

<style scoped>
.eb { height: 100%; display: flex; flex-direction: column; }
.eb__fallback {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; padding: 20px; color: var(--text-muted);
}
.eb__icon { font-size: 24px; }
.eb__title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.eb__msg { font-size: 11px; text-align: center; max-width: 240px; }
.eb__btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-surface); color: var(--text-secondary); font-size: 11px; cursor: pointer; }
.eb__btn:hover { background: var(--bg-hover); }
</style>
