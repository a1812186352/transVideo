<template>
  <div class="analysis-result">
    <div class="analysis-result__head">结构标签</div>
    <div class="analysis-result__body">
      <!-- ── Semantic tags from modules ── -->
      <div class="analysis-result__tags" v-if="modules.length">
        <div
          v-for="(mod, i) in modules"
          :key="i"
          class="analysis-result__tag-wrapper"
          :title="semanticTags(mod).join(' · ')"
        >
          <span
            class="analysis-result__tag"
            :class="`analysis-result__tag--${tagTypeClass(mod)}`"
          >{{ semanticLabel(mod) }}</span>
        </div>
      </div>
      <div v-else class="analysis-result__empty">尚未分析</div>

      <!-- ── Statistics ── -->
      <div class="analysis-result__stats">
        <div class="analysis-result__stat">
          <span class="analysis-result__stat-label">总时长</span>
          <span class="analysis-result__stat-value">{{ totalDuration.toFixed(1) }}s</span>
        </div>
        <div class="analysis-result__stat">
          <span class="analysis-result__stat-label">结构段</span>
          <span class="analysis-result__stat-value">{{ segmentCount }}</span>
        </div>
        <div class="analysis-result__stat">
          <span class="analysis-result__stat-label">镜头切换</span>
          <span class="analysis-result__stat-value">{{ cutCount }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface ModuleLike {
  type: string;
  name: string;
  detail?: Record<string, any>;
}

withDefaults(defineProps<{
  modules?: ModuleLike[];
  totalDuration?: number;
  segmentCount?: number;
  cutCount?: number;
}>(), {
  modules: () => [],
  totalDuration: 0,
  segmentCount: 0,
  cutCount: 0,
});

const TYPE_CLASS_MAP: Record<string, string> = {
  opening: 'opening', highlight: 'highlight', transition: 'transition',
  closing: 'closing', effect: 'effect',
};

function semanticLabel(mod: ModuleLike): string {
  const d = mod.detail;
  if (d?.sub_type && d.sub_type !== '未分类' && d.sub_type !== '无') return d.sub_type;
  const tags = d?.scene_tags;
  if (Array.isArray(tags) && tags.length) return tags[0];
  return mod.name;
}

function semanticTags(mod: ModuleLike): string[] {
  const d = mod.detail;
  const result: string[] = [];
  if (d?.sub_type && d.sub_type !== '未分类' && d.sub_type !== '无') result.push(d.sub_type);
  const tags = d?.scene_tags;
  if (Array.isArray(tags)) result.push(...tags);
  if (!result.length) result.push(mod.name);
  return result;
}

function tagTypeClass(mod: ModuleLike): string {
  const t = mod.type;
  if (TYPE_CLASS_MAP[t]) return t;
  const d = mod.detail;
  const texts = [d?.sub_type, ...(Array.isArray(d?.scene_tags) ? d.scene_tags : [])].filter(Boolean);
  for (const txt of texts) {
    if (/开头|open|开场/i.test(txt)) return 'opening';
    if (/高潮|high/i.test(txt)) return 'highlight';
    if (/转场|过渡/i.test(txt)) return 'transition';
    if (/结尾|clos/i.test(txt)) return 'closing';
    if (/特效|effect/i.test(txt)) return 'effect';
  }
  return 'opening';
}
</script>

<style scoped>
.analysis-result-head { display: none; }
.analysis-result__head {
  height: 36px; display: flex; align-items: center;
  padding: 0 14px; font-size: 12px; font-weight: 600;
  border-bottom: 1px solid var(--border);
}

.analysis-result__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px;
}

.analysis-result__tag-wrapper {
  line-height: 0;
}

.analysis-result__tag {
  display: inline-block;
  padding: 3px 10px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 10px;
  color: #fff;
  white-space: nowrap;
  flex-shrink: 0;
  min-width: 48px;
  text-align: center;
}

.analysis-result__tag--opening    { background: var(--slot-opening); }
.analysis-result__tag--highlight  { background: var(--slot-highlight); }
.analysis-result__tag--transition { background: var(--slot-transition); }
.analysis-result__tag--closing    { background: var(--slot-closing); }
.analysis-result__tag--effect     { background: var(--slot-effect); }

.analysis-result__empty {
  padding: 12px;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}

/* ── Statistics ── */
.analysis-result__stats {
  display: flex;
  gap: 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.analysis-result__stat {
  flex: 1;
  text-align: center;
  padding: 8px 4px;
  border-right: 1px solid var(--border);
}
.analysis-result__stat:last-child { border-right: none; }
.analysis-result__stat-label {
  display: block; font-size: 9px; color: var(--text-muted);
  text-transform: uppercase; margin-bottom: 2px;
}
.analysis-result__stat-value {
  display: block; font-size: 14px; font-weight: 700;
  color: var(--text-primary); font-family: var(--font-mono);
}
</style>
