/** SSE connection manager with auto-reconnect and polling fallback.

 *  Provides a unified EventSource wrapper that:
 *  1. Connects to an SSE endpoint
 *  2. Auto-reconnects on disconnect (up to 3 tries)
 *  3. Falls back to HTTP polling if reconnection fails
 *  4. Emits connection state changes for UI feedback
 */

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'fallback' | 'disconnected';

export interface SseOptions {
  url: string;
  /** Callback for each parsed SSE message */
  onMessage: (data: unknown) => void;
  /** Callback on connection state change */
  onStateChange?: (state: ConnectionState) => void;
  /** Max reconnection attempts before switching to polling fallback (default 3) */
  maxRetries?: number;
  /** Polling interval in ms when in fallback mode (default 2000) */
  pollInterval?: number;
  /** Polling function — called periodically when fallback is active */
  pollFn?: () => Promise<void>;
}

export class SseClient {
  private es: EventSource | null = null;
  private retries = 0;
  private maxRetries: number;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private pollInterval: number;
  private _state: ConnectionState = 'disconnected';
  private destroyed = false;

  readonly options: SseOptions;

  constructor(options: SseOptions) {
    this.options = options;
    this.maxRetries = options.maxRetries ?? 3;
    this.pollInterval = options.pollInterval ?? 2000;
    this.connect();
  }

  get state(): ConnectionState { return this._state; }

  private setState(s: ConnectionState) {
    if (this._state === s || this.destroyed) return;
    this._state = s;
    this.options.onStateChange?.(s);
  }

  connect() {
    if (this.destroyed) return;
    this.setState('connecting');
    this.close();

    try {
      this.es = new EventSource(this.options.url);
    } catch {
      this.startFallback();
      return;
    }

    this.es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.options.onMessage(data);
      } catch { /* ignore parse errors */ }
    };

    this.es.onopen = () => {
      this.retries = 0;
      this.setState('connected');
    };

    this.es.onerror = () => {
      this.es?.close();
      this.es = null;

      if (this.retries < this.maxRetries) {
        this.retries++;
        this.setState('reconnecting');
        // Exponential backoff
        const delay = Math.min(1000 * Math.pow(2, this.retries), 10000);
        setTimeout(() => this.connect(), delay);
      } else {
        this.startFallback();
      }
    };
  }

  private startFallback() {
    if (this.destroyed) return;
    this.setState('fallback');
    this.pollTimer = setInterval(async () => {
      if (this.destroyed) { this.stopPolling(); return; }
      try {
        await this.options.pollFn?.();
      } catch { /* keep trying */ }
    }, this.pollInterval);
  }

  private stopPolling() {
    if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
  }

  close() {
    try { this.es?.close(); } catch { /* */ }
    this.es = null;
  }

  destroy() {
    this.destroyed = true;
    this.close();
    this.stopPolling();
    this.setState('disconnected');
  }
}
