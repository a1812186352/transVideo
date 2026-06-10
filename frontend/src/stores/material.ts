/**
 * 素材缺口管理 Store — 从 creative_pattern.gaps 映射到上传槽位
 *
 * 每个缺口 = { type, label, reason, accept }
 * 用户上传文件后，store 记录映射关系 { gap_key: File }
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export interface MaterialGap {
  /** 缺口键名，如 "product_shot"、"bgm_track" */
  key: string;
  /** 缺口标签，如 "产品展示"、"BGM 音频" */
  label: string;
  /** 缺口状态: missing / insufficient / matched */
  status: 'missing' | 'insufficient' | 'matched';
  /** 缺口原因描述，如 "需要上传产品展示视频" */
  reason: string;
  /** 接受的文件类型 */
  accept: string;
  /** 用户已上传的文件 */
  file: { name: string; url?: string } | null;
}

export interface CreativeGaps {
  shot_rhythm?: { gap?: MaterialGap };
  subtitle_style?: { gap?: MaterialGap };
  visual_style?: { gap?: MaterialGap };
  transition?: { gap?: MaterialGap };
  music_sync?: { gap?: MaterialGap };
  narrative_structure?: { gap?: MaterialGap };
}

/** 从 creative_pattern 提取缺口列表 */
function extractGaps(creativePattern: Record<string, any> | null): MaterialGap[] {
  if (!creativePattern) return [];

  const raw: MaterialGap[] = [];
  const decon = creativePattern.deconstruction || creativePattern;

  // 镜头节奏 → 视频素材
  const shotRhythm = decon.shot_rhythm;
  if (shotRhythm?.gap) {
    raw.push({
      key: 'shot_rhythm',
      label: shotRhythm.gap.label || shotRhythm.gap.type || '镜头素材',
      status: shotRhythm.gap.status || 'missing',
      reason: shotRhythm.gap.reason || '需要上传镜头素材',
      accept: 'video/*,image/*',
      file: null,
    });
  }

  // 字幕风格 → 字体/样式文件
  const subtitle = decon.subtitle_style;
  if (subtitle?.gap) {
    raw.push({
      key: 'subtitle_style',
      label: subtitle.gap.label || '字幕样式',
      status: subtitle.gap.status || 'missing',
      reason: subtitle.gap.reason || '需要上传字体或样式文件',
      accept: '.ttf,.otf,.woff,.json',
      file: null,
    });
  }

  // 画面包装 → 模板/贴纸
  const visual = decon.visual_style;
  if (visual?.gap) {
    raw.push({
      key: 'visual_style',
      label: visual.gap.label || '画面包装',
      status: visual.gap.status || 'missing',
      reason: visual.gap.reason || '需要上传模板或贴纸素材',
      accept: 'image/*,.psd,.json',
      file: null,
    });
  }

  // 转场 → 转场预设
  const trans = decon.transition;
  if (trans?.gap) {
    raw.push({
      key: 'transition',
      label: trans.gap.label || '转场预设',
      status: trans.gap.status || 'missing',
      reason: trans.gap.reason || '需要上传转场模板',
      accept: '.json,.mp4',
      file: null,
    });
  }

  // BGM → 音频文件
  const music = decon.music_sync;
  if (music?.gap) {
    raw.push({
      key: 'music_sync',
      label: music.gap.label || 'BGM 音频',
      status: music.gap.status || 'missing',
      reason: music.gap.reason || '需要上传背景音乐',
      accept: 'audio/*',
      file: null,
    });
  }

  // 叙事结构 → 补充视频/脚本
  const narrative = decon.narrative_structure;
  if (narrative?.gap) {
    raw.push({
      key: 'narrative_structure',
      label: narrative.gap.label || '叙事素材',
      status: narrative.gap.status || 'missing',
      reason: narrative.gap.reason || '需要上传补充脚本或视频',
      accept: 'video/*,image/*,.txt,.md',
      file: null,
    });
  }

  return raw;
}

export const useMaterialStore = defineStore('material', () => {
  /** 原始缺口列表（由 creative_pattern 驱动） */
  const gaps = ref<MaterialGap[]>([]);

  /** 已上传文件映射 { gap_key: File } */
  const uploadedFiles = ref<Record<string, { name: string; url?: string }>>({});

  /** 汇总统计 */
  const total = computed(() => gaps.value.length);
  const matched = computed(() => gaps.value.filter(g => g.status === 'matched' || !!uploadedFiles.value[g.key]).length);
  const missing = computed(() => gaps.value.filter(g => g.status === 'missing').length);
  const coverage = computed(() => total.value > 0 ? Math.round((matched.value / total.value) * 100) : 0);

  /** 从 creative_pattern 刷新缺口 */
  function loadFromCreativePattern(creativePattern: Record<string, any> | null) {
    gaps.value = extractGaps(creativePattern);

    // 恢复已有上传记录
    for (const g of gaps.value) {
      const existing = uploadedFiles.value[g.key];
      if (existing) {
        g.file = existing;
        if (g.status === 'missing') g.status = 'matched';
      }
    }
  }

  /** 上传文件到指定缺口 */
  function uploadFile(gapKey: string, file: File) {
    const gap = gaps.value.find(g => g.key === gapKey);
    if (!gap) return;

    const entry = { name: file.name };
    uploadedFiles.value[gapKey] = entry;
    gap.file = entry;
    gap.status = 'matched';
  }

  /** 移除已上传文件 */
  function removeFile(gapKey: string) {
    const gap = gaps.value.find(g => g.key === gapKey);
    if (!gap) return;

    delete uploadedFiles.value[gapKey];
    gap.file = null;
    gap.status = 'missing';
  }

  /** 重置所有缺口 */
  function reset() {
    gaps.value = [];
    uploadedFiles.value = {};
  }

  return {
    gaps,
    uploadedFiles,
    total,
    matched,
    missing,
    coverage,
    loadFromCreativePattern,
    uploadFile,
    removeFile,
    reset,
  };
});
