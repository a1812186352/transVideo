<template>
  <div class="workbench" :class="`workbench--${viewMode}`" :style="workbenchStyle">
    <!-- ═══════════════════════════════════════
         CLASSIC WORKBENCH — 原版六区容器，完全不动
         ═══════════════════════════════════════ -->
    <template v-if="viewMode === 'classic'">
      <TopBar
        class="zone zone--topbar"
        @upload="onTopBarUpload"
        @settings="ws.settingsOpen = true"
      />

      <div class="view-switcher">
        <button class="view-switcher__btn view-switcher__btn--active">经典工作台</button>
        <button class="view-switcher__btn" @click="viewMode = 'migration'">迁移工作台</button>
      </div>

      <aside class="zone zone--material" :style="{ width: leftWidth }">
        <div class="zone__panel" v-show="!leftCollapsed">
          <div class="zone__header">
            <span class="zone__label">脚本</span>
            <button class="zone__collapse" @click="leftCollapsed = true" title="折叠">◀</button>
          </div>
          <div class="zone__body">
            <MaterialPanel :api-base-url="project.apiBaseUrl" />
          </div>
        </div>
        <div class="zone__handle" v-show="leftCollapsed" @click="leftCollapsed = false" title="展开">
          <span class="zone__handle-arrow">▶</span>
          <span class="zone__handle-label">脚本</span>
        </div>
      </aside>

      <main class="zone zone--preview">
        <div class="zone__body"><PreviewPanel @upload="onPreviewUpload" /></div>
      </main>

      <aside class="zone zone--property" :style="{ width: rightWidth }">
        <div class="zone__panel" v-show="!rightCollapsed">
          <div class="zone__header">
            <span class="zone__label">属性</span>
            <button class="zone__collapse" @click="rightCollapsed = true" title="折叠">▶</button>
          </div>
          <div class="zone__body"><PropertyPanel /></div>
        </div>
        <div class="zone__handle" v-show="rightCollapsed" @click="rightCollapsed = false" title="展开">
          <span class="zone__handle-arrow">◀</span>
          <span class="zone__handle-label">属性</span>
        </div>
      </aside>

      <aside class="zone zone--generate" :style="{ width: genWidth }">
        <div class="zone__panel" v-show="!genCollapsed">
          <div class="zone__header">
            <span class="zone__label">生成视频</span>
            <button class="zone__collapse" @click="genCollapsed = true" title="折叠">▶</button>
          </div>
          <div class="zone__body"><GeneratePanel /></div>
        </div>
        <div class="zone__handle" v-show="genCollapsed" @click="genCollapsed = false" title="展开">
          <span class="zone__handle-arrow">◀</span>
          <span class="zone__handle-label">生成</span>
        </div>
      </aside>

      <footer class="zone zone--timeline">
        <div class="zone__body"><TimelineBar /></div>
      </footer>
    </template>

    <!-- ═══════════════════════════════════════
         MIGRATION WORKBENCH — 仿 demo.html 50:50 双栏
         ═══════════════════════════════════════ -->
    <template v-if="viewMode === 'migration'">
      <!-- Top bar: Logo + actions + view switcher -->
      <header class="migration__topbar">
        <div class="migration__logo">trans<span class="migration__logo-accent">Video</span> · 视频拆解与生成工作台</div>
        <div class="view-switcher view-switcher--migration">
          <button class="view-switcher__btn" @click="viewMode = 'classic'">经典工作台</button>
          <button class="view-switcher__btn view-switcher__btn--active">迁移工作台</button>
        </div>
      </header>

      <!-- Main: 50:50 双栏 -->
      <div class="migration__main">
        <!-- ── 左侧：视频拆解 ── -->
        <section class="migration__col migration__col--deconstruct">
          <div class="migration__col-label">视频拆解</div>

          <div class="mg-panel mg-panel--analysis">
            <div class="mg-panel__header">
              <span>结构解析结果</span>
              <span class="mg-panel__badge">5 类 · 11 段</span>
            </div>
            <div class="mg-panel__body">
              <VideoMetaPanel
                :width="videoMeta.width"
                :height="videoMeta.height"
                :fps="videoMeta.fps"
                :codec="videoMeta.codec"
                :video-type="videoMeta.videoType"
                :file-size="videoMeta.fileSize"
              />
              <AnalysisResultPanel
                :modules="analysisModules"
                :total-duration="totalDuration"
                :segment-count="segmentCount"
                :cut-count="0"
              />
            </div>
          </div>

          <div class="mg-panel mg-panel--script">
            <div class="mg-panel__header">
              <span>模块描述</span>
              <span class="mg-panel__hint">各模块发生了什么</span>
            </div>
            <div class="mg-panel__body">
              <ScriptTimelinePanel :modules="analysisModules" @seek="onSeek" />
            </div>
          </div>
        </section>

        <!-- ── 右侧：视频生成 ── -->
        <section class="migration__col migration__col--generate">
          <div class="migration__col-label">视频生成</div>

          <!-- 视频模板（上方） -->
          <div class="mg-panel mg-panel--template">
            <div class="mg-panel__header">
              <span>视频模板</span>
              <span class="mg-panel__hint">选择目标风格</span>
            </div>
            <div class="mg-panel__body">
              <TemplatePanel @select="onTemplateSelect" @migrate="onMigrate" />
            </div>
          </div>

          <!-- 素材栏位（中间） -->
          <div class="mg-panel mg-panel--material">
            <div class="mg-panel__header">
              <span>素材栏位</span>
              <span class="mg-panel__badge">{{ filledSlotCount }} / {{ materialSlots.length }}</span>
            </div>
            <div class="mg-panel__body">
              <MaterialGrid />
            </div>
          </div>

          <!-- 生成预览（下方，自适应） -->
          <div class="mg-panel mg-panel--preview">
            <div class="mg-panel__header">
              <span>生成预览</span>
              <span class="mg-panel__badge" :class="{ 'mg-panel__badge--danger': gapCount > 0 }">
                {{ gapCount > 0 ? `${gapCount} 缺口` : '素材充足' }}
              </span>
              <button class="mg-panel__export-btn" @click="ws.handleExport">导出视频</button>
            </div>
            <div class="mg-panel__body">
              <GenerationPreview
                :slots="genSlots"
                @remove-slot="onRemoveGenSlot"
                @fill-slot="onFillGenSlot"
              />
            </div>
          </div>
        </section>
      </div>

      <!-- Bottom: 迁移状态栏 -->
      <footer class="migration__bottombar">
        <MigrationStatusBar
          :steps="migrationSteps"
          :coverage-percent="coveragePercent"
          :estimated-duration="estimatedDuration"
        />
      </footer>
    </template>

    <!-- ═══ Settings modal ═══ -->
    <Teleport to="body">
      <div v-if="ws.settingsOpen" class="modal-overlay" @click.self="ws.settingsOpen = false">
        <div class="modal">
          <div class="modal__header">
            <h2>设置</h2>
            <button class="modal__close" @click="ws.settingsOpen = false">×</button>
          </div>
          <div class="modal__body"><ApiSettingsPanelStatic /></div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useProjectStore } from '../stores/project';
import { useWorkbenchStore } from '../stores/workbench';
import TopBar from '../components/TopBar.vue';
import MaterialPanel from '../components/MaterialPanel.vue';
import MaterialGrid from '../components/generation/MaterialGrid.vue';
import PreviewPanel from '../components/PreviewPanel.vue';
import PropertyPanel from '../components/PropertyPanel.vue';
import GeneratePanel from '../components/GeneratePanel.vue';
import TimelineBar from '../components/TimelineBar.vue';
import ScriptTimelinePanel from '../components/ScriptTimelinePanel.vue';
import AnalysisResultPanel from '../components/AnalysisResultPanel.vue';
import VideoMetaPanel from '../components/VideoMetaPanel.vue';
import TemplatePanel from '../components/TemplatePanel.vue';
import GenerationPreview from '../components/GenerationPreview.vue';
import MigrationStatusBar from '../components/MigrationStatusBar.vue';
import ApiSettingsPanelStatic from '../components/ApiSettingsPanelStatic.vue';
import type { ScriptModule } from '../components/ScriptTimelinePanel.vue';
import { useMaterialStore } from '../stores/material';

const project = useProjectStore();
const ws = useWorkbenchStore();

// ── View mode ──
const viewMode = ref<'classic' | 'migration'>('classic');

// ── Panel collapse state (classic only) ──
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

// ── Template selection state ──
const templateSelected = ref(false);
function onTemplateSelect(name: string) {
  templateSelected.value = true;
  console.log('Template selected:', name);
}

// ── Structure migration ──
function onMigrate() {
  if (!templateSelected.value) return;
  // Update migration steps to reflect migration triggered
  migrationSteps.value[2].done = true;
  migrationSteps.value[3].done = false;
  console.log('Structure migration triggered');
}

// ── Real data from analysis result ──
import type { Module } from '../types/script';
import { usePlaybackStore } from '../stores/playbackStore';
import { useTimelineStore } from '../stores/timelineStore';
const playback = usePlaybackStore();
const timeline = useTimelineStore();

const analysisModules = computed<ScriptModule[]>(() => {
  // Prefer ws.analysisResult (full REST data), fallback to timeline modules (SSE real-time)
  const src = ws.analysisResult?.script?.modules;
  const fallback = timeline.modules;
  const modules = (src && src.length) ? src : fallback;
  if (!modules?.length) return [];
  return modules.map((mod: Module) => {
    const d = (mod as any).detail || {};
    return {
      name: d.semantic_label || mod.label || mod.type,
      startTime: mod.start_time,
      endTime: mod.start_time + mod.duration,
      description: d.description || buildModuleDesc(mod),
      type: mapModuleType(mod.type, mod.detail),
      // Pass raw detail fields for expandable technical view
      motion: d.motion,
      visualElements: d.visual_elements,
      ocrTexts: d.ocr_texts,
      voiceContent: d.voice_content,
      sceneTags: d.scene_tags,
      emotionPeak: d.emotion_peak,
      bpm: d.bpm,
      bgmType: d.bgm_type,
    };
  });
});

function mapModuleType(modType: string, detail?: Record<string, any>): 'opening' | 'highlight' | 'transition' | 'closing' | 'effect' {
  const m: Record<string, string> = {
    title: 'opening', video_segment: 'highlight', transition: 'transition',
    effect: 'effect',
  };
  const mapped = m[modType];
  if (mapped) return mapped as any;
  const tags = detail?.content_tags;
  if (Array.isArray(tags)) {
    if (tags.some((t: string) => /开头|open/.test(t))) return 'opening';
    if (tags.some((t: string) => /结尾|clos/.test(t))) return 'closing';
    if (tags.some((t: string) => /转场|过/.test(t))) return 'transition';
    if (tags.some((t: string) => /特效|effect/.test(t))) return 'effect';
  }
  return 'highlight';
}

function buildModuleDesc(mod: Module): string {
  const d = (mod as any).detail || {};
  const parts: string[] = [];
  if (Array.isArray(d.content_tags) && d.content_tags.length) {
    parts.push(d.content_tags.slice(0, 2).join(' · '));
  }
  if (d.voice_content && d.voice_content !== '无') {
    const v = String(d.voice_content).slice(0, 30);
    parts.push(`「${v}${v.length >= 30 ? '…' : ''}」`);
  }
  if (d.motion && d.motion !== '无') parts.push(d.motion);
  return parts.join('  ') || '—';
}

const totalDuration = computed(() => project.metadata.total_duration || 0);
const segmentCount = computed(() => analysisModules.value.length);

const videoMeta = computed(() => {
  const sig = ws.analysisResult?.script?.metadata;
  const vt = (ws.analysisResult as any)?.signal_data?.video_type;
  const vtObj = typeof vt === 'object' && vt ? vt : {};
  return {
    width: sig?.resolution?.width || 0,
    height: sig?.resolution?.height || 0,
    fps: sig?.fps || 0,
    codec: (ws.analysisResult as any)?.signal_data?.video_codec || '—',
    videoType: vtObj.video_type || vt || '—',
    fileSize: (ws.analysisResult as any)?.signal_data?.video_file_size
      ? ((ws.analysisResult as any).signal_data.video_file_size / (1024*1024)).toFixed(1) + ' MB'
      : '—',
  };
});

function onSeek(time: number) {
  playback.seekTo(time);
  const video = document.querySelector('.preview__video') as HTMLVideoElement | null;
  if (video) video.currentTime = time;
}

// ── Material grid: driven by creative_pattern ──


// ── Material slots ──
const materialSlots = ref<Array<{ id: string; label: string; file: File | null; tags: string[] }>>([
  { id: '1', label: '槽位 1', file: null, tags: [] },
  { id: '2', label: '槽位 2', file: null, tags: [] },
  { id: '3', label: '槽位 3', file: null, tags: [] },
  { id: '4', label: '槽位 4', file: null, tags: [] },
  { id: '5', label: '槽位 5', file: null, tags: [] },
]);
const filledSlotCount = computed(() => materialSlots.value.filter(s => s.file).length);

// ── Generation preview slots (reactive) ──
const genSlots = ref([
  { name: '标题卡',   startPercent: 0,  widthPercent: 10, status: 'filled' as const },
  { name: '人物引入', startPercent: 10, widthPercent: 12, status: 'filled' as const },
  { name: '动作高燃', startPercent: 22, widthPercent: 18, status: 'filled' as const },
  { name: '商品特写', startPercent: 40, widthPercent: 10, status: 'gap' as const },
  { name: '台词金句', startPercent: 50, widthPercent: 12, status: 'filled' as const },
  { name: '对比',     startPercent: 62, widthPercent: 8,  status: 'fallback' as const },
  { name: '视觉爆发', startPercent: 70, widthPercent: 14, status: 'filled' as const },
  { name: 'CTA',      startPercent: 84, widthPercent: 8,  status: 'filled' as const },
  { name: '品牌露出', startPercent: 92, widthPercent: 8,  status: 'filled' as const },
]);

const gapCount = computed(() => genSlots.value.filter(s => s.status === 'gap' || s.status === 'fallback').length);
const fillCount = computed(() => genSlots.value.filter(s => s.status === 'filled').length);
const coveragePercent = computed(() => Math.round((fillCount.value / genSlots.value.length) * 100));
const estimatedDuration = computed(() => 28);

function onRemoveGenSlot(index: number) {
  genSlots.value.splice(index, 1);
  // Recalculate percentages after removal
  recalcSlotPercents();
}

function onFillGenSlot(index: number, fix: 'reuse' | 'fallback') {
  const slot = genSlots.value[index];
  if (!slot) return;
  if (fix === 'reuse') {
    slot.status = 'fallback';
    slot.name = slot.name + ' (复用)';
  } else {
    slot.status = 'filled';
  }
}

function recalcSlotPercents() {
  const total = genSlots.value.length;
  if (total === 0) return;
  const each = Math.floor(100 / total);
  let acc = 0;
  genSlots.value.forEach((s, i) => {
    s.startPercent = acc;
    s.widthPercent = i === total - 1 ? 100 - acc : each;
    acc += s.widthPercent;
  });
}

// ── AnalysisResultPanel demo data ──


// ── Migration steps ──
const migrationSteps = ref([
  { label: '槽位抽取', done: true },
  { label: '素材匹配', done: true },
  { label: '结构迁移', done: false },
  { label: '缺口补全', done: false },
  { label: '生成导出', done: false },
]);

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
   CLASSIC WORKBENCH — 原版六区容器
   ═══════════════════════════════════════ */

.workbench--classic {
  display: grid;
  grid-template-columns: var(--left-width, 240px) 1fr var(--right-width, 300px) var(--gen-width, 280px);
  grid-template-rows: 48px 36px 1fr 120px;
  grid-template-areas:
    "topbar    topbar    topbar    topbar"
    "switcher  switcher  switcher  switcher"
    "material  preview   property  generate"
    "timeline  timeline  timeline  timeline";
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
.zone:last-child { border-right: none; }

.zone--topbar    { grid-area: topbar; padding: 0; border-right: none; background: transparent; flex-direction: row; align-items: center; }
.zone--material  { grid-area: material; }
.zone--preview   { grid-area: preview; border-right: none; background: var(--bg-root); }
.zone--property  { grid-area: property; }
.zone--generate  { grid-area: generate; }
.zone--timeline  { grid-area: timeline; flex-direction: row; border-top: 1px solid var(--border); background: var(--bg-surface); }

.zone__header {
  display: flex; align-items: center; justify-content: space-between;
  height: 36px; padding: 0 10px; border-bottom: 1px solid var(--border);
  flex-shrink: 0; font-size: 12px; font-weight: 600; color: var(--text-secondary); user-select: none;
}
.zone__label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-transform: uppercase; letter-spacing: 0.4px; }
.zone__collapse {
  background: none; border: none; color: var(--text-muted); cursor: pointer;
  font-size: 10px; padding: 2px 4px; border-radius: var(--radius-sm);
  transition: background var(--transition), color var(--transition); flex-shrink: 0;
}
.zone__collapse:hover { background: var(--bg-hover); color: var(--text-primary); }
.zone__panel { display: flex; flex-direction: column; height: 100%; width: 100%; }
.zone__handle {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; width: 22px; cursor: pointer; user-select: none; color: var(--text-muted);
  font-size: 10px; gap: 4px; transition: background var(--transition), color var(--transition);
}
.zone__handle:hover { background: var(--bg-hover); color: var(--accent); }
.zone__handle-arrow { font-size: 12px; line-height: 1; }
.zone__handle-label { writing-mode: vertical-rl; font-size: 9px; letter-spacing: 1px; }
.zone__body { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.zone--timeline .zone__body { height: 100%; overflow: hidden; }

/* ═══════════════════════════════════════
   View Switcher
   ═══════════════════════════════════════ */

.view-switcher {
  grid-area: switcher;
  display: flex; align-items: center; gap: 6px;
  padding: 0 16px; background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}
.view-switcher--migration {
  grid-area: unset; border-bottom: none; background: transparent; padding: 0; margin-left: 12px; flex-shrink: 0;
}
.view-switcher__btn {
  padding: 3px 12px; font-size: 11px; font-weight: 500;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: transparent; color: var(--text-secondary); cursor: pointer; transition: all var(--transition);
}
.view-switcher__btn:hover { border-color: var(--accent); color: var(--accent); }
.view-switcher__btn--active { background: var(--accent); border-color: var(--accent); color: #fff; }

/* ═══════════════════════════════════════
   MIGRATION WORKBENCH
   ═══════════════════════════════════════ */

.workbench--migration {
  display: flex; flex-direction: column; height: 100vh;
  background: var(--bg-root); color: var(--text-primary); font-family: var(--font-sans); overflow: hidden;
}

.migration__topbar {
  height: 48px; min-height: 48px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; background: var(--bg-panel); border-bottom: 1px solid var(--border);
}
.migration__logo { font-weight: 700; font-size: 15px; letter-spacing: -0.5px; white-space: nowrap; }
.migration__logo-accent { color: var(--accent); }
.migration__actions { display: flex; gap: 8px; align-items: center; }

.mg-btn {
  height: 32px; padding: 0 14px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg-panel);
  color: var(--text-primary); font-size: 12px; cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px;
  transition: all 0.15s; white-space: nowrap;
}
.mg-btn:hover:not(:disabled) { border-color: var(--text-muted); }
.mg-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.mg-btn--primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.mg-btn--primary:hover:not(:disabled) { box-shadow: 0 0 14px rgba(91, 141, 239, 0.15); }
.mg-btn--primary:disabled { background: var(--border); border-color: var(--border); color: var(--text-muted); }
.mg-btn--success { background: var(--slot-closing); border-color: var(--slot-closing); color: #0f1117; font-weight: 600; }

.migration__main {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
  padding: 12px; flex: 1; min-height: 0;
}
.migration__col { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.migration__col-label {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1.5px; color: var(--text-muted); padding: 0 4px; margin-bottom: -4px;
}

/* ── Migration panels ── */
.mg-panel {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 10px; overflow: hidden; display: flex; flex-direction: column; min-height: 0;
}
.mg-panel--analysis { flex: 1; min-height: 0; }
.mg-panel--script   { flex: 1; min-height: 0; }
/* Right column: template (22%) → material (30%) → preview (auto) */
.mg-panel--template { flex: 0 0 22%; }
.mg-panel--material { flex: 0 0 30%; }
.mg-panel--preview  { flex: 1 1 auto; }

.mg-panel__header {
  height: 36px; min-height: 36px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 14px; border-bottom: 1px solid var(--border);
  font-size: 12px; font-weight: 600;
}
.mg-panel__body {
  flex: 1; min-height: 0; overflow: auto; padding: 0;
}
.mg-panel__body::-webkit-scrollbar { width: 4px; }
.mg-panel__body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.mg-panel__badge {
  font-size: 10px; padding: 1px 8px; border-radius: 10px;
  background: rgba(91, 141, 239, 0.12); color: var(--accent);
}
.mg-panel__badge--danger { background: rgba(239, 68, 68, 0.12); color: var(--gap-solid); }
.mg-panel__hint { font-size: 10px; color: var(--text-muted); }

.mg-panel__export-btn {
  min-width: 60px;
  margin-left: auto;
  padding: 3px 12px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid var(--accent);
  border-radius: 4px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  transition: opacity 0.15s;
}
.mg-panel__export-btn:hover { opacity: 0.85; }

.migration__bottombar {
  height: 44px; min-height: 44px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; background: var(--bg-panel); border-top: 1px solid var(--border);
  font-size: 12px; color: var(--text-muted);
}

/* ═══════════════════════════════════════
   Settings modal
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
  width: 28px; height: 28px; border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent; color: var(--text-muted); font-size: 16px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
}
:global(.modal__close:hover) { color: var(--text-primary); }
:global(.modal__body) { padding: 16px 20px; }
</style>