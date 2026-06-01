import { ref, computed, nextTick } from 'vue';
import { defineStore } from 'pinia';
import { useProjectStore } from './project';
import type { ModuleType, UploadResult, AnalysisResult, ExportResult } from '../types/script';

/**
 * Workbench store — 六区工作台的所有业务逻辑
 * upload / analyze / export / monitor / 辅助函数
 */
export const useWorkbenchStore = defineStore('workbench', () => {
  const project = useProjectStore();

  /* ═══════════════════════════════════
     UI State
     ═══════════════════════════════════ */
  const settingsOpen = ref(false);
  const dragOver = ref(false);
  const exportDownloadUrl = ref<string | null>(null);
  const uploadFileSize = ref(0);
  const uploadFileName = ref('');
  const videoCurrentTime = ref(0);
  const analysisActualTime = ref('');
  const viewMode = ref<'list' | 'grid'>('list');
  const moduleScript = ref('');
  const showExportFmt = ref(false);
  const exportResolution = ref('1920x1080');
  const exportBitrate = ref(8);
  const exportSubtitles = ref(true);
  const exportFormat = ref('mp4');
  const videoType = ref('vlog');
  // prettier-ignore
  const VIDEO_TYPE_OPTIONS = [
    { value: 'vlog',     label: '生活Vlog' },
    { value: 'travel',   label: '旅行记录' },
    { value: 'food',     label: '美食制作' },
    { value: 'edu',      label: '教学教程' },
    { value: 'tech',     label: '科技数码' },
    { value: 'game',     label: '游戏剪辑' },
    { value: 'sport',    label: '运动健身' },
    { value: 'music',    label: '音乐MV' },
    { value: 'dance',    label: '舞蹈表演' },
    { value: 'pet',      label: '宠物日常' },
    { value: 'fashion',  label: '时尚穿搭' },
    { value: 'beauty',   label: '美妆护肤' },
    { value: 'news',     label: '新闻资讯' },
    { value: 'comedy',   label: '搞笑娱乐' },
    { value: 'film',     label: '影视剪辑' },
    { value: 'commercial', label: '商业广告' },
    { value: 'other',      label: '其他类型' },
  ];

  /* ═══════════════════════════════════
     Monitor / Log
     ═══════════════════════════════════ */
  interface LogLine { ts: string; tag?: string; msg: string; c?: string; icon?: string; hl?: boolean }
  const monitorLogs = ref<LogLine[]>([]);
  let _monitorTimer: ReturnType<typeof setInterval> | null = null;
  let _monitorAutoScroll = true;
  let _monitorStart = 0;

  function onMonitorScroll(el: HTMLElement | null) {
    if (!el) return;
    _monitorAutoScroll = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
  }

  function pushLog(tag: string, msg: string, c = '', _icon = '', hl = false) {
    const elapsed = (Date.now() - _monitorStart) / 1000;
    const m = Math.floor(elapsed / 60);
    const s = (elapsed % 60).toFixed(2);
    const ts = String(m).padStart(2, '0') + ':' + String(s).padStart(5, '0');
    monitorLogs.value.push({ ts, tag, msg, c, icon: _icon, hl });
    if (_monitorAutoScroll) {
      nextTick(() => {
        const el = document.querySelector('.mon-body');
        if (el) el.scrollTop = el.scrollHeight;
      });
    }
  }

  function startMonitor() {
    stopMonitor();
    _monitorStart = Date.now();
    _monitorAutoScroll = true;
    monitorLogs.value = [];
    pushLog('Pipeline', '任务初始化完成');
  }

  function finishMonitor(modules: typeof project.script.modules) {
    const sceneTimes = modules.filter(m => m.start_time > 0).map(m => m.start_time);
    for (let i = 0; i < sceneTimes.length; i++) {
      const m = modules.find(x => x.start_time === sceneTimes[i]);
      const type = m ? typeLabel(m.type) : '视频段';
      const typeMap: Record<string, string> = { title: '开头 Opening', video_segment: '高潮 Highlight', transition: '转场 Transition', effect: '特效 Effect' };
      // 置信度来自 pipeline 计算的 energy_peak_value（音频能量峰值，0~1）
      const detail = (m as any)?.detail;
      const confidence = detail?.energy_peak_value != null
        ? (detail.energy_peak_value as number).toFixed(2)
        : null;
      const confStr = confidence ? ` (峰值: <b>${confidence}</b>)` : '';
      pushLog('规则引擎', `片段 ${i} (${fmtDuration(sceneTimes[i])}): 匹配规则 → 类型: <b>${typeMap[type] || type}</b>${confStr}`, 'data', '✅', true);
    }
    pushLog('规则引擎', `候选排序完成，共 <b>${modules.length}</b> 个模块候选`, 'ok', '✅');
    const elapsed = ((Date.now() - _monitorStart) / 1000).toFixed(2);
    pushLog('Pipeline', `分析完成。总耗时: <b>${elapsed}s</b>，输出: <b>${modules.length}</b> 个模块`, 'ok', '✅');
    analysisActualTime.value = `${elapsed}s`;
    stopMonitor();
  }

  function stopMonitor() {
    if (_monitorTimer) { clearInterval(_monitorTimer); _monitorTimer = null; }
  }

  /* ═══════════════════════════════════
     File input (upload trigger)
     ═══════════════════════════════════ */
  const videoInputRef = ref<HTMLInputElement | null>(null);
  function triggerVideoUpload() { videoInputRef.value?.click(); }

  /* ═══════════════════════════════════
     Video events
     ═══════════════════════════════════ */
  function onVideoTimeUpdate(el: HTMLVideoElement | null) {
    if (el) videoCurrentTime.value = el.currentTime;
  }

  const videoSrc = computed(() => {
    if (!project.videoId) return '';
    const base = project.apiBaseUrl.replace(/\/+$/, '');
    return `${base}/upload/video/${project.videoId}`;
  });

  function seekVideo(time: number) {
    project.seekTo(time);
    const videoEl = document.querySelector('video') as HTMLVideoElement | null;
    if (videoEl) videoEl.currentTime = time;
  }

  /* ═══════════════════════════════════
     Status helpers
     ═══════════════════════════════════ */
  const statusLabel = computed(() => {
    if (project.analysisStatus === 'completed') return '分析完成';
    if (project.analysisStatus === 'processing') return '分析中…';
    const m: Record<string, string> = { idle: '待上传', uploading: '上传中', done: '已就绪', error: '失败' };
    return m[project.uploadStatus] || project.uploadStatus;
  });

  const statusBadgeClass = computed(() => {
    if (project.analysisStatus === 'completed') return 'badge--done';
    if (project.analysisStatus === 'processing') return 'badge--uploading';
    const m: Record<string, string> = { idle: '', uploading: 'badge--uploading', done: 'badge--done', error: 'badge--error' };
    return m[project.uploadStatus] || '';
  });

  /* ═══════════════════════════════════
     Video type presets
     ═══════════════════════════════════ */

  /* ═══════════════════════════════════
     Module helpers
     ═══════════════════════════════════ */
  const typeIcon = (t: ModuleType): string => {
    const m: Record<ModuleType, string> = { title: 'O', video_segment: 'H', subtitle: 'S', transition: 'T', audio: 'A', effect: 'E' };
    return m[t] || '?';
  };
  const typeLabel = (t: ModuleType): string => {
    const m: Record<ModuleType, string> = {
      title: 'Opening 开头', video_segment: 'Highlight 高潮', subtitle: '字幕',
      transition: 'Transition 转场', audio: '音频', effect: 'Effect 特效',
    };
    return m[t] || t;
  };

  /* ═══════════════════════════════════
     Selected module detail
     ═══════════════════════════════════ */
  const sceneTags = computed(() => {
    const m = project.selectedModule as any;
    if (!m || !m.detail) return '[无]';
    return (m.detail.scene_tags || ['分析中…']).map((t: string) => `[${t}]`).join(' ');
  });
  const detailData = computed(() => {
    const m = project.selectedModule as any;
    return m?.detail || null;
  });

  /* ═══════════════════════════════════
     Markers (analysis nodes)
     ═══════════════════════════════════ */
  const markers = computed(() => {
    return project.modules
      .filter(mod => mod.start_time > 0)
      .map(mod => ({
        time: mod.start_time,
        type: mod.type,
        label: typeLabel(mod.type),
      }));
  });

  /* ═══════════════════════════════════
     Module card drag-reorder
     ═══════════════════════════════════ */
  let _dragIdx = -1;

  function onDragStartRow(i: number, e: DragEvent) {
    _dragIdx = i;
    e.dataTransfer?.setData('text/plain', String(i));
    e.dataTransfer!.effectAllowed = 'move';
  }
  function onDragOverRow(_e: DragEvent) { /* needed for drop */ }
  function onDragLeaveRow(_e: DragEvent) { /* noop */ }
  function onDropRow(e: DragEvent, toIdx: number) {
    e.preventDefault();
    if (_dragIdx < 0 || _dragIdx === toIdx) return;
    const mods = [...project.modules];
    const [moved] = mods.splice(_dragIdx, 1);
    mods.splice(toIdx, 0, moved);
    project.script.modules = mods;
    _dragIdx = -1;
  }

  function moveModuleUp(i: number) {
    if (i <= 0) return;
    const mods = [...project.modules];
    [mods[i - 1], mods[i]] = [mods[i], mods[i - 1]];
    project.script.modules = mods;
  }
  function moveModuleDown(i: number) {
    if (i >= project.modules.length - 1) return;
    const mods = [...project.modules];
    [mods[i], mods[i + 1]] = [mods[i + 1], mods[i]];
    project.script.modules = mods;
  }

  function addNewModule() {
    const mod = {
      id: crypto.randomUUID(),
      type: 'video_segment' as ModuleType,
      label: '',
      start_time: 0,
      duration: 5,
      track_index: 0,
      params: {},
      children: [],
    };
    project.addModule(mod);
  }

  function onModuleLabel(id: string, val: string) {
    project.updateModule(id, { label: val });
  }

  /* ═══════════════════════════════════
     Script editing
     ═══════════════════════════════════ */
  function onScriptEdit(val: string) {
    moduleScript.value = val;
    if (project.selectedModule) {
      project.updateModule(project.selectedModule.id, {
        params: { ...project.selectedModule.params, text_content: val },
      });
    }
  }

  function toggleExportFmt() { showExportFmt.value = !showExportFmt.value; }

  function doExportScript(fmt: string) {
    showExportFmt.value = false;
    const mods = project.selectedModule ? [project.selectedModule] : project.script.modules;
    let content = '';
    let ext = 'txt';
    if (fmt === 'json') {
      content = JSON.stringify(mods, null, 2);
      ext = 'json';
    } else if (fmt === 'srt') {
      content = mods.map((m, i) =>
        `${i + 1}\n${fmtTimeSrt(m.start_time)} --> ${fmtTimeSrt(m.start_time + m.duration)}\n${m.label || typeLabel(m.type)}\n`
      ).join('\n');
      ext = 'srt';
    } else {
      content = mods.map(m =>
        `${typeLabel(m.type)} (${fmtDuration(m.start_time)} - ${fmtDuration(m.start_time + m.duration)}): ${m.params?.text_content || ''}`
      ).join('\n\n');
    }
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `script.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  /* ═══════════════════════════════════
     Upload
     ═══════════════════════════════════ */
  async function doUpload(file: File) {
    uploadFileSize.value = file.size;
    project.setUploadStatus('uploading');
    project.clearError();
    try {
      const base = project.apiBaseUrl.replace(/\/+$/, '');
      const fd = new FormData();
      fd.append('file', file);
      fd.append('title', file.name.replace(/\.[^.]+$/, ''));
      const res = await fetch(`${base}/upload`, { method: 'POST', body: fd });
      if (!res.ok) throw new Error(`Upload failed: HTTP ${res.status}`);
      const data: UploadResult = await res.json();
      // ── 先设 metadata，再设 videoId，确保 watch(videoId) 触发时 metadata 已就绪 ──
      project.setMetadata({
        title: file.name,
        fps: data.fps ?? 30,
        total_duration: data.duration ?? 0,
        resolution: { width: data.width ?? 1920, height: data.height ?? 1080 },
        source_video_id: data.video_id,
      });
      project.setVideoId(data.video_id);
      project.setUploadStatus('done');
      uploadFileSize.value = data.size_bytes || file.size;
      uploadFileName.value = file.name;
      startMonitor();
      pushLog('Pipeline', `视频已上传：${file.name} (${fmtSize(data.size_bytes || file.size)})`);
      pushLog('Pipeline', `分辨率 ${data.width}x${data.height}，时长 ${fmtDuration(data.duration || 0)}，帧率 ${data.fps || 30} fps`);
    } catch (err: any) {
      project.setUploadStatus('error');
      project.setError(err.message ?? '上传失败');
    }
  }

  function onDrop(e: DragEvent) {
    dragOver.value = false;
    const file = e.dataTransfer?.files?.[0];
    if (file && file.type.startsWith('video/')) doUpload(file);
  }

  function onVideoSelected(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) doUpload(file);
    input.value = '';
  }

  /* ═══════════════════════════════════
     Analyze
     ═══════════════════════════════════ */
  async function handleAnalyze() {
    if (!project.videoId) return;
    project.setAnalysisStatus('processing');
    project.clearError();
    startMonitor();
    try {
      const base = project.apiBaseUrl.replace(/\/+$/, '');
      // 1) 提交分析任务
      const res = await fetch(`${base}/analyze/${project.videoId}?video_type=${videoType.value}`, { method: 'POST' });
      if (!res.ok) throw new Error(`Analyze request failed: HTTP ${res.status}`);
      pushLog('Pipeline', '分析任务已提交，建立实时推送连接…');

      // 2) 通过 SSE 实时接收 segment 事件
      const sseUrl = `${base}/analyze/${project.videoId}/stream`;
      const es = new EventSource(sseUrl);

      const completed = await new Promise<{ moduleCount: number }>((resolve, reject) => {
        const timeout = setTimeout(() => {
          es.close();
          reject(new Error('分析超时（20 分钟）'));
        }, 20 * 60 * 1000);

        es.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'segment') {
              const mod = data.module;
              pushLog('Segment', `#${data.index} ${mod.type} @ ${fmtDuration(mod.start_time)} — ${mod.label || ''}`, 'data', '📦');
            } else if (data.type === 'done') {
              clearTimeout(timeout);
              resolve({ moduleCount: data.total });
            } else if (data.type === 'error') {
              clearTimeout(timeout);
              reject(new Error(data.message || '分析异常'));
            }
          } catch { /* ignore parse errors */ }
        };

        es.onerror = () => {
          clearTimeout(timeout);
          reject(new Error('SSE 连接中断'));
        };
      });

      es.close();
      pushLog('Pipeline', `实时推送完成，共接收 <b>${completed.moduleCount}</b> 个模块，获取完整脚本…`, 'ok', '✅');

      // 3) 拉取完整结果（含 metadata / tracks）
      const finalRes = await fetch(`${base}/analyze/${project.videoId}`);
      if (!finalRes.ok) throw new Error(`获取分析结果失败: HTTP ${finalRes.status}`);
      const result: AnalysisResult = await finalRes.json();
      if (result.script) {
        // 保留上传阶段更准确的元数据（cv2 实测分辨率/帧率，用户文件名）
        const prevMeta = project.script.metadata;
        const merged = {
          ...result.script,
          metadata: {
            ...result.script.metadata,
            title: prevMeta.title || result.script.metadata.title,
            fps: prevMeta.fps || result.script.metadata.fps,
            total_duration: prevMeta.total_duration || result.script.metadata.total_duration,
            resolution: {
              width: prevMeta.resolution.width || result.script.metadata.resolution.width,
              height: prevMeta.resolution.height || result.script.metadata.resolution.height,
            },
          },
        };
        project.setScript(merged);
        project.setAnalysisStatus('completed');
        finishMonitor(merged.metadata.total_duration ? merged.modules : result.script.modules);
      } else {
        throw new Error('分析结果为空（后端未返回 script）');
      }
    } catch (err: any) {
      project.setAnalysisStatus('failed');
      project.setError(err.message ?? '分析失败');
      pushLog('Pipeline', '异常: ' + (err.message ?? '未知'), 'err', '⚠');
      stopMonitor();
    }
  }

  /* ═══════════════════════════════════
     Export
     ═══════════════════════════════════ */
  async function handleExport() {
    if (!project.videoId || project.modules.length === 0) return;
    project.setExportStatus('processing');
    project.clearError();
    exportDownloadUrl.value = null;

    const [w, h] = exportResolution.value.split('x').map(Number);
    project.setMetadata({ resolution: { width: w, height: h } });

    try {
      const base = project.apiBaseUrl.replace(/\/+$/, '');
      const scriptToSend = {
        ...project.script,
        metadata: { ...project.script.metadata },
      };

      const res = await fetch(`${base}/export/${project.videoId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scriptToSend),
      });
      if (!res.ok) throw new Error(`导出请求失败: HTTP ${res.status}`);

      for (let i = 0; i < 600; i++) {
        await sleep(2000);
        const pollRes = await fetch(`${base}/export/${project.videoId}`);
        if (!pollRes.ok) throw new Error(`轮询失败: HTTP ${pollRes.status}`);

        const result: ExportResult = await pollRes.json();
        if (result.status === 'completed') {
          project.setExportStatus('completed');
          if (result.output_path) {
            exportDownloadUrl.value = `${base}${result.output_path}`;
          }
          return;
        }
        if (result.status === 'failed') throw new Error(result.error ?? '导出失败');
      }
      throw new Error('导出超时');
    } catch (err: any) {
      project.setExportStatus('failed');
      project.setError(err.message ?? '导出失败');
    }
  }

  /* ═══════════════════════════════════
     Shots callback
     ═══════════════════════════════════ */
  function onShotsChange(shots: Array<{ index: number; text: string; duration: string; ref_material_ids: string[] }>) {
    // Rebuild modules from shots
    const newModules = shots.map((shot, i) => ({
      id: crypto.randomUUID(),
      type: 'video_segment' as ModuleType,
      label: `Shot ${i + 1}`,
      start_time: i * 5,
      duration: parseFloat(shot.duration) || 5,
      track_index: 0,
      params: { text_content: shot.text, ref_material_ids: shot.ref_material_ids },
    }));
    project.script.modules = newModules as any;
  }

  /* ═══════════════════════════════════
     Formatting helpers
     ═══════════════════════════════════ */
  const fmtEta = (durSec: number): string => {
    const fps = project.script.metadata.fps || 30;
    const isApi = project.visionProvider === 'api' && !!project.visionApiUrl;
    const kf = Math.max(1, Math.ceil((durSec * fps) / (fps / 5) / Math.max(1, Math.ceil(durSec / 10))));
    const base = durSec * 0.25;
    const whisper = durSec * 0.6;
    const audio = durSec * 0.08;
    const ocr = kf * 0.12;
    const yolo = kf * 0.06;
    const api = isApi ? kf * 0.4 : 0;
    const total = Math.ceil((base + whisper + audio + ocr + yolo + api) * 1.15);
    if (total < 60) return `约 ${total} 秒`;
    const min = Math.floor(total / 60);
    const sec = total % 60;
    return sec > 0 ? `约 ${min} 分 ${sec} 秒` : `约 ${min} 分钟`;
  };

  const fmtDuration = (s: number): string => {
    if (!s || s <= 0) return '—';
    const min = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    const pad = (n: number) => String(n).padStart(2, '0');
    return min > 0 ? `${min}:${pad(sec)}` : `0:${pad(sec)}`;
  };

  const fmtSize = (bytes: number): string => {
    if (!bytes) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  function fmtTimeSrt(s: number): string {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const pad = (n: number, d = 2) => String(n).padStart(d, '0');
    return `${pad(h)}:${pad(m)}:${pad(Math.floor(sec))},${pad(Math.round((sec % 1) * 1000), 3)}`;
  }

  /* ═══════════════════════════════════
     Util
     ═══════════════════════════════════ */
  function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

  return {
    // UI state
    settingsOpen, dragOver, exportDownloadUrl, uploadFileSize, uploadFileName,
    videoCurrentTime, analysisActualTime, viewMode, moduleScript, showExportFmt,
    exportResolution, exportBitrate, exportSubtitles, exportFormat, videoType, VIDEO_TYPE_OPTIONS,
    // Monitor
    monitorLogs, onMonitorScroll, pushLog, startMonitor, finishMonitor, stopMonitor,
    // File input
    videoInputRef, triggerVideoUpload,
    // Video
    onVideoTimeUpdate, videoSrc, seekVideo,
    // Status
    statusLabel, statusBadgeClass,

    // Module helpers
    typeIcon, typeLabel,
    // Detail
    sceneTags, detailData,
    // Markers
    markers,
    // Module drag
    onDragStartRow, onDragOverRow, onDragLeaveRow, onDropRow,
    moveModuleUp, moveModuleDown, addNewModule, onModuleLabel,
    // Script
    onScriptEdit, toggleExportFmt, doExportScript,
    // Upload
    doUpload, onDrop, onVideoSelected,
    // Analyze
    handleAnalyze,
    // Export
    handleExport,
    // Shots
    onShotsChange,
    // Formatting
    fmtEta, fmtDuration, fmtSize, fmtTimeSrt,
  };
});
