<template>
  <div
    class="workbench"
    :style="workbenchStyle"
  >
    <!-- ═══ Top bar ═══ -->
    <header class="zone zone--topbar">
      <div class="zone__title">TransVideo</div>
      <div class="zone__center" />
      <div class="zone__actions">
        <button class="zone__btn" @click="toggleTheme" title="切换主题">🌓</button>
        <button class="zone__btn" @click="openSettings" title="设置">⚙</button>
      </div>
    </header>

    <!-- ═══ Material panel (left) ═══ -->
    <aside class="zone zone--material" :style="{ width: leftWidth }">
      <div class="zone__header">
        <span class="zone__label">素材库</span>
        <button class="zone__collapse" @click="leftCollapsed = !leftCollapsed">
          {{ leftCollapsed ? '▶' : '◀' }}
        </button>
      </div>
      <div class="zone__body">
        <slot name="material">
          <div class="zone__placeholder">素材面板</div>
        </slot>
      </div>
    </aside>

    <!-- ═══ Preview (center) ═══ -->
    <main class="zone zone--preview">
      <div class="zone__header">
        <span class="zone__label">预览</span>
      </div>
      <div class="zone__body">
        <slot name="preview">
          <div class="zone__placeholder">预览区域</div>
        </slot>
      </div>
    </main>

    <!-- ═══ Property panel (right) ═══ -->
    <aside class="zone zone--property" :style="{ width: rightWidth }">
      <div class="zone__header">
        <span class="zone__label">属性</span>
        <button class="zone__collapse" @click="rightCollapsed = !rightCollapsed">
          {{ rightCollapsed ? '◀' : '▶' }}
        </button>
      </div>
      <div class="zone__body">
        <slot name="property">
          <div class="zone__placeholder">属性面板</div>
        </slot>
      </div>
    </aside>

    <!-- ═══ Generate panel (far right) ═══ -->
    <aside class="zone zone--generate" :style="{ width: genWidth }">
      <div class="zone__header">
        <span class="zone__label">生成视频</span>
        <button class="zone__collapse" @click="genCollapsed = !genCollapsed">
          {{ genCollapsed ? '◀' : '▶' }}
        </button>
      </div>
      <div class="zone__body">
        <slot name="generate">
          <div class="zone__placeholder">生成面板</div>
        </slot>
      </div>
    </aside>

    <!-- ═══ Timeline (bottom) ═══ -->
    <footer class="zone zone--timeline">
      <div class="zone__header">
        <span class="zone__label">时间线</span>
      </div>
      <div class="zone__body">
        <slot name="timeline">
          <div class="zone__placeholder">时间线区域</div>
        </slot>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';

// ── Panel collapse state ──
const leftCollapsed = ref(false);
const rightCollapsed = ref(false);
const genCollapsed = ref(false);

const LEFT_FULL = '240px';
const RIGHT_FULL = '300px';
const GEN_FULL = '280px';

const leftWidth = computed(() => (leftCollapsed.value ? '0px' : LEFT_FULL));
const rightWidth = computed(() => (rightCollapsed.value ? '0px' : RIGHT_FULL));
const genWidth = computed(() => (genCollapsed.value ? '0px' : GEN_FULL));

const workbenchStyle = computed(() => ({
  '--left-width': leftWidth.value,
  '--right-width': rightWidth.value,
  '--gen-width': genWidth.value,
}));

// ── Theme ──
const toggleTheme = () => (globalThis as any).__toggleTheme?.();
const openSettings = () => (globalThis as any).__openSettings?.();
</script>

<style scoped>
/* ═══════════════════════════════════════
   Workbench — 六区容器
   ═══════════════════════════════════════ */

.workbench {
  display: grid;
  grid-template-columns: var(--left-width, 240px) 1fr var(--right-width, 300px) var(--gen-width, 280px);
  grid-template-rows: 48px 1fr 72px;
  grid-template-areas:
    "topbar   topbar   topbar   topbar"
    "material preview  property generate"
    "timeline timeline timeline timeline";
  height: 100vh;
  background: var(--bg-root);
  color: var(--text-primary);
  font-family: var(--font-sans);
  overflow: hidden;
  transition: grid-template-columns 200ms ease;
}

/* ── Zone base ── */
.zone {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
  transition: width 200ms ease;
}
.zone:last-child {
  border-right: none;
}

/* ── Zone areas ── */
.zone--topbar    { grid-area: topbar; flex-direction: row; align-items: center; background: var(--bg-surface); border-bottom: 1px solid var(--border); padding: 0 12px; }
.zone--material  { grid-area: material; }
.zone--preview   { grid-area: preview; border-right: none; background: var(--bg-root); }
.zone--property  { grid-area: property; }
.zone--generate  { grid-area: generate; }
.zone--timeline  { grid-area: timeline; flex-direction: row; border-top: 1px solid var(--border); background: var(--bg-surface); }

/* ── Zone header ── */
.zone__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 36px;
  padding: 0 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  user-select: none;
}
.zone--topbar .zone__header { display: none; }
.zone--preview .zone__header,
.zone--timeline .zone__header {
  border-bottom: none;
}
.zone__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Collapse button ── */
.zone__collapse {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 10px;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  transition: background var(--transition), color var(--transition);
  flex-shrink: 0;
}
.zone__collapse:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* ── Zone body ── */
.zone__body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

/* ── Zone placeholder ── */
.zone__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 13px;
}

/* ── Top bar specifics ── */
.zone__center {
  flex: 1;
}
.zone__actions {
  display: flex;
  gap: 4px;
}
.zone__btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 15px;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  transition: background var(--transition);
}
.zone__btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* ── Collapsed state ── */
.zone--material:not([style*="width: 0px"]),
.zone--property:not([style*="width: 0px"]),
.zone--generate:not([style*="width: 0px"]) {
  /* visible */;
}
</style>
