<template>
  <div class="api-settings-static">
    <div class="ass-field">
      <label for="ass-api-url">后端 API 地址</label>
      <input
        id="ass-api-url"
        type="text"
        :value="store.apiBaseUrl"
        @input="store.setApiBaseUrl(($event.target as HTMLInputElement).value)"
        placeholder="http://localhost:8000"
      />
    </div>

    <div class="ass-field">
      <label for="ass-llm-url">LLM API 地址</label>
      <input
        id="ass-llm-url"
        type="text"
        :value="store.llmApiUrl"
        @input="store.setLlmApiUrl(($event.target as HTMLInputElement).value)"
        placeholder="https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
      />
    </div>

    <div class="ass-field">
      <label for="ass-llm-key">LLM API 密钥</label>
      <input
        id="ass-llm-key"
        type="password"
        :value="store.llmApiKey"
        @input="store.setLlmApiKey(($event.target as HTMLInputElement).value)"
        placeholder="sk-..."
      />
    </div>

    <div class="ass-field">
      <label for="ass-model">模型名称</label>
      <input
        id="ass-model"
        type="text"
        :value="store.modelName"
        @input="store.setModelName(($event.target as HTMLInputElement).value)"
        placeholder="qwen-vl-max"
      />
    </div>

    <div class="ass-actions">
      <button
        class="ass-test-btn"
        :disabled="testing"
        @click="testConnection"
      >
        {{ testing ? '测试中…' : '测试连接' }}
      </button>
      <span v-if="testResult" class="ass-result" :class="{ 'ass-result--ok': testOk }">
        {{ testResult }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useProjectStore } from '../stores/project';

const store = useProjectStore();
const testing = ref(false);
const testResult = ref('');
const testOk = ref(false);

async function testConnection() {
  testing.value = true;
  testResult.value = '';
  try {
    const url = store.apiBaseUrl.replace(/\/+$/, '') + '/health';
    const res = await fetch(url, { method: 'GET', signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      testResult.value = '成功 — 后端可达';
      testOk.value = true;
    } else {
      testResult.value = `Error: HTTP ${res.status}`;
      testOk.value = false;
    }
  } catch (e: any) {
    testResult.value = `错误: ${e.message ?? '连接失败'}`;
    testOk.value = false;
  } finally {
    testing.value = false;
  }
}
</script>

<style scoped>
.api-settings-static {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ass-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ass-field label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 500;
}

.ass-field input {
  padding: 8px 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  font-family: var(--font-mono);
}

.ass-field input::placeholder {
  color: var(--text-muted);
}

.ass-field input:focus {
  outline: none;
  border-color: var(--accent-amber);
}

.ass-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}

.ass-test-btn {
  padding: 7px 16px;
  border: 1px solid var(--accent-amber);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--accent-amber);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.ass-test-btn:hover:not(:disabled) {
  background: var(--accent-amber-dim);
}

.ass-test-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.ass-result {
  font-size: 12px;
  color: var(--error);
}

.ass-result--ok {
  color: var(--success);
}
</style>
