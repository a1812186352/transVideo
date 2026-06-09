/**
 * frameCache.ts — 视频帧 GPU 纹理缓存
 *
 * 策略：
 *   1. 播放头前后各 PRELOAD_WINDOW 帧预加载
 *   2. LRU 淘汰，上限 MAX_FRAMES
 *   3. Canvas 离屏渲染 Image，seek 时先查缓存
 */

const MAX_FRAMES = 200;
const PRELOAD_WINDOW = 30;

interface CachedFrame {
  img: ImageBitmap | HTMLImageElement;
  time: number;
}

class FrameCache {
  private cache = new Map<number, CachedFrame>();
  private accessOrder: number[] = [];  // LRU queue (time keys)
  private baseUrl = '';
  private videoId = '';
  private fps = 30;
  private pending = new Set<number>();

  /** One shared OffscreenCanvas for decode (if supported) */
  private offscreen: OffscreenCanvas | null = null;

  configure(baseUrl: string, videoId: string, fps = 30) {
    if (this.baseUrl === baseUrl && this.videoId === videoId && this.fps === fps) return;
    this.clear();
    this.baseUrl = baseUrl;
    this.videoId = videoId;
    this.fps = fps;
  }

  /** Check cache for exact time match (± threshold) */
  get(time: number, threshold = 0.1): ImageBitmap | HTMLImageElement | null {
    // Exact match first
    const exact = this.cache.get(time);
    if (exact) {
      this.touch(time);
      return exact.img;
    }
    // Fuzzy match within threshold
    for (const [t, frame] of this.cache) {
      if (Math.abs(t - time) < threshold) {
        this.touch(t);
        return frame.img;
      }
    }
    return null;
  }

  /** Store a frame in cache */
  set(time: number, img: ImageBitmap | HTMLImageElement) {
    // LRU eviction
    while (this.cache.size >= MAX_FRAMES) {
      const oldest = this.accessOrder.shift();
      if (oldest !== undefined) {
        const frame = this.cache.get(oldest);
        if (frame?.img && 'close' in frame.img) (frame.img as ImageBitmap).close();
        this.cache.delete(oldest);
      }
    }
    // Remove old entry at same time
    const old = this.cache.get(time);
    if (old?.img && 'close' in old.img) (old.img as ImageBitmap).close();

    this.cache.set(time, { img, time });
    this.touch(time);
  }

  /** Preload window around current time */
  async preload(centerTime: number, durationSec: number) {
    if (!this.videoId) return;
    const step = 1 / this.fps;
    const windowSec = (PRELOAD_WINDOW / this.fps);
    const start = Math.max(0, centerTime - windowSec);
    const end = Math.min(durationSec, centerTime + windowSec);

    const toLoad: number[] = [];
    for (let t = start; t <= end; t += step) {
      const key = Math.round(t * 1000) / 1000;  // round to ms
      if (!this.cache.has(key) && !this.pending.has(key)) {
        toLoad.push(key);
      }
    }

    // Load in parallel (batched by 4)
    for (let i = 0; i < toLoad.length; i += 4) {
      const batch = toLoad.slice(i, i + 4);
      await Promise.allSettled(batch.map(t => this.loadFrame(t)));
    }
  }

  private async loadFrame(time: number) {
    if (this.pending.has(time)) return;
    this.pending.add(time);
    try {
      const url = `${this.baseUrl}/upload/video/${this.videoId}/thumbnail?time=${time.toFixed(2)}`;
      const resp = await fetch(url);
      if (!resp.ok) return;
      const blob = await resp.blob();
      const img = await this.decodeImage(blob);
      if (img) this.set(time, img);
    } catch { /* skip */ }
    finally { this.pending.delete(time); }
  }

  private async decodeImage(blob: Blob): Promise<ImageBitmap | HTMLImageElement | null> {
    // Prefer ImageBitmap for GPU texture
    try {
      return await createImageBitmap(blob);
    } catch {
      // Fallback to HTMLImageElement
      return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => resolve(null);
        img.src = URL.createObjectURL(blob);
      });
    }
  }

  private touch(time: number) {
    const idx = this.accessOrder.indexOf(time);
    if (idx >= 0) this.accessOrder.splice(idx, 1);
    this.accessOrder.push(time);
  }

  clear() {
    for (const frame of this.cache.values()) {
      if (frame.img && 'close' in frame.img) (frame.img as ImageBitmap).close();
    }
    this.cache.clear();
    this.accessOrder = [];
    this.pending.clear();
  }

  get size() { return this.cache.size; }
  get isConfigured() { return !!this.videoId; }
}

/** Singleton */
export const frameCache = new FrameCache();
