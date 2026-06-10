<template>
  <div class="prop">
    <div class="prop__title">模块解析</div>

    <!-- ═══ Video type selector ═══ -->
    <div class="prop-field" v-if="store.videoId">
      <select class="prop-select" v-model="ws.videoType">
        <option v-for="opt in ws.VIDEO_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
    </div>

    <!-- ═══ Text replacer toggle ═══ -->
    <div class="prop-analyze" v-if="store.videoId">
      <button class="prop-repl-btn" @click="showTextReplacer = !showTextReplacer">
        🔤 批量替换文本
      </button>
    </div>

    <!-- ═══ Analyze button ═══ -->
    <div class="prop-analyze" v-if="store.videoId">
      <button
        class="prop-analyze-btn"
        :class="{
          'prop-analyze-btn--processing': store.analysisStatus === 'processing',
          'prop-analyze-btn--done': store.analysisStatus === 'completed',
          'prop-analyze-btn--fail': store.analysisStatus === 'failed',
        }"
        :disabled="store.analysisStatus === 'processing'"
        @click="ws.handleAnalyze()"
      >
        <template v-if="store.analysisStatus === 'idle' || store.analysisStatus === 'failed'">▶ 开始分析</template>
        <template v-else-if="store.analysisStatus === 'processing'">分析中…</template>
        <template v-else-if="store.analysisStatus === 'completed'">✓ 分析完成</template>
      </button>
    </div>

    <div class="prop__body" v-if="selectedModule">
      <!-- ═══ Scene Tags ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('scene')">场景标签 <span class="prop-group__arrow" :class="{ open: groups.scene }">▼</span></div>
        <div class="prop-group__body" v-show="groups.scene">
          <div v-if="sceneTags.length" class="prop-tags">
            <span v-for="tag in sceneTags" :key="tag" class="prop-tag">{{ tag }}</span>
          </div>
          <span v-else class="prop-empty">等待分析</span>
        </div>
      </div>

      <!-- ═══ Visual Elements ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('visual')">视觉元素 <span class="prop-group__arrow" :class="{ open: groups.visual }">▼</span></div>
        <div class="prop-group__body" v-show="groups.visual">
          <div class="prop-row"><span class="prop-dot comp" /> 构图: {{ safeVal(detail?.composition) }}</div>
          <div class="prop-row"><span class="prop-dot cont" /> 内容: {{ safeVal(detail?.visual_elements) }}</div>
          <div class="prop-row"><span class="prop-dot motion" /> 动效: {{ safeVal(detail?.motion) }}</div>
          <!-- 3c: YOLO quality flag -->
          <div class="prop-row" v-if="detail?.yolo_quality_flag">
            <span class="prop-detect-dot" :class="`detect-${detail.yolo_quality_flag}`" />
            检测质量: {{ qualityLabel(detail.yolo_quality_flag) }}
          </div>
        </div>
      </div>

      <!-- ═══ Color Tone ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('color')">色彩基调 <span class="prop-group__arrow" :class="{ open: groups.color }">▼</span></div>
        <div class="prop-group__body" v-show="groups.color">
          <!-- 3a: HSV zone stacked bar -->
          <div v-if="colorZones.length" class="prop-hsv">
            <div class="prop-hsv__bar">
              <span
                v-for="(z, i) in colorZones"
                :key="i"
                class="prop-hsv__seg"
                :style="{ width: z.pct + '%', background: z.color }"
                :title="z.label + ' ' + z.pct + '%'"
              />
            </div>
            <div class="prop-hsv__labels">
              <span v-for="(z, i) in colorZones" :key="i" class="prop-hsv__lbl">{{ z.label }} {{ z.pct }}%</span>
            </div>
            <!-- neutral hint -->
            <div v-if="detail?.is_dominantly_neutral" class="prop-hsv__hint">画面主体为中性色（白/灰/黑），色调分析仅供参考</div>
          </div>

        </div>
      </div>

      <!-- ═══ Audio Analysis ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('audio')">音频分析 <span class="prop-group__arrow" :class="{ open: groups.audio }">▼</span></div>
        <div class="prop-group__body" v-show="groups.audio">
          <div class="prop-row">BPM: {{ safeVal(detail?.bpm) }} · 类型: {{ safeVal(detail?.bgm_type) }}</div>
          <!-- 3b: Mood tag -->
          <div v-if="detail?.mood" class="prop-mood">
            <span class="prop-mood__tag">{{ moodLabel(detail.mood) }}</span>
            <span v-if="detail.mood_confidence" class="prop-mood__conf">
              <span class="prop-mood__bar" :style="{ width: (detail.mood_confidence * 100) + '%' }" />
            </span>
            <span v-if="detail.mood_secondary" class="prop-mood__sec">次情绪: {{ moodLabel(detail.mood_secondary) }}</span>
          </div>
          <AudioWaveform
            v-if="detail?.energy_curve?.length"
            :energy-curve="detail.energy_curve"
            :duration="selectedModule?.duration || (detail.original_end - detail.original_start) || 5"
            :start-time="selectedModule?.start_time ?? detail.original_start ?? 0"
            :current-time="playback.currentTime"
            :bpm="detail?.bpm"
            :mood-labels="waveMoods"
            @seek="playback.seekTo"
          />
        </div>
      </div>

      <!-- ═══ Text Analysis ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('text')">文字解析 <span class="prop-group__arrow" :class="{ open: groups.text }">▼</span></div>
        <div class="prop-group__body" v-show="groups.text">
          <div v-if="ocrItems.length" class="prop-ocr">
            <div v-for="(t, i) in ocrItems" :key="i" class="prop-ocr__line" :class="{ 'prop-ocr__low': t.lowConfidence }">
              <span :class="['prop-ocr__text', sizeClass(t.sizeRank)]">{{ t.text }}</span>
              <span v-if="t.sizeRank" class="prop-ocr__badge" :class="`badge--${t.sizeRank}`">{{ sizeLabel(t.sizeRank) }}</span>
            </div>
          </div>
          <span v-else class="prop-empty">等待分析</span>
        </div>
      </div>
    </div>

    <!-- No selection -->
    <div v-else class="prop__empty">
      <span>选择模块查看详情</span>
    </div>
  </div>


  <!-- ═══ 创作特征 — Deconstructor 全片维度分析 ═══ -->
  <div class="prop-creative" v-if="creative">
    <div class="prop-group">
      <div class="prop-group__head" @click="toggleCreative = !toggleCreative">
        创作特征 <span class="prop-group__arrow" :class="{ open: toggleCreative }">▼</span>
      </div>
      <div class="prop-group__body" v-show="toggleCreative">

        <div class="prop-dense-title">镜头节奏</div>
        <div v-if="creative.shot_rhythm?.shot_count != null" class="prop-creative__zone">
          <div class="prop-row">节奏: <b>{{ creative.shot_rhythm.rhythm_pattern || '—' }}</b></div>
          <div class="prop-row">镜头数: {{ creative.shot_rhythm.shot_count }}</div>
          <div class="prop-row" v-if="creative.shot_rhythm.avg_shot_duration">平均: {{ creative.shot_rhythm.avg_shot_duration.toFixed(1) }}s</div>
          <div v-if="creative.shot_rhythm.duration_distribution?.length" class="prop-hist">
            <div v-for="(v, i) in creative.shot_rhythm.duration_distribution.slice(0,12)" :key="i"
                 class="prop-hist__bar" :style="{ height: Math.max(4, v * 60) + 'px' }" />
          </div>
        </div>
        <div v-else class="prop-row" style="color:var(--text-muted)">—</div>

        <div class="prop-dense-title">字幕风格</div>
        <div v-if="creative.subtitle_style?.available !== false && creative.subtitle_style" class="prop-creative__zone">
          <div class="prop-row">密度: {{ creative.subtitle_style.density?.toFixed(2) || '—' }}</div>
          <div class="prop-row" v-if="creative.subtitle_style.avg_appear_duration">平均时长: {{ creative.subtitle_style.avg_appear_duration.toFixed(1) }}s</div>
          <div v-if="creative.subtitle_style.top_positions?.length" class="prop-tags" style="margin-top:2px">
            <span v-for="p in creative.subtitle_style.top_positions" :key="p" class="prop-tag">{{ p }}</span>
          </div>
        </div>
        <div v-else class="prop-row" style="color:var(--text-muted)">—</div>

        <div class="prop-dense-title">视觉风格</div>
        <div v-if="creative.visual_packaging?.available !== false && creative.visual_packaging" class="prop-creative__zone">
          <div class="prop-row">主色调: <b>{{ creative.visual_packaging.dominant_color_style || '—' }}</b></div>
          <div class="prop-row">构图: {{ creative.visual_packaging.composition_score || '—' }}</div>
          <div class="prop-row" v-if="creative.visual_packaging.packaging_label">包装: {{ creative.visual_packaging.packaging_label }}</div>
          <div v-if="creative.visual_packaging.color_palette?.length" class="prop-swatches" style="margin-top:4px">
            <span v-for="(c, i) in creative.visual_packaging.color_palette" :key="i" class="prop-swatch" :style="{ background: c }" />
          </div>
        </div>
        <div v-else class="prop-row" style="color:var(--text-muted)">—</div>

        <div class="prop-dense-title">转场特征</div>
        <div v-if="creative.transition_pattern?.available !== false && creative.transition_pattern" class="prop-creative__zone">
          <div class="prop-row">总数: <b>{{ creative.transition_pattern.total_count || 0 }}</b></div>
          <div class="prop-row">密度: {{ creative.transition_pattern.density?.toFixed(3) || '—' }}</div>
          <div class="prop-row" v-if="creative.transition_pattern.top_type">主要: <b>{{ creative.transition_pattern.top_type }}</b></div>
          <div v-if="creative.transition_pattern.type_distribution" class="prop-creative__table">
            <div v-for="(v, k) in Object.entries(creative.transition_pattern.type_distribution)" :key="k" class="prop-creative__row">
              <span class="prop-creative__cell">{{ k }}</span>
              <span class="prop-creative__cell prop-creative__cell--right">{{ v }}</span>
            </div>
          </div>
        </div>
        <div v-else class="prop-row" style="color:var(--text-muted)">—</div>

        <div class="prop-dense-title">音乐同步</div>
        <div v-if="creative.music_sync?.available !== false && creative.music_sync" class="prop-creative__zone">
          <div class="prop-row">BPM: <b>{{ creative.music_sync.bpm || '—' }}</b></div>
          <div v-if="creative.music_sync.sync_density != null" class="prop-row">
            <span>同步密度:</span>
            <span class="sync-bar__track" style="display:inline-flex;width:60px;height:6px;background:var(--border);border-radius:3px;overflow:hidden;margin:0 4px">
              <span class="sync-bar__fill" :style="{ width: (creative.music_sync.sync_density * 100) + '%', background: 'var(--accent)', height: '100%' }" />
            </span>
            <span>{{ (creative.music_sync.sync_density * 100).toFixed(0) }}%</span>
          </div>
          <div class="prop-row" v-if="creative.music_sync.music_structure">结构: <b>{{ creative.music_sync.music_structure }}</b></div>
        </div>
        <div v-else class="prop-row" style="color:var(--text-muted)">—</div>

      </div>
    </div>
  </div>

    <!-- ═══ Text Replacer overlay ═══ -->
    <Teleport to="body">
      <div v-if="showTextReplacer" class="prop-overlay" @click.self="showTextReplacer = false">
        <TextReplacer @close="showTextReplacer = false" />
      </div>
    </Teleport>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useProjectStore } from '../stores/project';
import { useTimelineStore } from '../stores/timelineStore';
import { usePlaybackStore } from '../stores/playbackStore';
import { useWorkbenchStore } from '../stores/workbench';
import TextReplacer from "./TextReplacer.vue";
import AudioWaveform from './AudioWaveform.vue';

const store = useProjectStore();
const timeline = useTimelineStore();
const playback = usePlaybackStore();
const ws = useWorkbenchStore();

const showTextReplacer = ref(false);
const toggleCreative = ref(false);

const groups = reactive({
  scene: true, visual: true, color: true, audio: true, text: true, voice: true,
});
function toggleGroup(key: keyof typeof groups) {
  groups[key] = !groups[key];
}

const selectedModule = computed(() => timeline.selectedModule);
const creative = computed(() => (ws as any).analysisResult?.creative_pattern || null);

// 兼容后端可能的字段名
const detail = computed(() => {
  const mod = selectedModule.value as any;
  return mod?.detail || mod?.analysis || mod?.params || null;
});

function safeVal(val: any, fallback = '等待分析'): string {
  if (val === null || val === undefined || val === '') return fallback;
  if (Array.isArray(val) && val.length === 0) return fallback;
  return Array.isArray(val) ? val.join('、') : String(val);
}

const sceneTags = computed(() => detail.value?.scene_tags || []);

/* ── 3c: YOLO quality ── */
function qualityLabel(flag: string): string {
  const m: Record<string, string> = { reliable: '检测可靠', suspicious: '部分可疑', rejected: '检测已拒绝' };
  return m[flag] || flag;
}

/* ── 3a: HSV zone colors ── */
const HSV_ZONE_CONFIG = [
  { key: 'white', label: '白色', color: '#e8e8f0' },
  { key: 'warm',  label: '暖色', color: '#f59e0b' },
  { key: 'cool',  label: '冷色', color: '#3b82f6' },
  { key: 'neutral', label: '中性', color: '#8b8ba0' },
  { key: 'dark',  label: '暗色', color: '#3a3a4a' },
];

const colorZones = computed(() => {
  const pcts = detail.value?.color_zone_pcts;
  if (!pcts || typeof pcts !== 'object') return [];
  return HSV_ZONE_CONFIG
    .filter(z => pcts[z.key] != null)
    .map(z => ({ ...z, pct: Math.round(pcts[z.key]) }));
});



/* ── 3b: Mood mapping ── */
const MOOD_MAP: Record<string, string> = {
  energetic: '激昂', calm: '平静', cheerful: '欢快',
  tense: '紧张', melancholy: '忧伤', neutral: '中性',
};
function moodLabel(mood: string): string {
  return MOOD_MAP[mood] || mood;
}

/* ── 3d: OCR — prefer structured items, fallback to plain texts ── */
interface OcrItem { text: string; sizeRank: string | null; lowConfidence: boolean }
const transcriptLines = computed(() => {
  const mod = selectedModule.value as any;
  if (mod?.contained_transcript?.length) return mod.contained_transcript;
  const d = detail.value;
  if (d?.voice_content && d.voice_content !== '无') return [d.voice_content];
  return [];
});

const ocrItems = computed<OcrItem[]>(() => {
  const d = detail.value;
  // 优先读取结构化字段
  const structured = d?.ocr_texts_structured;
  if (structured && Array.isArray(structured) && structured.length) {
    return structured.map((item: any) => ({
      text: item.text || '',
      sizeRank: item.text_size_rank || null,
      lowConfidence: !!item.low_confidence,
    }));
  }
  // 回退到纯文本数组
  const raw = d?.ocr_texts || [];
  return raw.map((text: string) => ({ text, sizeRank: null, lowConfidence: false }));
});

function sizeLabel(rank: string): string {
  const m: Record<string, string> = { large: '大', medium: '中', small: '小' };
  return m[rank] || rank;
}
function sizeClass(rank: string | null): string {
  if (rank === 'large') return 'ocr-size-lg';
  if (rank === 'small') return 'ocr-size-sm';
  return '';
}

// Mood labels mapped to waveform zones
const MOOD_COLORS: Record<string, string> = {
  energetic: '#ef4444', calm: '#3b82f6', cheerful: '#f59e0b',
  tense: '#8b5cf6', melancholy: '#10b981', neutral: '#6b7280',
};
const waveMoods = computed(() => {
  const d = detail.value;
  if (!d?.mood || !d?.duration) return [];
  // Place mood marker at 30% and 70% of duration for visual reference
  return [
    { at: d.duration * 0.3, label: d.mood, color: MOOD_COLORS[d.mood] || '#6b7280' },
  ];
});

const energyBars = computed(() => {
  const d = detail.value;
  if (d?.energy_curve && Array.isArray(d.energy_curve)) {
    return d.energy_curve.slice(0, 20).map((v: number) => Math.round(v * 100));
  }
  return new Array(20).fill(0);
});
</script>

<style scoped>
.prop { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

/* ── Title ── */
.prop__title {
  height: 36px; display: flex; align-items: center; padding: 0 12px;
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.4px;
  border-bottom: 1px solid var(--border); flex-shrink: 0;
}

/* ── Video type selector ── */
.prop-field { padding: 6px 12px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.prop-select {
  width: 100%; padding: 5px 8px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-surface); color: var(--text-primary);
  font-size: 12px; outline: none; cursor: pointer;
}
.prop-select:focus { border-color: var(--accent); }

/* ── Analyze button ── */
.prop-analyze { padding: 6px 12px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.prop-analyze-btn {
  width: 100%; padding: 6px 0; border: none;
  border-radius: var(--radius-sm); background: var(--accent); color: #fff;
  font-size: 12px; font-weight: 600; cursor: pointer; transition: all var(--transition);
}
.prop-analyze-btn:hover:not(:disabled) { background: var(--accent-hover); }
.prop-analyze-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.prop-analyze-btn--processing { background: var(--bg-surface); color: var(--text-primary); border: 1px solid var(--border); }
.prop-analyze-btn--done { background: var(--bg-surface); color: var(--accent); border: 1px solid var(--accent); cursor: default; }
.prop-analyze-btn--fail { background: #da3633; }

/* ── Body ── */
.prop__body { flex: 1; overflow-y: auto; padding: 6px 10px; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
.prop__empty { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: 13px; }

/* ── Collapsible group ── */
.prop-group { margin-bottom: 2px; border: 1px solid transparent; border-radius: var(--radius-sm); }
.prop-group__head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; font-size: 11px; font-weight: 600; color: var(--text-secondary);
  cursor: pointer; border-radius: var(--radius-sm); transition: background var(--transition);
}
.prop-group__head:hover { background: var(--bg-hover); }
.prop-group__arrow { font-size: 8px; color: var(--text-muted); transition: transform 200ms ease; }
.prop-group__arrow.open { transform: rotate(180deg); }
.prop-group__body { padding: 0 8px 8px; }

/* ── Tags ── */
.prop-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.prop-tag { padding: 2px 8px; font-size: 11px; background: var(--accent-subtle); color: var(--accent); border-radius: 10px; font-weight: 500; }

/* ── Row ── */
.prop-row { font-size: 12px; padding: 2px 0; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }
.prop-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.prop-dot.comp   { background: #00a8e8; }
.prop-dot.cont   { background: #f59e0b; }
.prop-dot.motion { background: #10b981; }

/* ── YOLO quality dot ── */
.prop-detect-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.detect-reliable  { background: #3fb950; }
.detect-suspicious { background: #f0b429; }
.detect-rejected   { background: #f85149; }



/* ── HSV stacked bar ── */
.prop-hsv { margin: 6px 0 4px; }
.prop-hsv__bar { display: flex; height: 10px; border-radius: 3px; overflow: hidden; }
.prop-hsv__seg { transition: width 0.3s; }
.prop-hsv__labels { display: flex; flex-wrap: wrap; gap: 2px 6px; margin-top: 3px; }
.prop-hsv__lbl { font-size: 9px; color: var(--text-muted); }
.prop-hsv__hint { font-size: 10px; color: var(--text-muted); font-style: italic; margin-top: 4px; padding: 3px 6px; background: var(--bg-surface); border-radius: 3px; }

/* ── Waveform ── */
.prop-waveform { display: flex; align-items: flex-end; gap: 1px; height: 28px; margin-top: 4px; }
.prop-bar { width: 6px; border-radius: 2px 2px 0 0; background: var(--accent); opacity: 0.7; }

/* ── Mood ── */
.prop-mood { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.prop-mood__tag { padding: 2px 8px; font-size: 11px; background: var(--accent-subtle); color: var(--accent); border-radius: 10px; font-weight: 500; }
.prop-mood__conf { flex: 1; max-width: 80px; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
.prop-mood__bar { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.3s; }
.prop-mood__sec { font-size: 10px; color: var(--text-muted); }

/* ── OCR ── */
.prop-ocr { max-height: 120px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
.prop-ocr__line {
  display: flex; align-items: center; gap: 4px;
  font-size: 10px; color: var(--text-secondary); padding: 2px 0;
  border-bottom: 1px solid var(--border); font-family: var(--font-mono);
}
.prop-ocr__line:last-child { border-bottom: none; }
.prop-ocr__low { opacity: 0.5; font-style: italic; }
.prop-ocr__text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ocr-size-lg { font-size: 12px; font-weight: 700; }
.ocr-size-sm { font-size: 9px; color: var(--text-muted); }
.prop-ocr__badge {
  font-size: 8px; padding: 1px 4px; border-radius: 3px;
  background: var(--bg-surface); color: var(--text-muted); flex-shrink: 0;
}
.badge--large { background: var(--accent-subtle); color: var(--accent); font-weight: 600; }
.badge--small { opacity: 0.6; }

.prop-repl-btn {
  width: 100%; padding: 5px 0; border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--bg-surface); color: var(--text-secondary); font-size: 11px;
  cursor: pointer; transition: all var(--transition);
}
.prop-repl-btn:hover { border-color: var(--accent); color: var(--accent); }
.prop-overlay {
  position: fixed; inset: 0; z-index: 2000;
  background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center;
}

.prop-creative { border-top: 1px solid var(--border); flex-shrink: 0; }
.prop-dense-title { font-size: 10px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.3px; padding: 6px 0 2px; }
.prop-creative__zone { padding: 2px 0 6px; }
.prop-creative__table { display: flex; flex-direction: column; gap: 1px; margin-top: 4px; }
.prop-creative__row { display: flex; justify-content: space-between; font-size: 11px; padding: 1px 0; }
.prop-creative__cell { color: var(--text-secondary); }
.prop-creative__cell--right { font-family: var(--font-mono); color: var(--text-muted); }
.prop-hist { display: flex; align-items: flex-end; gap: 2px; height: 40px; margin-top: 4px; }
.prop-hist__bar { width: 8px; border-radius: 2px 2px 0 0; background: var(--accent); opacity: 0.7; min-height: 4px; }
.sync-bar__track { width: 60px; height: 6px; }
.prop-muted { color: var(--text-muted); }
.prop-voice { max-height: 120px; overflow-y: auto; scrollbar-width: thin; }
.prop-voice__line {
  font-size: 10px; color: var(--text-secondary); padding: 2px 0;
  border-bottom: 1px solid var(--border); font-family: var(--font-mono);
}
.prop-voice__line:last-child { border-bottom: none; }
.prop-empty { font-size: 11px; color: var(--text-muted); }
</style>
