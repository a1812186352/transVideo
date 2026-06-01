<template>
  <Workbench />
</template>

<script setup lang="ts">
import Workbench from './views/Workbench.vue';
</script>

<style>
/* ── Global reset (kept minimal) ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  font-family: var(--font-sans);
  background: var(--bg-root);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
}
#app { height: 100%; }
</style>
