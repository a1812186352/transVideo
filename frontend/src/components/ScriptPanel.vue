<template>
  <div class="spanel">
    <div class="spanel__header">
      <span class="spanel__title">脚本预览</span>
      <span class="spanel__count" v-if="timeline.modules.length">
        {{ timeline.modules.length }} 个模块
      </span>
    </div>

    <!-- Block list -->
    <div class="spanel__list" v-if="blocks.length">
      <div
        v-for="(b, i) in blocks"
        :key="b.module_id"
        class="spanel__block"
        :class="{ 'spanel__block--sel': timeline.selectedModuleId === b.module_id }"
        @click="selectBlock(b)"
      >
        <div class="spanel__block-order">{{ i + 1 }}</div>
        <div class="spanel__block-body">
          <div class="spanel__block-head">
            <span class="spanel__block-type">{{ b.label }}</span>
            <span class="spanel__block-time">{{ fmtHMS(b.start_time) }} → {{ fmtHMS(b.end_time) }}</span>
          </div>
          <div class="spanel__block-desc">{{ b.content_description }}</div>
          <div class="spanel__block-tags" v-if="b.content_tags.length">
            <span v-for="t in b.content_tags" :key="t" class="spanel__tag">{{ t }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="spanel__empty">
      选择模块后在此编辑脚本内容
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useTimelineStore } from '../stores/timelineStore';
import { usePlaybackStore } from '../stores/playbackStore';
import { composeScript, type ScriptBlock } from '../utils/scriptGenerator';

const timeline = useTimelineStore();
const playback = usePlaybackStore();

const blocks = computed<ScriptBlock[]>(() => {
  if (!timeline.modules.length) return [];
  return composeScript(timeline.modules).blocks;
});

function selectBlock(b: ScriptBlock) {
  timeline.selectModule(b.module_id);
  playback.seekTo(b.start_time);
}

const fmtHMS = (s: number): string => {
  if (!s || s <= 0) return '0:00';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  const p = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${p(m)}:${p(sec)}` : `${m}:${p(sec)}`;
};
</script>

<style scoped>
.spanel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.spanel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.spanel__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.spanel__count {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.spanel__list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.spanel__block {
  display: flex;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  transition: background var(--transition);
  border-bottom: 1px solid var(--border);
}
.spanel__block:hover { background: var(--bg-hover); }
.spanel__block--sel { background: var(--accent-subtle); }

.spanel__block-order {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}

.spanel__block-body {
  flex: 1;
  min-width: 0;
}
.spanel__block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.spanel__block-type {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary);
}
.spanel__block-time {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  white-space: nowrap;
}
.spanel__block-desc {
  font-size: 10px;
  color: var(--text-secondary);
  margin-top: 2px;
  line-height: 1.4;
}
.spanel__block-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 3px;
}
.spanel__tag {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--accent-subtle);
  color: var(--accent);
  font-weight: 500;
}

.spanel__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
