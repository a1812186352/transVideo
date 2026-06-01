<template>
  <div class="prop">
    <div class="prop__title">模块解析</div>

    <div class="prop__body" v-if="selectedModule">
      <!-- ═══ Scene Tags ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('scene')">场景标签 <span class="prop-group__arrow" :class="{ open: groups.scene }">▼</span></div>
        <div class="prop-group__body" v-show="groups.scene">
          <div v-if="sceneTags.length" class="prop-tags">
            <span v-for="tag in sceneTags" :key="tag" class="prop-tag">{{ tag }}</span>
          </div>
          <span v-else class="prop-empty">—</span>
        </div>
      </div>

      <!-- ═══ Visual Elements ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('visual')">视觉元素 <span class="prop-group__arrow" :class="{ open: groups.visual }">▼</span></div>
        <div class="prop-group__body" v-show="groups.visual">
          <div class="prop-row"><span class="prop-dot comp" /> 构图: {{ detail?.composition || '—' }}</div>
          <div class="prop-row"><span class="prop-dot cont" /> 内容: {{ detail?.visual_elements?.join('、') || '—' }}</div>
          <div class="prop-row"><span class="prop-dot motion" /> 动效: {{ detail?.motion || '—' }}</div>
        </div>
      </div>

      <!-- ═══ Color Tone ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('color')">色彩基调 <span class="prop-group__arrow" :class="{ open: groups.color }">▼</span></div>
        <div class="prop-group__body" v-show="groups.color">
          <div class="prop-swatches" v-if="detail?.color_palette?.length">
            <span v-for="(c, i) in detail.color_palette" :key="i" class="prop-swatch" :style="{ background: c }" />
          </div>
          <div class="prop-row" style="margin-top: 4px;">{{ detail?.color_tone || '—' }}</div>
        </div>
      </div>

      <!-- ═══ Audio Analysis ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('audio')">音频分析 <span class="prop-group__arrow" :class="{ open: groups.audio }">▼</span></div>
        <div class="prop-group__body" v-show="groups.audio">
          <div class="prop-row">BPM: {{ detail?.bpm || '—' }} · 类型: {{ detail?.bgm_type || '—' }}</div>
          <div class="prop-waveform">
            <span v-for="(v, i) in energyBars" :key="i" class="prop-bar" :style="{ height: v + '%' }" />
          </div>
        </div>
      </div>

      <!-- ═══ Text Analysis ═══ -->
      <div class="prop-group">
        <div class="prop-group__head" @click="toggleGroup('text')">文字解析 <span class="prop-group__arrow" :class="{ open: groups.text }">▼</span></div>
        <div class="prop-group__body" v-show="groups.text">
          <div v-if="ocrTexts.length" class="prop-ocr">
            <div v-for="(t, i) in ocrTexts" :key="i" class="prop-ocr__line">{{ t }}</div>
          </div>
          <span v-else class="prop-empty">—</span>
        </div>
      </div>
    </div>

    <!-- No selection -->
    <div v-else class="prop__empty">
      <span>选择模块查看详情</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue';
import { useProjectStore } from '../stores/project';

const store = useProjectStore();

const groups = reactive({
  scene: true, visual: true, color: true, audio: true, text: true,
});
function toggleGroup(key: keyof typeof groups) {
  groups[key] = !groups[key];
}

const selectedModule = computed(() => store.selectedModule);
const detail = computed(() => (selectedModule.value as any)?.detail || null);

const sceneTags = computed(() => {
  const d = detail.value;
  return d?.scene_tags || [];
});

const ocrTexts = computed(() => {
  const d = detail.value;
  return d?.ocr_texts || [];
});

// Generate 20 energy bars from mock or real energy data
const energyBars = computed(() => {
  const d = detail.value;
  if (d?.energy_curve && Array.isArray(d.energy_curve)) {
    return d.energy_curve.slice(0, 20).map((v: number) => Math.round(v * 100));
  }
  // fallback: generate gentle wave pattern
  return Array.from({ length: 20 }, (_, i) =>
    Math.round(20 + Math.sin(i * 0.8) * 15 + Math.random() * 10)
  );
});
</script>

<style scoped>
.prop {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── Title ── */
.prop__title {
  height: 36px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

/* ── Body (scrollable) ── */
.prop__body {
  flex: 1;
  overflow-y: auto;
  padding: 6px 10px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

/* ── Empty ── */
.prop__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 13px;
}

/* ── Collapsible group ── */
.prop-group {
  margin-bottom: 2px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
}
.prop-group__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background var(--transition);
}
.prop-group__head:hover {
  background: var(--bg-hover);
}
.prop-group__arrow {
  font-size: 8px;
  color: var(--text-muted);
  transition: transform 200ms ease;
}
.prop-group__arrow.open {
  transform: rotate(180deg);
}
.prop-group__body {
  padding: 0 8px 8px;
}

/* ── Tags ── */
.prop-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.prop-tag {
  padding: 2px 8px; font-size: 11px;
  background: var(--accent-subtle); color: var(--accent);
  border-radius: 10px; font-weight: 500;
}

/* ── Row ── */
.prop-row {
  font-size: 12px; padding: 2px 0; color: var(--text-secondary);
  display: flex; align-items: center; gap: 6px;
}
.prop-dot {
  width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
}
.prop-dot.comp   { background: #00a8e8; }
.prop-dot.cont   { background: #f59e0b; }
.prop-dot.motion { background: #10b981; }

/* ── Color swatches ── */
.prop-swatches { display: flex; gap: 2px; margin-top: 4px; }
.prop-swatch { height: 8px; flex: 1; border-radius: 2px; }

/* ── Waveform ── */
.prop-waveform {
  display: flex; align-items: flex-end; gap: 1px;
  height: 28px; margin-top: 4px;
}
.prop-bar {
  width: 6px; border-radius: 2px 2px 0 0;
  background: var(--accent); opacity: 0.7;
}

/* ── OCR ── */
.prop-ocr {
  max-height: 100px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.prop-ocr__line {
  font-size: 10px;
  color: var(--text-secondary);
  padding: 1px 0;
  border-bottom: 1px solid var(--border);
  font-family: var(--font-mono);
}
.prop-ocr__line:last-child {
  border-bottom: none;
}

/* ── Empty value ── */
.prop-empty {
  font-size: 11px;
  color: var(--text-muted);
}
</style>
