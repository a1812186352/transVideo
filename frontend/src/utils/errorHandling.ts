/**
 * 统一错误处理 — 后端 error code → 用户中文提示 映射表。
 *
 * 用法:
 *   import { showErrorToast, isRetryable, getErrorMessage } from '@/utils/errorHandling';
 *
 *   try { ... } catch (err) {
 *     showErrorToast(err);
 *     if (isRetryable(err)) { retry(); }
 *   }
 */

// ═══════════════════════════════════════════════════════════════════
//  错误码 → 中文提示映射表
// ═══════════════════════════════════════════════════════════════════

const ERROR_MESSAGES: Record<string, string> = {
  // ── Upload errors ──
  UPLOAD_ERROR: '文件上传失败，请检查网络后重试',
  UPLOAD_TOO_LARGE: '文件过大，请选择 2 GB 以内的视频文件',
  UPLOAD_INVALID_TYPE: '不支持的视频格式，请上传 MP4 / MOV / AVI 等格式',
  UPLOAD_INTERRUPTED: '上传被中断，请重新上传',

  // ── Analysis errors ──
  ANALYSIS_ERROR: '视频分析失败，系统将从断点恢复，请稍后重试',
  ANALYSIS_TIMEOUT: '分析超时，系统将自动重试',
  ANALYSIS_UNAVAILABLE: '分析服务暂时繁忙，请 1 分钟后重试',

  // ── Render errors ──
  RENDER_ERROR: '视频渲染失败，请重试',
  RENDER_TIMEOUT: '渲染超时，系统将自动重试',

  // ── Validation errors ──
  VALIDATION_ERROR: '请求参数有误，请检查后重试',
  BAD_REQUEST: '请求格式有误',

  // ── General ──
  NOT_FOUND: '请求的资源不存在',
  CONFLICT: '操作冲突，请等待当前任务完成',
  UNAUTHORIZED: '未授权，请刷新页面',
  FORBIDDEN: '无权限访问',
  TOO_MANY_REQUESTS: '请求过于频繁，请稍后再试',
  INTERNAL_ERROR: '服务器内部错误，请稍后重试',
  SERVICE_UNAVAILABLE: '服务暂时不可用，请稍后重试',
  PAYLOAD_TOO_LARGE: '请求体过大',

  // ── Network errors ──
  NETWORK_ERROR: '网络连接失败，请检查网络设置',
  TIMEOUT: '请求超时，请检查网络后重试',
  UNKNOWN: '发生未知错误，请刷新页面后重试',
};

// ═══════════════════════════════════════════════════════════════════
//  可重试的错误码
// ═══════════════════════════════════════════════════════════════════

const RETRYABLE_CODES = new Set([
  'ANALYSIS_ERROR',
  'ANALYSIS_TIMEOUT',
  'ANALYSIS_UNAVAILABLE',
  'RENDER_ERROR',
  'RENDER_TIMEOUT',
  'SERVICE_UNAVAILABLE',
  'TOO_MANY_REQUESTS',
  'INTERNAL_ERROR',
  'NETWORK_ERROR',
  'TIMEOUT',
]);

// ═══════════════════════════════════════════════════════════════════
//  后端错误响应类型
// ═══════════════════════════════════════════════════════════════════

export interface BackendError {
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    recoverable: boolean;
  };
}

export interface AppError {
  code: string;
  message: string;
  userMessage: string;
  recoverable: boolean;
  details?: Record<string, unknown>;
  original?: unknown;
}

// ═══════════════════════════════════════════════════════════════════
//  公共 API
// ═══════════════════════════════════════════════════════════════════

/**
 * 从任意错误对象中提取统一 AppError。
 *
 * 支持:
 *   - 后端标准响应 { error: { code, message, recoverable } }
 *   - fetch TypeError (网络中断)
 *   - DOMException (AbortError / timeout)
 *   - 普通 Error / string
 */
export function parseError(err: unknown): AppError {
  // ── 后端标准响应 ──
  if (isBackendError(err)) {
    const be = (err as { error: BackendError['error'] }).error!;
    const code = be.code || 'UNKNOWN';
    return {
      code,
      message: be.message || '',
      userMessage: ERROR_MESSAGES[code] || be.message || ERROR_MESSAGES.UNKNOWN,
      recoverable: be.recoverable || RETRYABLE_CODES.has(code),
      details: be.details,
      original: err,
    };
  }

  // ── TypeError: Failed to fetch → 网络错误 ──
  if (err instanceof TypeError && err.message === 'Failed to fetch') {
    return {
      code: 'NETWORK_ERROR',
      message: err.message,
      userMessage: ERROR_MESSAGES.NETWORK_ERROR,
      recoverable: true,
      original: err,
    };
  }

  // ── DOMException: AbortError → 超时 ──
  if (err instanceof DOMException && err.name === 'AbortError') {
    return {
      code: 'TIMEOUT',
      message: 'Request timed out',
      userMessage: ERROR_MESSAGES.TIMEOUT,
      recoverable: true,
      original: err,
    };
  }

  // ── 其他 TypeError (网络相关) ──
  if (err instanceof TypeError) {
    return {
      code: 'NETWORK_ERROR',
      message: err.message,
      userMessage: ERROR_MESSAGES.NETWORK_ERROR,
      recoverable: true,
      original: err,
    };
  }

  // ── 普通 Error ──
  if (err instanceof Error) {
    return {
      code: 'UNKNOWN',
      message: err.message,
      userMessage: ERROR_MESSAGES.UNKNOWN,
      recoverable: false,
      original: err,
    };
  }

  // ── 兜底 ──
  return {
    code: 'UNKNOWN',
    message: String(err),
    userMessage: ERROR_MESSAGES.UNKNOWN,
    recoverable: false,
    original: err,
  };
}

/**
 * 显示错误 toast。
 *
 * 如果环境中有 UI 组件库则调用其 toast，否则回退到 console.error。
 * 在你的项目中可以替换为 antd / element-plus / naive-ui 的 toast。
 */
export function showErrorToast(err: unknown): void {
  const parsed = parseError(err);

  // ── 尝试使用项目已有的 toast 机制 ──
  const win = globalThis as Record<string, unknown>;

  if (typeof win.showToast === 'function') {
    (win.showToast as (msg: string, type: string) => void)(parsed.userMessage, 'error');
    return;
  }

  // ── Element Plus Message ──
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const vueApp = (win as any).__vue_app__;
    const msgApi = vueApp?.config?.globalProperties?.$message;
    if (msgApi?.error) {
      msgApi.error(parsed.userMessage);
      return;
    }
  } catch { /* not available */ }

  // ── Fallback: console ──
  console.error(`[${parsed.code}] ${parsed.userMessage}`, parsed.message);
}

/**
 * 判断错误是否可重试。
 */
export function isRetryable(err: unknown): boolean {
  return parseError(err).recoverable;
}

/**
 * 获取用户可读的中文错误提示。
 */
export function getErrorMessage(err: unknown): string {
  return parseError(err).userMessage;
}

/**
 * 获取后端错误码。
 */
export function getErrorCode(err: unknown): string {
  return parseError(err).code;
}

// ═══════════════════════════════════════════════════════════════════
//  辅助
// ═══════════════════════════════════════════════════════════════════

function isBackendError(err: unknown): err is BackendError {
  if (!err || typeof err !== 'object') return false;
  const be = err as BackendError;
  return !!(be.error && typeof be.error.code === 'string');
}
