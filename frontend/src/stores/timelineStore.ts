import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import type { Module, Track, DragPayload } from '../types/script';

// ═══════════════════════════════════════════════════════
//  Auto-save: debounced localStorage persistence
// ═══════════════════════════════════════════════════════

const SAVE_KEY = 'transvideo:timeline_modules';

function loadModules(): Module[] {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveModules(mods: Module[]) {
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(mods)); } catch { /* */ }
}

let _saveTimer: ReturnType<typeof setTimeout> | null = null;

function debounceSave(mods: Module[]) {
  if (_saveTimer) clearTimeout(_saveTimer);
  _saveTimer = setTimeout(() => { saveModules(mods); _saveTimer = null; }, 2000);
}

// ═══════════════════════════════════════════════════════

export const useTimelineStore = defineStore('timeline', () => {
  const modules = ref<Module[]>(loadModules());  // ← auto-restore from localStorage
  const tracks = ref<Track[]>([
    { index: 0, name: '视频轨道', type: 'video', muted: false, locked: false },
    { index: 1, name: '文字轨道', type: 'text', muted: false, locked: false },
    { index: 2, name: '音频轨道', type: 'audio', muted: false, locked: false },
  ]);
  const selectedModuleId = ref<string | null>(null);

  // ── Auto-save: debounce 2s on every modules change ──
  watch(modules, (val) => { debounceSave(val); }, { deep: true });

  const selectedModule = computed(() =>
    modules.value.find((m) => m.id === selectedModuleId.value) ?? null
  );

  const totalDuration = computed(() => {
    if (modules.value.length === 0) return 60;
    return Math.max(...modules.value.map((m) => m.start_time + m.duration));
  });

  const modulesByTrack = computed(() => {
    const map: Record<number, Module[]> = {};
    for (const mod of modules.value) {
      const idx = mod.track_index ?? 0;
      if (!map[idx]) map[idx] = [];
      map[idx].push(mod);
    }
    for (const key of Object.keys(map)) {
      map[Number(key)].sort((a, b) => a.start_time - b.start_time);
    }
    return map;
  });

  function resetTimeline() {
    modules.value = [];
    selectedModuleId.value = null;
    localStorage.removeItem('transvideo:timeline_modules');
  }

  function setModules(list: Module[]) { modules.value = list; }
  function setTracks(list: Track[]) { tracks.value = list; }
  function selectModule(id: string | null) { selectedModuleId.value = id; }
  function addTrack(track: Track) { tracks.value = [...tracks.value, track]; }

  function addModule(mod: Module, pos?: number) {
    const list = [...modules.value];
    if (pos !== undefined && pos < list.length) list.splice(pos, 0, { ...mod });
    else list.push({ ...mod });
    modules.value = list;
  }

  function removeModule(id: string) {
    modules.value = modules.value.filter(m => m.id !== id);
    if (selectedModuleId.value === id) selectedModuleId.value = null;
  }

  function updateModule(id: string, updates: Partial<Module>) {
    const idx = modules.value.findIndex(m => m.id === id);
    if (idx !== -1) {
      modules.value[idx] = { ...modules.value[idx], ...updates };
      modules.value = [...modules.value];
    }
  }

  function reorderModule(payload: DragPayload, toTrack: number, insertIdx: number) {
    const list = [...modules.value];
    const idx = list.findIndex(m => m.id === payload.moduleId);
    if (idx === -1) return;
    const [moved] = list.splice(idx, 1);
    moved.track_index = toTrack;
    const trackMods = list.filter(m => m.track_index === toTrack);
    let globalIdx = list.length;
    if (insertIdx < trackMods.length) {
      globalIdx = list.findIndex(m => m.id === trackMods[insertIdx]?.id);
    }
    if (globalIdx === -1) list.push(moved);
    else list.splice(globalIdx, 0, moved);
    modules.value = list;
  }

  return {
    modules, tracks, selectedModuleId, selectedModule, totalDuration, modulesByTrack,
    resetTimeline, setModules, setTracks, selectModule, addTrack,
    addModule, removeModule, updateModule, reorderModule,
  };
});
