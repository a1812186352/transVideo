/**
 * i18n.ts — 轻量国际化，为接入 vue-i18n 做准备
 * 当前仅中文，后需可扩展为 { zh: {...}, en: {...} }
 */

const zh: Record<string, string> = {
  // 通用
  loading: '加载中…',
  saving: '保存中…',
  failed: '失败',
  retry: '重试',
  close: '关闭',
  empty: '暂无数据',
  waiting: '等待分析',
  analyzing: '分析中…',
  completed: '分析完成',

  // 面板标题
  moduleParser: '模块解析',
  materialLib: '素材库',
  scriptEditor: '脚本',
  templates: '模板',
  propertyDetail: '属性',
  generateVideo: '生成视频',
  timeline: '时间轴',
  preview: '预览',

  // 操作
  uploadVideo: '上传视频',
  startAnalyze: '开始分析',
  analyzeProgress: '分析中…',
  analyzeDone: '✓ 分析完成',
  analyzeFailed: '↻ 重试分析',

  // 导出
  generate: '生成视频',
  generating: '生成中',
  viewVideo: '✓ 查看视频',
  exportScript: '📄 导出脚本',
  exportSettings: '导出设置',
  history: '历史产出',
  noHistory: '暂无生成记录',

  // 时间轴
  dropMaterial: '拖入素材到时间轴创建模块',
  undo: '撤销',
  redo: '重做',

  // 属性
  sceneTags: '场景标签',
  visualElements: '视觉元素',
  colorTone: '色彩基调',
  audioAnalysis: '音频分析',
  textAnalysis: '文字解析',
  composition: '构图',
  content: '内容',
  motion: '动效',
  detectQuality: '检测质量',
  reliable: '检测可靠',
  suspicious: '部分可疑',
  rejected: '检测已拒绝',
  bpm: 'BPM',
  type: '类型',
  mood: '情绪',
  secMood: '次情绪',
  waitAnalyze: '等待分析',
  selectModule: '选择模块查看详情',
  batchReplace: '🔤 批量替换文本',
  videoType: '视频类型',
  estTime: '预计耗时',

  // 缩略图
  thumbLoadFailed: '加载失败',
};

export function t(key: string, fallback?: string): string {
  return zh[key] || fallback || key;
}

export { zh };
