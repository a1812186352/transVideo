import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import type {
  Module,
  MigratableScript,
  Track,
  Metadata,
  DragPayload,
} from '../types/script';

/** Known stale defaults to auto-purge from localStorage */
const STALE_DEFAULTS: Record<string, string> = {
  apiBaseUrl: 'http://localhost:8001',
};

/** Load a value from localStorage, falling back to a default */
function loadPersisted<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(`transvideo:${key}`);
    if (raw !== null) {
      const val = JSON.parse(raw) as T;
      // Auto-purge known stale defaults
      if (typeof val === 'string' && key in STALE_DEFAULTS && val === STALE_DEFAULTS[key]) {
        localStorage.removeItem(`transvideo:${key}`);
        return fallback;
      }
      return val;
    }
  } catch { /* ignore parse errors */ }
  return fallback;
}

/** Persist a value to localStorage */
function persist(key: string, value: unknown) {
  try {
    localStorage.setItem(`transvideo:${key}`, JSON.stringify(value));
  } catch { /* ignore quota / access errors */ }
}

/**
 * Pinia store for project state management.
 *
 * Manages the module list, selection state, track definitions,
 * and drag-and-drop reordering logic.
 */
export const useProjectStore = defineStore('project', () => {
  // --- State ---
  const script = ref<MigratableScript>({
    version: '1.0.0',
    metadata: {
      title: '未命名项目',
      description: '',
      author: '',
      created_at: new Date().toISOString(),
      total_duration: 0,
      source_video_id: '',
      fps: 30,
      resolution: { width: 1920, height: 1080 },
      tags: [],
    },
    modules: [],
    tracks: [
      { index: 0, name: '视频轨道', type: 'video', muted: false, locked: false },
      { index: 1, name: '文字轨道', type: 'text', muted: false, locked: false },
      { index: 2, name: '音频轨道', type: 'audio', muted: false, locked: false },
    ],
  });

  const selectedModuleId = ref<string | null>(null);
  const isPlaying = ref(false);
  const currentTime = ref(0);
  const zoomLevel = ref(1.0);  // pixels per second

  // --- API / Backend state ---
  const videoId = ref<string | null>(null);
  const uploadStatus = ref<'idle' | 'uploading' | 'done' | 'error'>('idle');
  const analysisStatus = ref<'idle' | 'processing' | 'completed' | 'failed'>('idle');
  const exportStatus = ref<'idle' | 'queued' | 'processing' | 'completed' | 'failed'>('idle');
  const apiBaseUrl = ref<string>(loadPersisted('apiBaseUrl', 'http://localhost:8000'));
  const llmApiKey = ref<string>(loadPersisted('llmApiKey', ''));
  const llmApiUrl = ref<string>(loadPersisted('llmApiUrl', ''));
  const modelName = ref<string>(loadPersisted('modelName', 'qwen-vl-max'));
  const visionProvider = ref<string>(loadPersisted('visionProvider', 'local'));
  const visionApiUrl = ref<string>(loadPersisted('visionApiUrl', ''));
  const visionApiKey = ref<string>(loadPersisted('visionApiKey', ''));
  const visionModel = ref<string>(loadPersisted('visionModel', 'qwen-vl-max'));
  const errorMessage = ref<string | null>(null);

  // --- Getters ---
  const modules = computed(() => script.value.modules);

  const tracks = computed(() => script.value.tracks);

  const selectedModule = computed(() =>
    script.value.modules.find((m) => m.id === selectedModuleId.value) ?? null
  );

  const totalDuration = computed(() => {
    if (script.value.modules.length === 0) return 60; // default 60s
    return Math.max(
      ...script.value.modules.map((m) => m.start_time + m.duration)
    );
  });

  /** Group modules by track index */
  const modulesByTrack = computed(() => {
    const map: Record<number, Module[]> = {};
    for (const mod of script.value.modules) {
      const trackIdx = mod.track_index ?? 0;
      if (!map[trackIdx]) map[trackIdx] = [];
      map[trackIdx].push(mod);
    }
    // Sort each track by start_time
    for (const key of Object.keys(map)) {
      map[Number(key)].sort((a, b) => a.start_time - b.start_time);
    }
    return map;
  });

  // --- Actions ---
  function setScript(newScript: MigratableScript) {
    script.value = newScript;
  }

  function setMetadata(metadata: Partial<Metadata>) {
    script.value.metadata = { ...script.value.metadata, ...metadata };
  }

  function addModule(mod: Module, position?: number) {
    const newModules = [...script.value.modules];
    if (position !== undefined && position < newModules.length) {
      newModules.splice(position, 0, { ...mod });
    } else {
      newModules.push({ ...mod });
    }
    script.value.modules = newModules;
  }

  function removeModule(moduleId: string) {
    script.value.modules = script.value.modules.filter(
      (m) => m.id !== moduleId
    );
    if (selectedModuleId.value === moduleId) {
      selectedModuleId.value = null;
    }
  }

  function updateModule(moduleId: string, updates: Partial<Module>) {
    const idx = script.value.modules.findIndex((m) => m.id === moduleId);
    if (idx !== -1) {
      script.value.modules[idx] = {
        ...script.value.modules[idx],
        ...updates,
      };
      // Trigger reactivity
      script.value.modules = [...script.value.modules];
    }
  }

  function reorderModule(payload: DragPayload, toTrackIndex: number, insertIndex: number) {
    const modules = [...script.value.modules];
    const modIdx = modules.findIndex((m) => m.id === payload.moduleId);
    if (modIdx === -1) return;

    const [movedModule] = modules.splice(modIdx, 1);
    movedModule.track_index = toTrackIndex;

    // Calculate new start_time based on insert position
    const trackModules = modules.filter((m) => m.track_index === toTrackIndex);
    if (insertIndex === 0) {
      movedModule.start_time = 0;
    } else if (insertIndex >= trackModules.length) {
      const lastMod = trackModules[trackModules.length - 1];
      movedModule.start_time = lastMod
        ? lastMod.start_time + lastMod.duration
        : 0;
    } else {
      const prevMod = trackModules[insertIndex - 1];
      movedModule.start_time = prevMod
        ? prevMod.start_time + prevMod.duration
        : 0;
    }

    // Insert at correct global position
    const globalInsertIdx = modules.findIndex(
      (m) => m.id === trackModules[insertIndex]?.id
    );
    if (globalInsertIdx === -1) {
      modules.push(movedModule);
    } else {
      modules.splice(globalInsertIdx, 0, movedModule);
    }

    script.value.modules = modules;
  }

  function selectModule(moduleId: string | null) {
    selectedModuleId.value = moduleId;
  }

  function addTrack(track: Track) {
    script.value.tracks = [...script.value.tracks, track];
  }

  function setZoom(level: number) {
    zoomLevel.value = Math.max(0.1, Math.min(5.0, level));
  }

  function play() {
    isPlaying.value = true;
  }

  function pause() {
    isPlaying.value = false;
  }

  function seekTo(time: number) {
    currentTime.value = Math.max(0, time);
  }

  // --- API actions ---
  function setVideoId(id: string | null) {
    videoId.value = id;
  }

  function setUploadStatus(status: 'idle' | 'uploading' | 'done' | 'error') {
    uploadStatus.value = status;
  }

  function setAnalysisStatus(status: 'idle' | 'processing' | 'completed' | 'failed') {
    analysisStatus.value = status;
  }

  function setExportStatus(status: 'idle' | 'queued' | 'processing' | 'completed' | 'failed') {
    exportStatus.value = status;
  }

  function setApiBaseUrl(url: string) {
    apiBaseUrl.value = url;
    persist('apiBaseUrl', url);
  }

  function setLlmApiKey(key: string) {
    llmApiKey.value = key;
    persist('llmApiKey', key);
  }

  function setLlmApiUrl(url: string) {
    llmApiUrl.value = url;
    persist('llmApiUrl', url);
  }

  function setModelName(name: string) {
    modelName.value = name;
    persist('modelName', name);
  }

  function setVisionProvider(p: string) {
    visionProvider.value = p;
    persist('visionProvider', p);
  }

  function setVisionApiUrl(url: string) {
    visionApiUrl.value = url;
    persist('visionApiUrl', url);
  }

  function setVisionApiKey(key: string) {
    visionApiKey.value = key;
    persist('visionApiKey', key);
  }

  function setVisionModel(m: string) {
    visionModel.value = m;
    persist('visionModel', m);
  }

  function setError(message: string | null) {
    errorMessage.value = message;
  }

  function clearError() {
    errorMessage.value = null;
  }

  // Persist-on-change watchers (initialised once when store is first used)
  let _persistWired = false;
  function wirePersist() {
    if (_persistWired) return;
    _persistWired = true;
    watch(apiBaseUrl, (v) => persist('apiBaseUrl', v));
    watch(llmApiKey, (v) => persist('llmApiKey', v));
    watch(llmApiUrl, (v) => persist('llmApiUrl', v));
    watch(modelName, (v) => persist('modelName', v));
    watch(visionProvider, (v) => persist('visionProvider', v));
    watch(visionApiUrl, (v) => persist('visionApiUrl', v));
    watch(visionApiKey, (v) => persist('visionApiKey', v));
    watch(visionModel, (v) => persist('visionModel', v));
  }
  wirePersist();

  return {
    // State
    script,
    selectedModuleId,
    isPlaying,
    currentTime,
    zoomLevel,
    // API / Backend state
    videoId,
    uploadStatus,
    analysisStatus,
    exportStatus,
    apiBaseUrl,
    llmApiKey,
    llmApiUrl,
    modelName,
    visionProvider,
    visionApiUrl,
    visionApiKey,
    visionModel,
    errorMessage,
    // Getters
    modules,
    tracks,
    selectedModule,
    totalDuration,
    modulesByTrack,
    // Actions
    setScript,
    setMetadata,
    addModule,
    removeModule,
    updateModule,
    reorderModule,
    selectModule,
    addTrack,
    setZoom,
    play,
    pause,
    seekTo,
    // API actions
    setVideoId,
    setUploadStatus,
    setAnalysisStatus,
    setExportStatus,
    setApiBaseUrl,
    setLlmApiKey,
    setLlmApiUrl,
    setModelName,
    setVisionProvider,
    setVisionApiUrl,
    setVisionApiKey,
    setVisionModel,
    setError,
    clearError,
  };
});
