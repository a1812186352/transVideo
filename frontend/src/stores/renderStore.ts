/**
 * Render store — real-time export progress via SSE, cancel support.
 *
 * Connects to ``GET /api/export/{jobId}/progress`` SSE endpoint and
 * exposes reactive ``renderProgress`` / ``renderStage`` for the UI.
 * Cancel via ``POST /api/export/{jobId}/cancel``.
 */
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { useProjectStore } from './project';

export const useRenderStore = defineStore('render', () => {
  const project = useProjectStore();

  /* ═══════════════════════════════════
     State
     ═══════════════════════════════════ */
  const renderProgress = ref(0);          // 0–100
  const renderStage = ref('');            // human-readable stage
  const renderEta = ref(0);               // seconds remaining
  const isRendering = ref(false);
  const jobId = ref<string | null>(null);

  let _eventSource: EventSource | null = null;

  /* ═══════════════════════════════════
     Subscribe
     ═══════════════════════════════════ */
  function subscribeProgress(videoId: string) {
    unsubscribe();
    jobId.value = videoId;
    isRendering.value = true;
    renderProgress.value = 0;
    renderStage.value = '排队中';

    const base = project.apiBaseUrl.replace(/\/+$/, '');
    const url = `${base}/export/${videoId}/progress`;

    _eventSource = new EventSource(url);

    _eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.progress !== undefined) {
          renderProgress.value = data.progress;
        }
        if (data.stage) {
          renderStage.value = data.stage;
        }
        if (data.eta !== undefined) {
          renderEta.value = data.eta;
        }
        // Completion signals
        if (data.progress === 100) {
          isRendering.value = false;
          unsubscribe();
        }
      } catch {
        // ignore malformed events
      }
    };

    _eventSource.onerror = () => {
      // SSE connection lost — fall back to polling
      _startPollFallback(videoId);
    };
  }

  /* ═══════════════════════════════════
     Fallback polling (when SSE fails)
     ═══════════════════════════════════ */
  let _pollTimer: ReturnType<typeof setInterval> | null = null;

  function _startPollFallback(videoId: string) {
    const base = project.apiBaseUrl.replace(/\/+$/, '');
    let attempts = 0;

    _pollTimer = setInterval(async () => {
      if (++attempts > 180) {  // 6 minutes max
        clearInterval(_pollTimer!);
        _pollTimer = null;
        return;
      }
      try {
        const res = await fetch(`${base}/export/${videoId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === 'completed') {
          renderProgress.value = 100;
          renderStage.value = '渲染完成';
          isRendering.value = false;
          clearInterval(_pollTimer!);
          _pollTimer = null;
        } else if (data.status === 'failed') {
          renderStage.value = `失败: ${data.error || '未知错误'}`;
          isRendering.value = false;
          clearInterval(_pollTimer!);
          _pollTimer = null;
        } else if (data.status === 'canceled') {
          renderStage.value = '已取消';
          isRendering.value = false;
          clearInterval(_pollTimer!);
          _pollTimer = null;
        } else {
          // Still processing — leave progress as-is (SSE was the real source)
        }
      } catch {
        // network error — keep trying
      }
    }, 2000);
  }

  /* ═══════════════════════════════════
     Cancel
     ═══════════════════════════════════ */
  async function cancelRender(): Promise<boolean> {
    if (!jobId.value) return false;
    const base = project.apiBaseUrl.replace(/\/+$/, '');
    try {
      const res = await fetch(`${base}/export/${jobId.value}/cancel`, {
        method: 'POST',
      });
      if (!res.ok) return false;
      renderStage.value = '取消中…';
      unsubscribe();
      return true;
    } catch {
      return false;
    }
  }

  /* ═══════════════════════════════════
     Cleanup
     ═══════════════════════════════════ */
  function unsubscribe() {
    if (_eventSource) {
      _eventSource.close();
      _eventSource = null;
    }
    if (_pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
  }

  function reset() {
    unsubscribe();
    renderProgress.value = 0;
    renderStage.value = '';
    renderEta.value = 0;
    isRendering.value = false;
    jobId.value = null;
  }

  return {
    renderProgress,
    renderStage,
    renderEta,
    isRendering,
    jobId,
    subscribeProgress,
    cancelRender,
    unsubscribe,
    reset,
  };
});
