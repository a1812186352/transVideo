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
      <button class="mg-btn mg-btn--clear" @click="clearCache" title="清除采样帧与脚本缓存">🗑 清除缓存</button>
        <div class="migration__actions">
          <button class="mg-btn mg-btn--primary" @click="ws.handleAnalyze()"
                  :disabled="!project.videoId || project.analysisStatus === 'processing'">
            {{ project.analysisStatus === 'processing' ? '分析中…' : project.analysisStatus === 'completed' ? '✓ 分析完成' : '分析视频结构' }}
          </button>
          <button class="mg-btn" v-if="project.analysisStatus === 'processing'" @click="ws.cancelAnalysis()">⏹ 停止</button>
          <span v-if="project.analysisStatus === 'completed'" class="mg-status-hint">选择模板后点击「结构迁移」生成蓝图</span>
        </div>
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
              <span class="mg-panel__badge">{{ analysisModules.length }} 段</span>
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

          <!-- 生成蓝图 -->
          <div class="mg-panel mg-panel--preview">
            <div class="mg-panel__header">
              <span>生成蓝图</span>
              <span v-if="blueprintLoading" class="mg-panel__badge">加载中…</span>
              <span v-else-if="blueprint" class="mg-panel__badge">
                {{ blueprint.template.label }} · {{ blueprint.summary.block_count }} 模块
              </span>
              <span v-else class="mg-panel__badge">等待迁移</span>
              <button class="mg-panel__export-btn" @click="ws.handleExport">导出视频</button>
            </div>
            <div class="mg-panel__body">
              <div v-if="blueprint" class="blueprint-track">
                <div v-for="(b, i) in blueprint.blocks" :key="i"
                     class="blueprint-block" :class="'blueprint-block--' + b.status"
                     :style="{ flex: b.duration || 1 }"
                     draggable="true"
                     @dragstart="onBlueprintDragStart(i, $event)"
                     @dragover.prevent="onBlueprintDragOver(i, $event)"
                     @dragend="onBlueprintDragEnd"
                     @drop.prevent="onBlueprintDrop(i, $event)">
                  <span class="blueprint-block__drag" title="拖拽调整顺序">⠿</span>
                  <span class="blueprint-block__name">{{ b.name }}</span>
                  <span class="blueprint-block__time">{{ formatBlockTime(b) }}</span>
                  <span class="blueprint-block__badge">{{ statusLabelBP(b.status) }}</span>
                </div>
                <div v-if="blueprint.summary.required_missing?.length" class="blueprint-warn">
                  ⚠ 缺核心: {{ blueprint.summary.required_missing.join('、') }}
                </div>
              </div>
              <div v-else-if="blueprintLoading" class="gen-preview-placeholder">生成蓝图中…</div>
              <div v-else class="gen-preview-placeholder">选择模板后点击「结构迁移」生成蓝图</div>
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

    <!-- ═══ Toast notification ═══ -->
    <Teleport to="body">
      <div v-if="toastMsg" class="toast">{{ toastMsg }}</div>
    </Teleport>

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
const selectedTemplateName = ref('');
function onTemplateSelect(name: string) {
  templateSelected.value = true;
  selectedTemplateName.value = name;
}

const TEMPLATE_ID_MAP: Record<string, string> = {
  '快节奏混剪': 'mashup', '口播带货': 'shopping_live',
  '产品测评': 'product_review', 'Vlog 叙事': 'talking_head', '其他': 'none',
};

// ── Blueprint state ──
import type { BlueprintResult } from '../types/script';
const toastMsg = ref('');
let toastTimer: ReturnType<typeof setTimeout> | null = null;
function showToast(msg: string) {
  toastMsg.value = msg;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastMsg.value = ''; }, 4000);
}

const blueprint = ref<BlueprintResult | null>(null);
const blueprintLoading = ref(false);

function statusLabelBP(s: string): string {
  const m: Record<string, string> = { matched: '✅', missing: '⚠', passthrough: '⬡' };
  return m[s] || s;
}

function formatBlockTime(b: { start_time?: number; duration?: number }): string {
  const start = typeof b.start_time === 'number' ? b.start_time : 0;
  const dur = typeof b.duration === 'number' ? b.duration : 0;
  return `${start.toFixed(1)}-${(start + dur).toFixed(1)}s`;
}

// ── Blueprint drag-and-drop ──
let _bpDragIdx = -1;
function onBlueprintDragStart(i: number, e: DragEvent) {
  _bpDragIdx = i;
  e.dataTransfer!.effectAllowed = 'move';
}
function onBlueprintDragOver(i: number, _e: DragEvent) {
  if (_bpDragIdx < 0 || _bpDragIdx === i) return;
  if (!blueprint.value) return;
  const blocks = [...blueprint.value.blocks];
  const [moved] = blocks.splice(_bpDragIdx, 1);
  blocks.splice(i, 0, moved);
  let cursor = 0;
  for (const b of blocks) {
    b.start_time = Math.round(cursor * 100) / 100;
    cursor += b.duration;
  }
  blueprint.value = { ...blueprint.value, blocks };
  _bpDragIdx = i;
  // Sync material slots + gen preview
  syncBlueprintToSlots();
}
function onBlueprintDragEnd() { _bpDragIdx = -1; }
function onBlueprintDrop(_i: number, _e: DragEvent) { /* handled by dragOver */ }
function syncBlueprintToSlots() {
  if (!blueprint.value) return;
  materialSlots.value = blueprint.value.blocks.map((b: any, i: number) => ({
    id: `bp-${i}`, label: b.name,
    file: b.status === 'matched' ? { filename: '(复用原视频)' } : (materialSlots.value[i]?.file || null),
  }));
  genSlots.value = blueprint.value.blocks.map((b: any, i: number) => ({
    name: b.name, startPercent: i * (100 / blueprint.value!.blocks.length),
    widthPercent: 100 / blueprint.value!.blocks.length,
    status: b.status === 'matched' ? ('filled' as const) : ('gap' as const),
  }));
}

async function onMigrate() {
function buildFallbackBlueprint(templateType: string): BlueprintResult | null {
  const presets: Record<string, { name: string; key: string; dur: number; required: boolean }[]> = {
    product_review: [
      { name: '片头引语', key: 'opening_intro', dur: 3, required: false },
      { name: '开箱展示', key: 'unboxing', dur: 5, required: false },
      { name: '产品特写', key: 'product_closeup', dur: 6, required: true },
      { name: '使用场景', key: 'usage_scene', dur: 6, required: false },
      { name: '效果对比', key: 'comparison', dur: 4, required: true },
      { name: '优缺点总结', key: 'pros_cons', dur: 4, required: false },
      { name: 'CTA', key: 'cta', dur: 3, required: false },
    ],
    shopping_live: [
      { name: '痛点引入', key: 'pain_point', dur: 3, required: false },
      { name: '商品特写', key: 'product_closeup', dur: 6, required: true },
      { name: '卖点口播', key: 'selling_points', dur: 8, required: true },
      { name: '使用演示', key: 'demo', dur: 6, required: false },
      { name: '价格锚点', key: 'price_anchor', dur: 2, required: false },
      { name: '限时福利', key: 'urgency', dur: 2, required: false },
      { name: 'CTA', key: 'cta', dur: 3, required: false },
    ],
    talking_head: [
      { name: '话题引入', key: 'topic_intro', dur: 3, required: false },
      { name: '长时解说', key: 'long_speech', dur: 15, required: true },
      { name: '观点展开', key: 'viewpoint', dur: 5, required: false },
      { name: '案例佐证', key: 'case_study', dur: 5, required: false },
      { name: '金句收尾', key: 'quote_ending', dur: 3, required: false },
      { name: 'CTA', key: 'cta', dur: 3, required: false },
    ],
    mashup: [
      { name: '节奏引爆', key: 'rhythm_opener', dur: 2, required: false },
      { name: '画面冲击A', key: 'impact_a', dur: 4, required: true },
      { name: '内容过渡', key: 'bridge', dur: 2, required: false },
      { name: '画面冲击B', key: 'impact_b', dur: 4, required: true },
      { name: '情绪堆叠', key: 'emotion_build', dur: 4, required: false },
      { name: '高潮爆发', key: 'climax', dur: 4, required: true },
      { name: 'CTA', key: 'cta', dur: 2, required: false },
    ],
  };
  const preset = presets[templateType];
  if (!preset) return null;
  let cursor = 0;
  const blocks = preset.map(p => {
    const start = cursor; cursor += p.dur;
    return {
      name: p.name, template_key: p.key,
      start_time: Math.round(start * 100) / 100,
      duration: p.dur, status: 'missing' as const,
      required: p.required,
    };
  });
  return {
    template: { type: templateType, label: selectedTemplateName.value || templateType },
    blocks,
    summary: {
      block_count: blocks.length, total_duration: cursor,
      matched: 0, missing: blocks.length, passthrough: 0,
      required_missing: blocks.filter(b => b.required).map(b => b.name),
    },
  };
}

  const type = TEMPLATE_ID_MAP[selectedTemplateName.value] || 'none';
  blueprintLoading.value = true;
  blueprint.value = null;
  try {
    // ── Attempt backend merge ──
    let bpResult: BlueprintResult | null = null;
    if (project.videoId && project.analysisStatus === 'completed') {
      try {
        const base = project.apiBaseUrl.replace(/\/+$/, '');
        const res = await fetch(`${base}/export/blueprint`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ template_type: type, job_id: project.videoId }),
        });
        if (res.ok) {
          const data = await res.json();
          if (data?.blocks?.length && data.summary?.block_count) {
            bpResult = data;
          }
        }
      } catch { /* backend unreachable → fallback */ }
    }

    // ── Fallback: generate from template preset alone ──
    if (!bpResult) {
      bpResult = buildFallbackBlueprint(type);
      showToast(bpResult ? '使用模板预设生成蓝图（未连接后端分析数据）' : '蓝图生成失败');
    }

    if (!bpResult || !bpResult.blocks.length) {
      blueprint.value = null;
      return;
    }

    blueprint.value = bpResult;
    materialSlots.value = bpResult.blocks.map((b: any, i: number) => ({
      id: `bp-${i}`, label: b.name,
      file: b.status === 'matched' ? { filename: '(复用原视频)' } : null,
    }));
    genSlots.value = bpResult.blocks.map((b: any, i: number) => ({
      name: b.name, startPercent: i * (100 / bpResult!.blocks.length),
      widthPercent: 100 / bpResult!.blocks.length,
      status: b.status === 'matched' ? ('filled' as const) : ('gap' as const),
    }));
    showToast(`蓝图已生成：${bpResult.summary.block_count} 模块，${bpResult.summary.matched} 已匹配`);
    migrationSteps.value[2].done = true;
    migrationSteps.value[3].done = false;
  } catch (e) {
    showToast('蓝图生成失败: ' + ((e as any)?.message || ''));
    blueprint.value = null;
  }
  finally { blueprintLoading.value = false; }
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
      description: cleanDescription(d.description || buildModuleDesc(mod)),
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

/**
 * Clean raw module description: deduplicate, remove technical prefixes,
 * convert params to natural language.
 */
function cleanDescription(raw: string): string {
  if (!raw || raw === '—') return '—';

  let desc = raw.trim();

  // 1. Deduplicate: if halves are identical (e.g. "A B A B"), keep only first half
  const mid = Math.floor(desc.length / 2);
  let splitPoint = mid;
  for (let i = mid; i >= 0; i--) {
    if (desc[i] === ' ') { splitPoint = i; break; }
  }
  if (splitPoint > 0) {
    const left = desc.substring(0, splitPoint).trim();
    const right = desc.substring(splitPoint).trim();
    if (left && left === right) desc = left;
  }

  // 2. Strip transition/effect type prefixes (type already shown by colored dot)
  desc = desc
    .replace(/^硬切[·\s]*/, '')
    .replace(/^闪切插入[·\s]*/, '')
    .replace(/^同步淡出[·\s]*/, '')
    .replace(/^交叉溶解[·\s]*/, '')
    .replace(/^淡入淡出[·\s]*/, '')
    .replace(/^黑场过渡[·\s]*/, '')
    .replace(/^白场过渡[·\s]*/, '')
    .replace(/^划像[·\s]*/, '')
    .replace(/^叠化[·\s]*/, '');

  // 3. Convert technical terms → natural language
  desc = desc.replace(/静止定镜/g, '画面静止');
  desc = desc.replace(/镜头拉远\s*[（(]\s*缩小\s*[xX×]\s*([\d.]+)\s*[）)]/g,
    (_: string, val: string) => parseFloat(val) > 2 ? '镜头快速拉远' : '镜头拉远');
  desc = desc.replace(/镜头推进\s*[（(]\s*放大\s*[xX×]\s*([\d.]+)\s*[）)]/g,
    (_: string, val: string) => parseFloat(val) > 2 ? '镜头快速推进' : '镜头推进');
  desc = desc.replace(/缩放\s*[×xX]\s*([\d.]+)/g, (_: string, val: string) => {
    const n = parseFloat(val);
    if (n < 0.95) return '镜头快速拉远';
    if (n > 1.05) return '镜头快速推进';
    return '轻微缩放';
  });
  desc = desc.replace(/画面右移/g, '画面向右移动');
  desc = desc.replace(/画面左移/g, '画面向左移动');
  desc = desc.replace(/画面上移/g, '画面向上移动');
  desc = desc.replace(/画面下移/g, '画面向下移动');

  // 4. Strip trailing technical numeric params (no semantic value for user)
  desc = desc.replace(/\s*\|\s*位移\s*[-+]?\d+\.?\d*\s*(?:px|%)?/g, '');
  desc = desc.replace(/\s*\|\s*光流\s*\d+\.?\d*/g, '');
  desc = desc.replace(/\s*\|\s*旋转\s*[-+]?\d+\.?\d*°/g, '');

  // Clean up: collapse spaces, trim orphan separators
  desc = desc.replace(/\s+/g, ' ').trim();
  desc = desc.replace(/^\s*\|\s*/, '').replace(/\s*\|\s*$/, '');
  // Replace internal pipe separators with readable comma
  desc = desc.replace(/\s*\|\s*/g, '、');

  return desc || '—';
}

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


// ── Gen slots (for blueprint sync) ──
const genSlots = ref<Array<{ name: string; startPercent: number; widthPercent: number; status: 'filled' | 'gap' | 'fallback' }>>([]);

// ── Material slots (writable, populated by blueprint) ──
const materialSlots = ref<Array<{ id: string; label: string; file: { filename: string } | null }>>(
  Array.from({ length: 5 }, (_, i) => ({ id: String(i + 1), label: `槽位 ${i + 1}`, file: null }))
);
const filledSlotCount = computed(() => materialSlots.value.filter(s => s.file).length);

// ── Generation preview slots (derived from analysisModules) ──
const removedSlotIndices = ref(new Set<number>());
const slotStatusOverrides = ref<Record<number, 'filled' | 'gap' | 'fallback'>>({});

const genSlotsDynamic = computed<Array<{ name: string; startPercent: number; widthPercent: number; status: 'filled' | 'gap' | 'fallback'; _origIdx: number }>>(() => {
  const mods = analysisModules.value;
  const total = totalDuration.value || 1;
  if (!mods.length) return [];
  return mods
    .map((mod, i) => ({
      name: mod.name,
      startPercent: Math.round((mod.startTime / total) * 100),
      widthPercent: Math.max(1, Math.round(((mod.endTime - mod.startTime) / total) * 100)),
      status: slotStatusOverrides.value[i] || ('filled' as const),
      _origIdx: i,
    }))
    .filter(s => !removedSlotIndices.value.has(s._origIdx));
});

const gapCount = computed(() => genSlotsDynamic.value.filter(s => s.status === 'gap' || s.status === 'fallback').length);
const fillCount = computed(() => genSlotsDynamic.value.filter(s => s.status === 'filled').length);
const coveragePercent = computed(() => {
  const total = genSlotsDynamic.value.length;
  return total ? Math.round((fillCount.value / total) * 100) : 0;
});
const estimatedDuration = computed(() => 28);

function onRemoveGenSlot(index: number) {
  const slot = genSlotsDynamic.value[index];
  if (slot !== undefined) {
    removedSlotIndices.value = new Set([...removedSlotIndices.value, slot._origIdx]);
  }
}

function onFillGenSlot(index: number, fix: 'reuse' | 'fallback') {
  const slot = genSlotsDynamic.value[index];
  if (!slot) return;
  slotStatusOverrides.value = {
    ...slotStatusOverrides.value,
    [slot._origIdx]: fix === 'reuse' ? 'fallback' : 'filled',
  };
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
function clearCache() {
  timeline.setModules([]);
  timeline.setTracks([]);
  project.setMetadata({ title: '', total_duration: 0, fps: 30, resolution: { width: 0, height: 0 }, source_video_id: '', description: '', author: '', created_at: '', tags: [] } as any);
  project.setVideoId(null);
  project.setUploadStatus('idle');
  project.setAnalysisStatus('idle');
  project.setExportStatus('idle');
  project.clearError();
  ws.monitorLogs.length = 0;
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
.toast {
  position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
  background: #da3633; color: #fff; padding: 8px 20px; border-radius: var(--radius-sm);
  font-size: 12px; z-index: 9999; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  animation: toast-in 0.2s ease;
}
@keyframes toast-in { from { opacity:0; transform: translateX(-50%) translateY(10px); } to { opacity:1; transform: translateX(-50%) translateY(0); } }

.mg-btn--clear {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 11px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition);
}
.mg-btn--clear:hover {
  border-color: #f85149;
  color: #f85149;
}

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
.mg-status-hint { font-size: 11px; color: var(--text-muted); white-space: nowrap; }

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

/* ── Blueprint timeline ── */
.blueprint-track { display: flex; align-items: center; gap: 2px; padding: 6px 8px; height: 100%; overflow-x: auto; }
.blueprint-block {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-width: 60px; border-radius: var(--radius-sm); padding: 4px 8px;
  border: 1px solid var(--border); gap: 2px; flex-shrink: 0; position: relative;
}
.blueprint-block--matched { border-color: #1a7f37; background: #1a7f3710; }
.blueprint-block__drag { font-size: 10px; color: var(--text-muted); cursor: grab; line-height: 1; position: absolute; left: 2px; top: 2px; }
.blueprint-block__drag:active { cursor: grabbing; }
.blueprint-block--missing { border-color: #da3633; background: #da363310; border-style: dashed; }
.blueprint-block--passthrough { border-color: var(--text-muted); background: var(--bg-surface); }
.blueprint-block__name { font-size: 11px; font-weight: 600; color: var(--text-primary); white-space: nowrap; }
.blueprint-block__time { font-size: 9px; color: var(--text-muted); font-family: var(--font-mono); }
.blueprint-block__badge { font-size: 9px; color: var(--text-muted); }
.blueprint-warn { padding: 4px 8px; font-size: 10px; color: #da3633; background: #da363310; flex-shrink: 0; }
.gen-preview-placeholder { display: flex; align-items: center; justify-content: center; height: 100%; font-size: 11px; color: var(--text-muted); }

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