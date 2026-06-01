<template>
  <div class="prop">
    <div class="prop__title">模块解析</div>

    <div class="prop__body" v-if="selectedModule">
      <!-- ═══ Scene Tags ═══ -->
      <details class="prop-group" open>
        <summary class="prop-group__head">场景标签 <span class="prop-group__arrow">▼</span></summary>
        <div class="prop-group__body">
          <div v-if="sceneTags.length" class="prop-tags">
            <span v-for="tag in sceneTags" :key="tag" class="prop-tag">{{ tag }}</span>
          </div>
          <span v-else class="prop-empty">—</span>
        </div>
      </details>

      <!-- ═══ Visual Elements ═══ -->
      <details class="prop-group" open>
        <summary class="prop-group__head">视觉元素 <span class="prop-group__arrow">▼</span></summary>
        <div class="prop-group__body">
          <div class="prop-row"><span class="prop-dot" /> 构图: {{ detail?.composition || '—' }}</div>
          <div class="prop-row"><span class="prop-dot" /> 内容: {{ detail?.visual_elements?.join('、') || '—' }}</div>
          <div class="prop-row"><span class="prop-dot" /> 动效: {{ detail?.motion || '—' }}</div>
        </div>
      </details>

      <!-- ═══ Color Tone ═══ -->
      <details class="prop-group" open>
        <summary class="prop-group__head">色彩基调 <span class="prop-group__arrow">▼</span></summary>
        <div class="prop-group__body">
          <div class="prop-swatches" v-if="detail?.color_palette?.length">
            <span v-for="(c, i) in detail.color_palette" :key="i" class="prop-swatch" :style="{ background: c }" :title="c" />
          </div>
          <div class="prop-row" style="margin-top: 4px;">{{ detail?.color_tone || '—' }}</div>
        </div>
      </details>

      <!-- ═══ Audio Analysis ═══ -->
      <details class="prop-group" open>
        <summary class="prop-group__head">音频解析 <span class="prop-group__arrow">▼</span></summary>
        <div class="prop-group__body">
          <div class="prop-row-audio">
            <span class="prop-audio-label">BPM: {{ detail?.bpm || '—' }}</span>
            <div class="prop-energy">
              <span v-for="(v, i) in energyBars" :key="i" class="prop-bar" :style="{ height: v + '%' }" />
            </div>
          </div>
          <div class="prop-row">类型: {{ detail?.bgm_type || '—' }}</div>
        </div>
      </details>

      <!-- ═══ Text Analysis ═══ -->
      <details class="prop-group" open>
        <summary class="prop-group__head">文字解析 <span class="prop-group__arrow">▼</span></summary>
        <div class="prop-group__body">
          <div v-if="ocrTexts.length" class="prop-ocr">
            <div v-for="(t, i) in ocrTexts" :key="i" class="prop-ocr__line">{{ t }}</div>
          </div>
          <span v-else class="prop-empty">—</span>
        </div>
      </details>
    </div>

    <!-- No selection -->
    <div v-else class="prop__empty">
      <span>选择模块查看详情</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useProjectStore } from '../stores/project';

const store = useProjectStore();

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
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 6px;
  overflow: hidden;
  transition: height 200ms ease;
}
.prop-group__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  background: var(--bg-surface);
  list-style: none;
}
.prop-group__head::-webkit-details-marker {
  display: none;
}
.prop-group__head:hover {
  background: var(--bg-hover);
}
.prop-group__arrow {
  font-size: 8px;
  color: var(--text-muted);
  transition: transform 200ms ease;
}
details[open] .prop-group__arrow {
  transform: rotate(180deg);
}
.prop-group__body {
  padding: 6px 10px 8px;
}

/* ── Tag row ── */
.prop-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.prop-tag {
  display: inline-block;
  padding: 2px 6px;
  font-size: 10px;
  border-radius: 3px;
  background: var(--accent-subtle);
  color: var(--accent);
}

/* ── Row ── */
.prop-row {
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}
.prop-dot {
  display: inline-block;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}

/* ── Color swatches ── */
.prop-swatches {
  display: flex;
  gap: 4px;
}
.prop-swatch {
  width: 20px;
  height: 20px;
  border-radius: 3px;
  border: 1px solid var(--border);
}

/* ── Audio row ── */
.prop-row-audio {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}
.prop-audio-label {
  font-size: 11px;
  color: var(--text-secondary);
  flex-shrink: 0;
}
.prop-energy {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 24px;
  flex: 1;
}
.prop-bar {
  flex: 1;
  background: var(--accent);
  border-radius: 1px;
  min-height: 2px;
  opacity: 0.6;
  transition: height 200ms ease;
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
