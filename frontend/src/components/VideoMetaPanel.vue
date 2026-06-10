<template>
  <div class="vmeta">
    <div class="vmeta__head" @click="open = !open">
      视频元数据 <span class="vmeta__arrow" :class="{ open }">▼</span>
    </div>
    <div class="vmeta__body" v-show="open">
      <div class="vmeta__row"><span class="vmeta__label">分辨率</span><span class="vmeta__value">{{ width }}×{{ height }}</span></div>
      <div class="vmeta__row"><span class="vmeta__label">帧率</span><span class="vmeta__value">{{ fps }} fps</span></div>
      <div class="vmeta__row"><span class="vmeta__label">编码</span><span class="vmeta__value">{{ codec || '—' }}</span></div>
      <div class="vmeta__row"><span class="vmeta__label">视频类型</span><span class="vmeta__value">{{ videoTypeLabel || '—' }}</span></div>
      <div class="vmeta__row"><span class="vmeta__label">文件大小</span><span class="vmeta__value">{{ fileSize }}</span></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';

const props = withDefaults(defineProps<{
  width?: number;
  height?: number;
  fps?: number;
  codec?: string;
  videoType?: string;
  fileSize?: string;
}>(), {
  width: 0, height: 0, fps: 0, codec: '', videoType: '', fileSize: '—',
});

const open = ref(false);
const videoTypeLabel = computed(() => {
  if (!props.videoType) return '';
  const labels: Record<string, string> = {
    commercial: '商业广告', gaming: '游戏集锦', lecture: '公开课/讲座',
    film_tv: '影视剧集', music: '音乐/MV', anime: '动画/动漫',
    knowledge: '知识科普', sports: '体育赛事', food: '美食',
    auto: '汽车', short_drama: '短剧', vlog: 'Vlog（通用）',
    travel: '旅游', agriculture: '农业', parenting: '亲子',
    beauty_fashion: '美妆时尚',
  };
  return labels[props.videoType] || props.videoType;
});
</script>

<style scoped>
.vmeta {
  border-bottom: 1px solid var(--border);
}
.vmeta__head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 12px; font-size: 10px; font-weight: 600;
  color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.3px;
  cursor: pointer; user-select: none;
  transition: background var(--transition);
}
.vmeta__head:hover { background: var(--bg-hover); }
.vmeta__arrow { font-size: 8px; color: var(--text-muted); transition: transform 200ms ease; }
.vmeta__arrow.open { transform: rotate(180deg); }
.vmeta__body { padding: 4px 12px 8px; }
.vmeta__row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 2px 0; font-size: 11px;
}
.vmeta__label { color: var(--text-muted); }
.vmeta__value { color: var(--text-primary); font-family: var(--font-mono); font-size: 11px; }
</style>
