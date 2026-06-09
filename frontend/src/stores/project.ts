import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import type { Metadata } from '../types/script';

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

export const useProjectStore = defineStore('project', () => {
  const metadata = ref<Metadata>({
    title: '未命名项目', description: '', author: '',
    created_at: new Date().toISOString(), total_duration: 0, source_video_id: '',
    fps: 30, resolution: { width: 1920, height: 1080 }, tags: [],
  });
  const videoId = ref<string | null>(null);
  const uploadStatus = ref<'idle'|'uploading'|'done'|'error'>('idle');
  const analysisStatus = ref<'idle'|'processing'|'completed'|'failed'>('idle');
  const exportStatus = ref<'idle'|'queued'|'processing'|'completed'|'failed'>('idle');
  const apiBaseUrl = ref(loadPersisted('apiBaseUrl', 'http://localhost:8000'));
  const llmApiKey = ref(loadPersisted('llmApiKey', ''));
  const llmApiUrl = ref(loadPersisted('llmApiUrl', ''));
  const modelName = ref(loadPersisted('modelName', 'qwen-vl-max'));
  const visionProvider = ref(loadPersisted('visionProvider', 'local'));
  const visionApiUrl = ref(loadPersisted('visionApiUrl', ''));
  const visionApiKey = ref(loadPersisted('visionApiKey', ''));
  const visionModel = ref(loadPersisted('visionModel', 'qwen-vl-max'));
  const errorMessage = ref<string | null>(null);

  function setMetadata(m: Partial<Metadata>) { metadata.value = { ...metadata.value, ...m }; }
  function setVideoId(id: string|null) { videoId.value = id; }
  function setUploadStatus(s: 'idle'|'uploading'|'done'|'error') { uploadStatus.value = s; }
  function setAnalysisStatus(s: 'idle'|'processing'|'completed'|'failed') { analysisStatus.value = s; }
  function setExportStatus(s: 'idle'|'queued'|'processing'|'completed'|'failed') { exportStatus.value = s; }
  function setApiBaseUrl(u: string) { apiBaseUrl.value = u; persist('apiBaseUrl', u); }
  function setLlmApiKey(k: string) { llmApiKey.value = k; persist('llmApiKey', k); }
  function setLlmApiUrl(u: string) { llmApiUrl.value = u; persist('llmApiUrl', u); }
  function setModelName(n: string) { modelName.value = n; persist('modelName', n); }
  function setVisionProvider(p: string) { visionProvider.value = p; persist('visionProvider', p); }
  function setVisionApiUrl(u: string) { visionApiUrl.value = u; persist('visionApiUrl', u); }
  function setVisionApiKey(k: string) { visionApiKey.value = k; persist('visionApiKey', k); }
  function setVisionModel(m: string) { visionModel.value = m; persist('visionModel', m); }
  function setError(m: string|null) { errorMessage.value = m; }
  function clearError() { errorMessage.value = null; }

  let _w = false;
  function wire() { if (_w) return; _w = true;
    watch(apiBaseUrl,v=>persist('apiBaseUrl',v)); watch(llmApiKey,v=>persist('llmApiKey',v));
    watch(llmApiUrl,v=>persist('llmApiUrl',v)); watch(modelName,v=>persist('modelName',v));
    watch(visionProvider,v=>persist('visionProvider',v)); watch(visionApiUrl,v=>persist('visionApiUrl',v));
    watch(visionApiKey,v=>persist('visionApiKey',v)); watch(visionModel,v=>persist('visionModel',v));
  }
  wire();

  return { metadata, videoId, uploadStatus, analysisStatus, exportStatus,
    apiBaseUrl, llmApiKey, llmApiUrl, modelName,
    visionProvider, visionApiUrl, visionApiKey, visionModel, errorMessage,
    setMetadata, setVideoId, setUploadStatus, setAnalysisStatus, setExportStatus,
    setApiBaseUrl, setLlmApiKey, setLlmApiUrl, setModelName,
    setVisionProvider, setVisionApiUrl, setVisionApiKey, setVisionModel,
    setError, clearError };
});
