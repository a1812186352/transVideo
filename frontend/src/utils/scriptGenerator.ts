/** Client-side script generator — assemblies and exports composed scripts.

 *  Mirrors ``generation/script_composer.py`` on the frontend side
 *  so live preview and export work without a backend round-trip.
 */

import type { Module } from '../types/script';

export interface ScriptBlock {
  module_id: string;
  order: number;
  module_type: string;
  structure_type: string;
  start_time: number;
  end_time: number;
  duration: number;
  label: string;
  content_tags: string[];
  content_description: string;
  template_params: Record<string, unknown>;
}

export interface ComposedScript {
  version: string;
  metadata: {
    title: string;
    total_duration: number;
    block_count: number;
    structure_summary: Record<string, number>;
  };
  blocks: ScriptBlock[];
}

// ═══════════════════════════════════════════════════════
//  Templates (mirrors backend)
// ═══════════════════════════════════════════════════════

const TYPE_TEMPLATES: Record<string, {
  label: string; description: string; structure_type: string; animation: string | null; default_duration: number;
}> = {
  title:           { label: '片头标题', description: '视频开场标题片段',     structure_type: 'opening',    animation: 'fade_in',    default_duration: 5.0 },
  video_segment:   { label: '视频片段', description: '原始视频高光片段',     structure_type: 'highlight',  animation: null,         default_duration: 8.0 },
  subtitle:        { label: '字幕叠加', description: '叠加字幕文字内容',     structure_type: 'content',     animation: 'slide_up',   default_duration: 3.0 },
  transition:      { label: '转场效果', description: '模块间过渡转场',       structure_type: 'transition',  animation: 'crossfade',  default_duration: 1.5 },
  audio:           { label: '音频段落', description: '背景音乐或音效段落',   structure_type: 'content',     animation: null,         default_duration: 5.0 },
  effect:          { label: '视觉特效', description: '叠层特效或滤镜',       structure_type: 'effect',      animation: 'scale_up',   default_duration: 1.0 },
};

// ═══════════════════════════════════════════════════════
//  Composer
// ═══════════════════════════════════════════════════════

export function composeScript(modules: Module[], title?: string): ComposedScript {
  const blocks: ScriptBlock[] = [];
  let cumulative = 0;

  for (let i = 0; i < modules.length; i++) {
    const mod = modules[i];
    const modType = mod.type || 'video_segment';
    const tpl = TYPE_TEMPLATES[modType] || TYPE_TEMPLATES['video_segment'];
    const detail = (mod as any).detail || {};
    const modStart = mod.start_time;
    const modDur = mod.duration || 3;

    // ── Content description ──
    const parts: string[] = [];
    const tags: string[] = Array.isArray(detail.content_tags) ? detail.content_tags : [];
    if (tags.length) parts.push(tags.slice(0, 3).join(' · '));
    if (detail.voice_content && detail.voice_content !== '无')
      parts.push(`配音: ${detail.voice_content}`);
    if (detail.motion && detail.motion !== '无')
      parts.push(`运镜: ${detail.motion}`);
    if (detail.color_tone && detail.color_tone !== '未知')
      parts.push(`色调: ${detail.color_tone}`);
    if (detail.bgm_type && detail.bgm_type !== '无' && detail.bgm_type !== '未知')
      parts.push(`背景乐: ${detail.bgm_type}`);

    // ── Params ──
    const params: Record<string, unknown> = {};
    if (modType === 'title')
      params.text = mod.label || title || '未命名';
    if (modType === 'video_segment') {
      params.source_start = detail.original_start ?? modStart;
      params.source_end   = detail.original_end   ?? (modStart + modDur);
      params.source_path  = mod.source?.path || '';
    }
    if (mod.params?.transition_type)
      params.transition_type = mod.params.transition_type;

    blocks.push({
      module_id: mod.id,
      order: i,
      module_type: modType,
      structure_type: tpl.structure_type,
      start_time: modStart,
      end_time: modStart + modDur,
      duration: modDur,
      label: mod.label || tpl.label,
      content_tags: tags,
      content_description: parts.join('；') || tpl.description,
      template_params: params,
    });

    cumulative = modStart + modDur;
  }

  const structureSummary: Record<string, number> = {};
  for (const b of blocks) {
    structureSummary[b.structure_type] = (structureSummary[b.structure_type] || 0) + 1;
  }

  return {
    version: '1.0.0',
    metadata: {
      title: title || '未命名项目',
      total_duration: cumulative,
      block_count: blocks.length,
      structure_summary: structureSummary,
    },
    blocks,
  };
}

// ═══════════════════════════════════════════════════════
//  Export formats
// ═══════════════════════════════════════════════════════

function fmtHMS(s: number): string {
  if (!s || s <= 0) return '0:00';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  const p = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${p(m)}:${p(sec)}` : `${m}:${p(sec)}`;
}

function fmtTimeSrt(s: number): string {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const p = (n: number, d = 2) => String(n).padStart(d, '0');
  return `${p(h)}:${p(m)}:${p(Math.floor(sec))},${p(Math.round((sec % 1) * 1000), 3)}`;
}

export type ExportFormat = 'json' | 'markdown' | 'html' | 'srt' | 'plain';

export function exportScript(script: ComposedScript, format: ExportFormat): { content: string; ext: string } {
  const ext = { json: 'json', markdown: 'md', html: 'html', srt: 'srt', plain: 'txt' }[format];
  let content = '';

  switch (format) {
    case 'json':
      content = JSON.stringify(script, null, 2);
      break;

    case 'markdown': {
      const lines = [
        `# ${script.metadata.title}`,
        '',
        `| # | 类型 | 时间 | 时长 | 描述 |`,
        `|---|------|------|------|------|`,
      ];
      for (const b of script.blocks) {
        lines.push(`| ${b.order + 1} | ${b.label} | ${fmtHMS(b.start_time)} → ${fmtHMS(b.end_time)} | ${Math.round(b.duration)}s | ${b.content_description} |`);
      }
      lines.push('', `> 共 ${script.metadata.block_count} 个模块，总时长 ${fmtHMS(script.metadata.total_duration)}`);
      content = lines.join('\n');
      break;
    }

    case 'html': {
      const rows = script.blocks.map((b, i) =>
        `<tr><td>${i + 1}</td><td>${b.label}</td><td>${fmtHMS(b.start_time)} → ${fmtHMS(b.end_time)}</td><td>${Math.round(b.duration)}s</td><td>${b.content_description}</td></tr>`
      ).join('\n');
      content = `<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>${script.metadata.title}</title>
<style>body{font-family:system-ui;max-width:960px;margin:2em auto;padding:0 1em;color:#333}
table{width:100%;border-collapse:collapse}th,td{padding:8px 12px;border-bottom:1px solid #eee;text-align:left;font-size:14px}
th{background:#f5f5f5;font-weight:600}tr:hover{background:#fafafa}
.summary{color:#888;font-size:13px;margin-top:1em}</style></head>
<body><h1>${script.metadata.title}</h1>
<table><thead><tr><th>#</th><th>类型</th><th>时间</th><th>时长</th><th>描述</th></tr></thead>
<tbody>${rows}</tbody></table>
<p class="summary">共 ${script.metadata.block_count} 个模块，总时长 ${fmtHMS(script.metadata.total_duration)}</p>
</body></html>`;
      break;
    }

    case 'srt':
      content = script.blocks.map((b, i) =>
        `${i + 1}\n${fmtTimeSrt(b.start_time)} --> ${fmtTimeSrt(b.end_time)}\n${b.label}\n`
      ).join('\n');
      break;

    case 'plain':
      content = script.blocks.map(b =>
        `${b.order + 1}. [${b.structure_type}] ${b.label} (${fmtHMS(b.start_time)} → ${fmtHMS(b.end_time)}, ${Math.round(b.duration)}s)\n    ${b.content_description}`
      ).join('\n\n');
      break;
  }

  return { content, ext };
}

/** Trigger a browser download for the given content. */
export function downloadScript(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
