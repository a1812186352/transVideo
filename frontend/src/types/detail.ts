/**
 * 模块 detail 严格类型定义 — 对齐后端 pipeline_detail.py
 */
export interface ModuleDetail {
  // 场景
  scene_tags?: string[];
  // 视觉
  composition?: string;
  visual_elements?: string[];
  motion?: string;
  yolo_quality_flag?: 'reliable' | 'suspicious' | 'rejected';
  // 色彩
  color_zone_pcts?: Record<string, number>;
  color_palette?: string[];
  color_tone?: string;
  is_dominantly_neutral?: boolean;
  // 音频
  bpm?: number;
  bgm_type?: string;
  mood?: string;
  mood_confidence?: number;
  mood_secondary?: string;
  energy_curve?: number[];
  // 文字
  ocr_texts?: string[];
  ocr_texts_structured?: Array<{ text: string; text_size_rank?: string; low_confidence?: boolean }>;
  text_size_rank?: Record<string, string>;
  low_confidence_texts?: Record<string, boolean>;
  // 动效
  brightness_trend?: string;
  scale_trend?: string;
  movement_trend?: string;
  motion_trend?: Record<string, string>;
  motion_description?: { label?: string };
  object_transitions?: { fade_in_count?: number; fade_out_count?: number };
  // 时间
  original_start?: number;
  original_end?: number;
  // 帧
  keyframes?: string[];
  keyframe_url?: string;
  // 标签
  content_tags?: string[];
  // 能量
  energy_peak_value?: number;
}
