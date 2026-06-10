<template>
  <div class="mat-panel">
    <div class="mat-content">
      <ScriptPanel />
    </div>
  </div>
</template>

<script setup lang="ts">
import ScriptPanel from './ScriptPanel.vue';
</script>

<style scoped>
.mat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* ── Content ── */
.mat-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

/* ── Script textarea ── */
.mat-script {
  width: 100%;
  height: 100%;
  min-height: 200px;
  padding: 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  resize: none;
  outline: none;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.mat-script:focus {
  box-shadow: inset 0 0 0 1px var(--accent);
}
.mat-script::placeholder {
  color: var(--text-muted);
}
</style>