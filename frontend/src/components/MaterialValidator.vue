<template>
  <div class="validator">
    <div class="validator__header">
      <span class="validator__title">素材校验</span>
      <button class="validator__refresh" @click="doCheck" :disabled="checking">
        {{ checking ? '检测中…' : '🔄 重新检测' }}
      </button>
      <button
        class="validator__fixall"
        @click="fixAll"
        :disabled="!fixableCount"
      >
        🛠 一键修复 ({{ fixableCount }})
      </button>
    </div>

    <!-- Summary bar -->
    <div class="validator__summary" v-if="results.length">
      <span class="validator__badge validator__badge--ok">✓ {{ okCount }} 正常</span>
      <span class="validator__badge validator__badge--broken">⚠ {{ brokenCount }} 缺失</span>
      <span class="validator__badge validator__badge--empty">○ {{ emptyCount }} 未填</span>
    </div>

    <div class="validator__body" v-if="results.length">
      <div
        v-for="(r, i) in results"
        :key="i"
        class="validator__item"
        :class="{ 'validator__item--broken': r.status !== 'ok' }"
        @click="selectModule(r.moduleId)"
      >
        <!-- Status icon -->
        <span class="validator__icon">{{ statusIcon(r.status) }}</span>

        <!-- Module info -->
        <div class="validator__info">
          <span class="validator__mod">{{ r.moduleType }} · {{ r.moduleLabel || '未命名' }}</span>
          <span class="validator__path" :class="'validator__path--' + r.status">
            {{ r.path || '(未填写)' }}
          </span>
        </div>

        <!-- Suggestions -->
        <div class="validator__actions" v-if="r.suggestions.length">
          <select
            class="validator__select"
            v-model="selectedSuggestion[i]"
            @click.stop
          >
            <option value="">选择补全…</option>
            <option v-for="s in r.suggestions" :key="s" :value="s">{{ s }}</option>
          </select>
          <button
            class="validator__apply"
            @click.stop="applySuggestion(i, r)"
            :disabled="!selectedSuggestion[i]"
          >
            ✓
          </button>
        </div>
        <span v-else-if="r.status !== 'ok'" class="validator__nosug">无建议</span>
      </div>
    </div>

    <div class="validator__empty" v-else-if="!checking">
      点击「重新检测」扫描素材路径
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useTimelineStore } from '../stores/timelineStore';
import { useProjectStore } from '../stores/project';

const timeline = useTimelineStore();
const project = useProjectStore();

// ── State ──
const checking = ref(false);
const results = ref<CheckResult[]>([]);
const selectedSuggestion = ref<string[]>([]);

interface CheckResult {
  moduleId: string;
  moduleType: string;
  moduleLabel: string;
  path: string;
  status: 'ok' | 'broken' | 'empty' | 'error';
  basename: string;
  suggestions: string[];
}

// ── Computed ──
const okCount = computed(() => results.value.filter(r => r.status === 'ok').length);
const brokenCount = computed(() => results.value.filter(r => r.status === 'broken').length);
const emptyCount = computed(() => results.value.filter(r => r.status === 'empty').length);
const fixableCount = computed(() => results.value.filter(r =>
  r.status !== 'ok' && r.suggestions.length > 0
).length);

// ── Check ──
async function doCheck() {
  checking.value = true;
  try {
    // Gather all source paths from modules
    const items: { moduleId: string; moduleType: string; moduleLabel: string; path: string }[] = [];
    for (const mod of timeline.modules) {
      const src = (mod as any).source;
      const path = (typeof src?.path === 'string') ? src.path : '';
      items.push({
        moduleId: mod.id,
        moduleType: mod.type,
        moduleLabel: mod.label || '',
        path,
      });
    }

    if (!items.length) {
      results.value = [];
      return;
    }

    const base = project.apiBaseUrl.replace(/\/+$/, '');
    const paths = items.map(it => it.path);
    const res = await fetch(`${base}/materials/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data: { results: { path: string; status: string; basename: string; suggestions: string[] }[] } = await res.json();

    results.value = items.map((item, idx) => ({
      moduleId: item.moduleId,
      moduleType: item.moduleType,
      moduleLabel: item.moduleLabel,
      path: item.path,
      status: (data.results[idx]?.status || 'error') as CheckResult['status'],
      basename: data.results[idx]?.basename || '',
      suggestions: data.results[idx]?.suggestions || [],
    }));

    selectedSuggestion.value = new Array(results.value.length).fill('');
  } catch (e) {
    console.warn('Material check failed:', e);
  } finally {
    checking.value = false;
  }
}

// ── Actions ──
function selectModule(id: string) {
  timeline.selectModule(id);
}

function applySuggestion(idx: number, r: CheckResult) {
  const suggestion = selectedSuggestion.value[idx];
  if (!suggestion || !r.moduleId) return;

  timeline.updateModule(r.moduleId, {
    source: {
      type: 'video',
      path: suggestion,
      start_offset: 0,
      end_offset: 0,
    },
  } as any);

  // Update local result
  results.value[idx] = { ...r, path: suggestion, status: 'ok', suggestions: [] };
  selectedSuggestion.value[idx] = '';
}

function fixAll() {
  for (let i = 0; i < results.value.length; i++) {
    const r = results.value[i];
    if (r.status !== 'ok' && r.suggestions.length > 0) {
      const suggestion = r.suggestions[0];
      timeline.updateModule(r.moduleId, {
        source: {
          type: 'video',
          path: suggestion,
          start_offset: 0,
          end_offset: 0,
        },
      } as any);
      results.value[i] = { ...r, path: suggestion, status: 'ok', suggestions: [] };
      selectedSuggestion.value[i] = '';
    }
  }
}

const statusIcon = (s: string): string => {
  if (s === 'ok') return '✅';
  if (s === 'broken') return '⚠️';
  if (s === 'empty') return '○';
  return '❓';
};
</script>

<style scoped>
.validator {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── Header ── */
.validator__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.validator__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-right: auto;
}
.validator__refresh,
.validator__fixall {
  border: none;
  border-radius: var(--radius-sm);
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
  transition: all var(--transition);
}
.validator__refresh {
  background: var(--bg-surface);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}
.validator__refresh:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.validator__fixall {
  background: var(--accent);
  color: #fff;
}
.validator__fixall:hover:not(:disabled) { background: var(--accent-hover); }
.validator__fixall:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Summary ── */
.validator__summary {
  display: flex;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.validator__badge {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
}
.validator__badge--ok { background: #1a7f3730; color: #1a7f37; }
.validator__badge--broken { background: #da363330; color: #da3633; }
.validator__badge--empty { background: var(--bg-hover); color: var(--text-muted); }

/* ── Body ── */
.validator__body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.validator__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  transition: background var(--transition);
}
.validator__item:hover { background: var(--bg-hover); }
.validator__item--broken { background: #da363308; }

.validator__icon { flex-shrink: 0; font-size: 14px; width: 20px; text-align: center; }

.validator__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.validator__mod {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.validator__path {
  font-size: 10px;
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.validator__path--broken { color: #da3633; }
.validator__path--empty { color: var(--text-muted); font-style: italic; }
.validator__path--ok { color: #1a7f37; }

/* ── Actions ── */
.validator__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.validator__select {
  max-width: 120px;
  padding: 2px 4px;
  font-size: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-primary);
}
.validator__apply {
  border: none;
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  font-size: 12px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
}
.validator__apply:disabled { opacity: 0.3; cursor: not-allowed; }
.validator__nosug {
  font-size: 10px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.validator__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
