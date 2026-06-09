import { createApp } from 'vue';
import { createPinia } from 'pinia';
import './assets/theme.css';
import App from './App.vue';
import { showErrorToast, parseError } from './utils/errorHandling';

// ── Theme init ──
const saved = localStorage.getItem('theme') || 'dark';
document.documentElement.setAttribute('data-theme', saved);
(globalThis as any).__theme = saved;
(globalThis as any).__toggleTheme = () => {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  (globalThis as any).__theme = next;
};

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);

// ── Global error handler — catches unhandled Vue errors ──
app.config.errorHandler = (err, _instance, info) => {
  console.error(`[Vue Error] (${info})`, err);
  showErrorToast(err);
};

// ── Global promise rejection handler ──
window.addEventListener('unhandledrejection', (event) => {
  console.error('[Unhandled Promise]', event.reason);
  showErrorToast(event.reason);
});

// ── Network error auto-retry interceptor ──
// Monkey-patches fetch with exponential backoff (max 3 retries)
// for GET requests that fail with network or 5xx errors.
installFetchRetry();

app.mount('#app');

// ═══════════════════════════════════════════════════════════════════
//  fetch auto-retry: 3 attempts, exponential backoff 1s → 2s → 4s
// ═══════════════════════════════════════════════════════════════════

function installFetchRetry() {
  const originalFetch = window.fetch.bind(window);
  const MAX_RETRIES = 3;
  const BASE_DELAY_MS = 1000;

  window.fetch = async function retryFetch(
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> {
    const method = (init?.method || 'GET').toUpperCase();
    // Only retry idempotent requests (GET / HEAD / OPTIONS)
    const retryable = method === 'GET' || method === 'HEAD' || method === 'OPTIONS';

    let lastError: unknown;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await originalFetch(input, init);

        // Retry on 5xx or 429
        if (retryable && attempt < MAX_RETRIES && (response.status >= 500 || response.status === 429)) {
          const delay = BASE_DELAY_MS * Math.pow(2, attempt);
          console.warn(
            `[fetch] ${response.status} on attempt ${attempt + 1}/${MAX_RETRIES + 1}, ` +
            `retrying in ${delay}ms...`,
          );
          await sleep(delay);
          continue;
        }

        return response;
      } catch (err) {
        lastError = err;

        if (!retryable || attempt >= MAX_RETRIES) {
          throw err;
        }

        const parsed = parseError(err);
        if (!parsed.recoverable && attempt >= MAX_RETRIES - 1) {
          throw err;
        }

        const delay = BASE_DELAY_MS * Math.pow(2, attempt);
        console.warn(
          `[fetch] Network error on attempt ${attempt + 1}/${MAX_RETRIES + 1}, ` +
          `retrying in ${delay}ms...`,
          err,
        );
        await sleep(delay);
      }
    }

    throw lastError;
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
