import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import type { Metadata } from '../types/script';

// ═══════════════════════════════════════════════════════
//  Persistence helpers
// ═══════════════════════════════════════════════════════

const STALE_DEFAULTS: Record<string, string> = { apiBaseUrl: 'http://localhost:8001' };

function loadPersisted<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(`transvideo:${key}`);
    if (raw !== null) {
      const val = JSON.parse(raw) as T;
      if (typeof val === 'string' && key in STALE_DEFAULTS && val === STALE_DEFAULTS[key]) {
        localStorage.removeItem(`transvideo:${key}`);
        return fallback;
      }
      return val;
    }
  } catch { /* fallthrough */ }
  return fallback;
}

function persist(key: string, value: unknown) {
  try { localStorage.setItem(`transvideo:${key}`, JSON.stringify(value)); } catch { /* */ }
}

/** Save value to sessionStorage (lost on tab close). */
function sessionSave(key: string, value: unknown) {
  try { sessionStorage.setItem(`transvideo:${key}`, JSON.stringify(value)); } catch { /* */ }
}

/** Load from sessionStorage with TTL (default 1 hour). */
function sessionLoad<T>(key: string, fallback: T, ttlMs = 3600_000): T {
  try {
    const raw = sessionStorage.getItem(`transvideo:${key}`);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    // { value, ts } envelope
    if (parsed && typeof parsed === 'object' && 'ts' in parsed && 'value' in parsed) {
      if (Date.now() - parsed.ts > ttlMs) return fallback;
      return parsed.value;
    }
    return parsed;
  } catch { return fallback; }
}

const SS = {
  save(key: string, value: unknown) { sessionSave(key, { value, ts: Date.now() }); },
  load<T>(key: string, fb: T) { return sessionLoad(key, fb); },
  clear(key: string) { try { sessionStorage.removeItem(`transvideo:${key}`); } catch { /* */ } },
};

// ═══════════════════════════════════════════════════════
//  State machine definitions
// ═══════════════════════════════════════════════════════

interface Transition {
  from: string[];
  to: string;
}

const UPLOAD_TRANSITIONS: Transition[] = [
  { from: ['idle', 'error', 'done'],  to: 'uploading' },
  { from: ['uploading'],             to: 'done' },
  { from: ['uploading'],             to: 'error' },
  { from: ['done', 'error'],         to: 'idle' },
];

const ANALYSIS_TRANSITIONS: Transition[] = [
  { from: ['idle', 'failed', 'completed'], to: 'processing' },
  { from: ['processing'],                 to: 'completed' },
  { from: ['processing'],                 to: 'failed' },
  { from: ['completed', 'failed'],        to: 'idle' },
];

const EXPORT_TRANSITIONS: Transition[] = [
  { from: ['idle', 'failed'],        to: 'queued' },
  { from: ['idle', 'queued'],        to: 'processing' },
  { from: ['processing'],            to: 'completed' },
  { from: ['processing', 'queued'],  to: 'failed' },
  { from: ['completed', 'failed'],   to: 'idle' },
];

function checkTransition(
  transitions: Transition[],
  current: string,
  target: string,
  label: string,
): void {
  const allowed = transitions.find(t => t.to === target && t.from.includes(current));
  if (!allowed) {
    const msg = `[状态机] ${label}: ${current} → ${target} 非法`;
    console.warn(msg);
    throw new Error(msg);
  }
}

// ═══════════════════════════════════════════════════════
//  Store
// ═══════════════════════════════════════════════════════

type UploadStatus = 'idle' | 'uploading' | 'done' | 'error';
type AnalysisStatus = 'idle' | 'processing' | 'completed' | 'failed';
type ExportStatus = 'idle' | 'queued' | 'processing' | 'completed' | 'failed';

export const useProjectStore = defineStore('project', () => {
  // ── Session-recovered state ──
  const videoId = ref<string | null>(SS.load<string | null>('videoId', null));
  const uploadStatus = ref<UploadStatus>(SS.load<UploadStatus>('uploadStatus', 'idle'));
  const analysisStatus = ref<AnalysisStatus>(SS.load<AnalysisStatus>('analysisStatus', 'idle'));
  const exportStatus = ref<ExportStatus>(SS.load<ExportStatus>('exportStatus', 'idle'));

  const metadata = ref<Metadata>({
    title: '未命名项目', description: '', author: '',
    created_at: new Date().toISOString(), total_duration: 0, source_video_id: '',
    fps: 30, resolution: { width: 1920, height: 1080 }, tags: [],
  });
  const apiBaseUrl = ref(loadPersisted('apiBaseUrl', 'http://localhost:8000'));
  const llmApiKey = ref(loadPersisted('llmApiKey', ''));
  const llmApiUrl = ref(loadPersisted('llmApiUrl', ''));
  const modelName = ref(loadPersisted('modelName', 'qwen-vl-max'));
  const errorMessage = ref<string | null>(null);

  function setMetadata(m: Partial<Metadata>) { metadata.value = { ...metadata.value, ...m }; }

  function setVideoId(id: string | null) {
    videoId.value = id;
    if (id) SS.save('videoId', id); else SS.clear('videoId');
  }

  // ── Transactional status setters ──
  function setUploadStatus(s: UploadStatus) {
    checkTransition(UPLOAD_TRANSITIONS, uploadStatus.value, s, 'uploadStatus');
    uploadStatus.value = s;
    SS.save('uploadStatus', s);
  }

  function setAnalysisStatus(s: AnalysisStatus) {
    checkTransition(ANALYSIS_TRANSITIONS, analysisStatus.value, s, 'analysisStatus');
    analysisStatus.value = s;
    SS.save('analysisStatus', s);
  }

  function setExportStatus(s: ExportStatus) {
    checkTransition(EXPORT_TRANSITIONS, exportStatus.value, s, 'exportStatus');
    exportStatus.value = s;
    SS.save('exportStatus', s);
  }

  // ── Other setters ──
  function setApiBaseUrl(u: string) { apiBaseUrl.value = u; persist('apiBaseUrl', u); }
  function setLlmApiKey(k: string) { llmApiKey.value = k; persist('llmApiKey', k); }
  function setLlmApiUrl(u: string) { llmApiUrl.value = u; persist('llmApiUrl', u); }
  function setModelName(n: string) { modelName.value = n; persist('modelName', n); }
  function setError(m: string | null) { errorMessage.value = m; }
  function resetProject() {
    videoId.value = null;
    uploadStatus.value = 'idle';
    analysisStatus.value = 'idle';
    exportStatus.value = 'idle';
    errorMessage.value = null;
    metadata.value = {
      title: '未命名项目', description: '', author: '',
      created_at: new Date().toISOString(), total_duration: 0, source_video_id: '',
      fps: 30, resolution: { width: 1920, height: 1080 }, tags: [],
    };
    SS.clear('videoId');
    SS.clear('uploadStatus');
    SS.clear('analysisStatus');
    SS.clear('exportStatus');
  }

  function clearError() { errorMessage.value = null; }

  // Persist config watches
  let _w = false;
  function wire() { if (_w) return; _w = true;
    watch(apiBaseUrl, v => persist('apiBaseUrl', v));
    watch(llmApiKey, v => persist('llmApiKey', v));
    watch(llmApiUrl, v => persist('llmApiUrl', v));
    watch(modelName, v => persist('modelName', v));
  }
  wire();

  return {
    metadata, videoId, uploadStatus, analysisStatus, exportStatus,
    apiBaseUrl, llmApiKey, llmApiUrl, modelName, errorMessage,
    resetProject,
    setMetadata, setVideoId,
    setUploadStatus, setAnalysisStatus, setExportStatus,
    setApiBaseUrl, setLlmApiKey, setLlmApiUrl, setModelName,
    setError, clearError,
  };
});
