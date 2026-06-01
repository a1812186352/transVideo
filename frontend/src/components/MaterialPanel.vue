<template>
  <div class="mat-panel">
    <!-- ═══ Tabs ═══ -->
    <div class="mat-tabs">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="mat-tab"
        :class="{ 'mat-tab--active': activeTab === t.key }"
        @click="activeTab = t.key"
      >{{ t.label }}</button>
    </div>

    <!-- ═══ Tab: 素材 ═══ -->
    <div v-show="activeTab === 'materials'" class="mat-content">
      <!-- Upload zone -->
      <div
        class="mat-upload"
        :class="{ 'mat-upload--dragover': dragOver }"
        @click="triggerUpload"
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop.prevent="onDrop"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <span>拖入素材到时间轴</span>
      </div>
      <input ref="fileInput" type="file" accept="image/*,video/*" multiple hidden @change="onFilesSelected" />

      <!-- Materials grid (2 columns) -->
      <div v-if="materials.length" class="mat-grid">
        <div
          v-for="mat in materials"
          :key="mat.material_id"
          class="mat-card"
          draggable="true"
          @dragstart="onDragStart(mat.material_id, $event)"
        >
          <img v-if="mat.thumbnail" :src="mat.thumbnail" class="mat-card__thumb" :alt="mat.filename" />
          <div v-else class="mat-card__thumb mat-card__thumb--empty">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
          </div>
          <div class="mat-card__name">{{ mat.filename }}</div>
        </div>
      </div>
      <div v-else class="mat-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3">
          <rect x="2" y="2" width="20" height="20" rx="2" />
          <circle cx="8" cy="8" r="2" />
          <path d="m22 16-5-5-5 5" />
          <path d="m12 18 3-3 4 4" />
        </svg>
        <span>拖入视频文件开始分析</span>
      </div>
    </div>

    <!-- ═══ Tab: 脚本 ═══ -->
    <div v-show="activeTab === 'script'" class="mat-content">
      <textarea
        class="mat-script"
        :value="scriptText"
        @input="onScriptEdit"
        placeholder="在此编辑脚本内容…"
        spellcheck="false"
      />
    </div>

    <!-- ═══ Tab: 模板 ═══ -->
    <div v-show="activeTab === 'templates'" class="mat-content">
      <div class="mat-grid">
        <div v-for="tpl in templates" :key="tpl.id" class="mat-card mat-card--tpl">
          <div class="mat-card__thumb mat-card__thumb--tpl">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="3" width="20" height="14" rx="2" />
              <line x1="8" y1="21" x2="16" y2="21" />
              <line x1="12" y1="17" x2="12" y2="21" />
            </svg>
          </div>
          <div class="mat-card__name">{{ tpl.name }}</div>
        </div>
      </div>
      <div v-if="!templates.length" class="mat-empty mat-empty--small">暂无模板</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue';
import { useProjectStore } from '../stores/project';

const store = useProjectStore();

// ── Tabs ──
const tabs = [
  { key: 'materials', label: '素材' },
  { key: 'script',    label: '脚本' },
  { key: 'templates', label: '模板' },
];
const activeTab = ref('materials');

// ── Script tab ──
const scriptText = computed(() => {
  // Build script text from store modules
  return store.modules.map(m => `${m.label || ''}: ${m.params?.text_content || ''}`).join('\n\n');
});
function onScriptEdit(e: Event) {
  const val = (e.target as HTMLTextAreaElement).value;
  // store script text back
}

// ── Templates ──
interface Template { id: string; name: string; }
const templates = ref<Template[]>([]);

// ── Materials ──
interface Material {
  material_id: string;
  filename: string;
  ext: string;
  size_bytes: number;
  thumbnail: string;
}
const props = defineProps<{ apiBaseUrl: string }>();
const materials = ref<Material[]>([]);
const uploading = ref(false);
const dragOver = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

onMounted(() => loadMaterials());

async function loadMaterials() {
  try {
    const base = props.apiBaseUrl.replace(/\/+$/, '');
    const res = await fetch(`${base}/materials/list`);
    if (res.ok) materials.value = await res.json();
  } catch { /* ignore */ }
}

function triggerUpload() { fileInput.value?.click(); }

function onDrop(e: DragEvent) {
  dragOver.value = false;
  const files = e.dataTransfer?.files;
  if (files) uploadFiles(Array.from(files));
}

function onFilesSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files) uploadFiles(Array.from(input.files));
  input.value = '';
}

async function uploadFiles(files: File[]) {
  uploading.value = true;
  const base = props.apiBaseUrl.replace(/\/+$/, '');
  for (const file of files) {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch(`${base}/materials/upload`, { method: 'POST', body: fd });
      if (res.ok) {
        const mat = await res.json();
        materials.value.unshift(mat);
      }
    } catch { /* skip */ }
  }
  uploading.value = false;
}

function onDragStart(id: string, e: DragEvent) {
  e.dataTransfer?.setData('application/x-material-id', id);
  e.dataTransfer!.effectAllowed = 'copy';
}
</script>

<style scoped>
.mat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* ── Tabs ── */
.mat-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  padding: 0 12px;
  flex-shrink: 0;
}
.mat-tab {
  padding: 7px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  border: none;
  background: transparent;
  border-bottom: 2px solid transparent;
  transition: all var(--transition);
}
.mat-tab--active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
.mat-tab:hover {
  color: var(--text-secondary);
}

/* ── Content ── */
.mat-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

/* ── Upload zone ── */
.mat-upload {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
  transition: all var(--transition);
  margin-bottom: 8px;
}
.mat-upload:hover,
.mat-upload--dragover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-subtle);
}

/* ── Grid (2 columns) ── */
.mat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

/* ── Card ── */
.mat-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: grab;
  transition: border-color var(--transition);
}
.mat-card:hover {
  border-color: var(--accent);
}
.mat-card:active {
  cursor: grabbing;
}
.mat-card__thumb {
  width: 100%;
  aspect-ratio: 16/9;
  object-fit: cover;
  display: block;
  background: var(--bg-surface);
}
.mat-card__thumb--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}
.mat-card__thumb--tpl {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}
.mat-card__name {
  padding: 4px 6px;
  font-size: 10px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Empty state ── */
.mat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  min-height: 120px;
  color: var(--text-muted);
  font-size: 12px;
}
.mat-empty--small {
  min-height: 60px;
}

/* ── Script textarea ── */
.mat-script {
  width: 100%;
  height: 100%;
  min-height: 200px;
  padding: 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  resize: none;
  outline: none;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.mat-script:focus {
  box-shadow: inset 0 0 0 1px var(--accent);
}
.mat-script::placeholder {
  color: var(--text-muted);
}
</style>
