<template>
  <div class="workbench" :style="workbenchStyle">
    <!-- ═══ Top bar ═══ -->
    <TopBar
      class="zone zone--topbar"
      @upload="onTopBarUpload"
      @settings="ws.settingsOpen = true"
    />

    <!-- ═══ Material panel (left) ═══ -->
    <aside class="zone zone--material" :style="{ width: leftWidth }">
      <div class="zone__panel" v-show="!leftCollapsed">
        <div class="zone__header">
          <span class="zone__label">素材库</span>
          <button class="zone__collapse" @click="leftCollapsed = true" title="折叠">◀</button>
        </div>
        <div class="zone__body">
          <MaterialPanel :api-base-url="project.apiBaseUrl" />
        </div>
      </div>
      <div class="zone__handle" v-show="leftCollapsed" @click="leftCollapsed = false" title="展开">
        <span class="zone__handle-arrow">▶</span>
        <span class="zone__handle-label">素材</span>
      </div>
    </aside>

    <!-- ═══ Preview (center) ═══ -->
    <main class="zone zone--preview">
      <div class="zone__body">
        <PreviewPanel @upload="onPreviewUpload" />
      </div>
    </main>

    <!-- ═══ Property panel (right) ═══ -->
    <aside class="zone zone--property" :style="{ width: rightWidth }">
      <div class="zone__panel" v-show="!rightCollapsed">
        <div class="zone__header">
          <span class="zone__label">属性</span>
          <button class="zone__collapse" @click="rightCollapsed = true" title="折叠">▶</button>
        </div>
        <div class="zone__body">
          <PropertyPanel />
        </div>
      </div>
      <div class="zone__handle" v-show="rightCollapsed" @click="rightCollapsed = false" title="展开">
        <span class="zone__handle-arrow">◀</span>
        <span class="zone__handle-label">属性</span>
      </div>
    </aside>

    <!-- ═══ Generate panel (far right) ═══ -->
    <aside class="zone zone--generate" :style="{ width: genWidth }">
      <div class="zone__panel" v-show="!genCollapsed">
        <div class="zone__header">
          <span class="zone__label">生成视频</span>
          <button class="zone__collapse" @click="genCollapsed = true" title="折叠">▶</button>
        </div>
        <div class="zone__body">
          <GeneratePanel />
        </div>
      </div>
      <div class="zone__handle" v-show="genCollapsed" @click="genCollapsed = false" title="展开">
        <span class="zone__handle-arrow">◀</span>
        <span class="zone__handle-label">生成</span>
      </div>
    </aside>

    <!-- ═══ Timeline (bottom) ═══ -->
    <footer class="zone zone--timeline">
      <div class="zone__body" style="flex-direction: row;">
        <div style="flex: 1; min-width: 0;"><TimelineBar /></div>
        <div style="width: 280px; flex-shrink: 0; border-left: 1px solid var(--border);"><PreviewPlayer /></div>
      </div>
    </footer>

    <!-- ═══ Settings modal (kept here, rendered by workbench store) ═══ -->
    <Teleport to="body">
      <div v-if="ws.settingsOpen" class="modal-overlay" @click.self="ws.settingsOpen = false">
        <div class="modal">
          <div class="modal__header">
            <h2>设置</h2>
            <button class="modal__close" @click="ws.settingsOpen = false">×</button>
          </div>
          <div class="modal__body">
            <ApiSettingsPanelStatic />
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useProjectStore } from '../stores/project';
import { useWorkbenchStore } from '../stores/workbench';
import TopBar from '../components/TopBar.vue';
import MaterialPanel from '../components/MaterialPanel.vue';
import PreviewPanel from '../components/PreviewPanel.vue';
import PropertyPanel from '../components/PropertyPanel.vue';
import GeneratePanel from '../components/GeneratePanel.vue';
import TimelineBar from '../components/TimelineBar.vue';
import PreviewPlayer from '../components/PreviewPlayer.vue';
import ApiSettingsPanelStatic from '../components/ApiSettingsPanelStatic.vue';

const project = useProjectStore();
const ws = useWorkbenchStore();

// ── Panel collapse state ──
const leftCollapsed = ref(false);
const rightCollapsed = ref(false);
const genCollapsed = ref(false);

const LEFT_FULL = '240px';
const RIGHT_FULL = '300px';
const GEN_FULL = '280px';
const HANDLE_W = '22px';

const leftWidth = computed(() => (leftCollapsed.value ? HANDLE_W : LEFT_FULL));
const rightWidth = computed(() => (rightCollapsed.value ? HANDLE_W : RIGHT_FULL));
const genWidth = computed(() => (genCollapsed.value ? HANDLE_W : GEN_FULL));

const workbenchStyle = computed(() => ({
  '--left-width': leftWidth.value,
  '--right-width': rightWidth.value,
  '--gen-width': genWidth.value,
}));

// ── Wire upload events → workbench store ──
function onTopBarUpload(file: File) {
  ws.doUpload(file);
}
function onPreviewUpload(file: File) {
  ws.doUpload(file);
}
</script>

<style scoped>
/* ═══════════════════════════════════════
   Workbench — 六区容器
   ═══════════════════════════════════════ */

.workbench {
  display: grid;
  grid-template-columns: var(--left-width, 240px) 1fr var(--right-width, 300px) var(--gen-width, 280px);
  grid-template-rows: 48px 1fr 120px;
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
.zone--topbar    { grid-area: topbar; padding: 0; border-right: none; background: transparent; flex-direction: row; align-items: center; }
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
.zone__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.4px;
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

/* ── Panel inner wrapper (visible when not collapsed) ── */
.zone__panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
}

/* ── Handle bar (visible when collapsed) ── */
.zone__handle {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 22px;
  cursor: pointer;
  user-select: none;
  color: var(--text-muted);
  font-size: 10px;
  gap: 4px;
  transition: background var(--transition), color var(--transition);
}
.zone__handle:hover {
  background: var(--bg-hover);
  color: var(--accent);
}
.zone__handle-arrow {
  font-size: 12px;
  line-height: 1;
}
.zone__handle-label {
  writing-mode: vertical-rl;
  font-size: 9px;
  letter-spacing: 1px;
}

/* ── Zone body ── */
.zone__body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ── Timeline body ── */
.zone--timeline .zone__body {
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ═══════════════════════════════════════
   Settings modal (shared styles)
   ═══════════════════════════════════════ */
:global(.modal-overlay) {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center;
}
:global(.modal) {
  background: var(--bg-panel); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  width: 480px; max-height: 80vh; overflow-y: auto;
}
:global(.modal__header) {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--border);
}
:global(.modal__header h2) { font-size: 16px; font-weight: 600; }
:global(.modal__close) {
  width: 28px; height: 28px; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: transparent; color: var(--text-muted); font-size: 16px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
:global(.modal__close:hover) { color: var(--text-primary); }
:global(.modal__body) { padding: 16px 20px; }
</style>
