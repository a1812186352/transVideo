<template>
  <Workbench />
</template>

<script setup lang="ts">
import Workbench from './views/Workbench.vue';
</script>

<style>
/* ── Global reset ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  font-family: var(--font-sans); font-size: 13px;
  background: var(--bg-root);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
}
#app { height: 100%; }

/* ── Global scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
