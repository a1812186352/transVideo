"""FastAPI application entry point for transVideo backend.

Mounts upload, analysis, and export routers with CORS enabled for
the frontend development server.

On startup, scans the SQLite job stores for stale tasks left over
from a previous ungraceful shutdown.  Analysis jobs are kept as-is
(they can be resumed via checkpoint); export jobs are marked failed
(since rendering cannot checkpoint-resume).
"""

import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

# Ensure project root is on sys.path so that `understanding`, `script`,
# `generation`, and `processing` packages are importable.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.log_config import setup_logging
from backend.routers import upload, analysis, export, materials
from backend.middleware.error_handler import register_error_handlers
from backend.middleware.auth import install_auth_middleware

# Initialize logging (console + rotating file handler)
_log_path = setup_logging()

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
#  sys.excepthook — crash dump to logs/crash_dumps/
# ═══════════════════════════════════════════════════════════════════

_CRASH_DIR = os.path.join(_project_root, "logs", "crash_dumps")


def _install_crash_hook() -> None:
    """Install a global exception hook that saves a crash dump.

    When an unhandled exception escapes the event loop, this hook:
    1. Writes the full Python stack trace to ``logs/crash_dumps/``
       with a timestamped filename.
    2. Logs the error at CRITICAL level with structured context.
    3. Attempts to dump memory stats (largest objects) if ``objgraph``
       is installed.
    """
    os.makedirs(_CRASH_DIR, exist_ok=True)

    def _crash_hook(exc_type, exc_value, exc_tb):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dump_path = os.path.join(_CRASH_DIR, f"crash_{timestamp}.txt")

        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(f"Crash time   : {timestamp}\n")
            f.write(f"Exception    : {exc_type.__name__}\n")
            f.write(f"Value        : {exc_value}\n")
            f.write(f"{'='*60}\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)

            # Attempt objgraph memory snapshot
            try:
                import objgraph
                f.write(f"\n{'='*60}\nTop 20 objects by count:\n")
                objgraph.show_most_common_types(limit=20, file=f)
            except ImportError:
                f.write("\n(objgraph not installed — skip memory snapshot)\n")

            # GC stats
            try:
                import gc
                f.write(f"\nGC tracked objects: {len(gc.get_objects())}\n")
            except Exception:
                pass

        _log.critical(
            "UNHANDLED EXCEPTION — crash dump saved to %s",
            dump_path,
            extra={"structured_fields": {
                "crash_dump": dump_path,
                "exception": exc_type.__name__,
            }},
        )

    sys.excepthook = _crash_hook


_install_crash_hook()


# ═══════════════════════════════════════════════════════════════════
#  Prometheus /metrics endpoint (lightweight, no external dependency)
# ═══════════════════════════════════════════════════════════════════

_METRICS: Dict[str, object] = {
    "app_start_time": time.time(),
    "analysis_starts": 0,
    "analysis_failures": 0,
    "analysis_elapsed_ms": [],     # rolling window for P50/P95/P99
    "ocr_frames_total": 0,
    "ocr_skipped_blurry": 0,
    "export_starts": 0,
    "export_failures": 0,
    "concurrent_analysis_max": 1,
}

_LATENCY_BUCKETS = [10_000, 30_000, 60_000, 120_000, 300_000, 600_000, 1_800_000]


def _percentile(sorted_data: List[float], pct: float) -> float:
    """Compute P* percentile from sorted list."""
    if not sorted_data:
        return 0.0
    n = len(sorted_data)
    idx = max(0, min(n - 1, int(n * pct / 100)))
    return sorted_data[idx]


def _build_metrics_text() -> str:
    """Return Prometheus exposition-format metrics."""
    lines: List[str] = []
    app_start = _METRICS.get("app_start_time", time.time())
    lines.append(f"# HELP transvideo_app_start_time Unix epoch of app start")
    lines.append(f"# TYPE transvideo_app_start_time gauge")
    lines.append(f"transvideo_app_start_time {app_start:.0f}")

    lines.append(f"# HELP transvideo_analysis_starts_total Total analysis jobs started")
    lines.append(f"# TYPE transvideo_analysis_starts_total counter")
    lines.append(f"transvideo_analysis_starts_total {_METRICS.get('analysis_starts', 0)}")

    lines.append(f"# HELP transvideo_analysis_failures_total Total analysis failures")
    lines.append(f"# TYPE transvideo_analysis_failures_total counter")
    lines.append(f"transvideo_analysis_failures_total {_METRICS.get('analysis_failures', 0)}")

    # Latency percentiles
    elapsed = _METRICS.get("analysis_elapsed_ms", [])
    if elapsed:
        sorted_elapsed = sorted(elapsed)
        p50 = _percentile(sorted_elapsed, 50)
        p95 = _percentile(sorted_elapsed, 95)
        p99 = _percentile(sorted_elapsed, 99)
    else:
        p50 = p95 = p99 = 0.0

    lines.append(f"# HELP transvideo_analysis_duration_seconds Analysis duration percentiles")
    lines.append(f"# TYPE transvideo_analysis_duration_seconds gauge")
    lines.append(f'transvideo_analysis_duration_seconds{{quantile="0.5"}} {p50 / 1000:.3f}')
    lines.append(f'transvideo_analysis_duration_seconds{{quantile="0.95"}} {p95 / 1000:.3f}')
    lines.append(f'transvideo_analysis_duration_seconds{{quantile="0.99"}} {p99 / 1000:.3f}')

    lines.append(f"# HELP transvideo_ocr_frames_total Frames submitted to OCR")
    lines.append(f"# TYPE transvideo_ocr_frames_total counter")
    lines.append(f"transvideo_ocr_frames_total {_METRICS.get('ocr_frames_total', 0)}")

    lines.append(f"# HELP transvideo_ocr_skipped_blurry_total Blurry frames skipped by OCR pre-filter")
    lines.append(f"# TYPE transvideo_ocr_skipped_blurry_total counter")
    lines.append(f"transvideo_ocr_skipped_blurry_total {_METRICS.get('ocr_skipped_blurry', 0)}")

    lines.append(f"# HELP transvideo_export_starts_total Export jobs started")
    lines.append(f"# TYPE transvideo_export_starts_total counter")
    lines.append(f"transvideo_export_starts_total {_METRICS.get('export_starts', 0)}")

    lines.append(f"# HELP transvideo_export_failures_total Export failures")
    lines.append(f"# TYPE transvideo_export_failures_total counter")
    lines.append(f"transvideo_export_failures_total {_METRICS.get('export_failures', 0)}")

    # Queue depth (from analysis router)
    try:
        from backend.routers.analysis import _analysis_semaphore
        q_depth = 0 if _analysis_semaphore.acquire(blocking=False) else 1
        if not q_depth:
            _analysis_semaphore.release()
    except Exception:
        q_depth = -1
    lines.append(f"# HELP transvideo_analysis_queue_depth Current analysis queue depth")
    lines.append(f"# TYPE transvideo_analysis_queue_depth gauge")
    lines.append(f"transvideo_analysis_queue_depth {q_depth}")

    return "\n".join(lines) + "\n"


app = FastAPI(
    title="transVideo API",
    description="""Video structure analysis, migratable script, and generation API.

## 核心工作流
1. **上传** `POST /upload/` — 上传视频文件（魔数校验 + MIME + 扩展名三级检查）
2. **分析** `POST /analyze/{video_id}` — 启动分析管线（帧差异 → 场景检测 → ASR → 音频分析 → OCR → 结构推断 → 模块树）
3. **导出** `POST /export/{video_id}` — 导出为 MP4（CompositeEngine 自动降级 HyperFrames → FFmpeg）

## 可观测性
- `GET /health` — 健康检查
- `GET /metrics` — Prometheus 指标（耗时 P50/P95/P99、失败率、队列深度）
- `GET /recovery/status` — 陈旧任务恢复状态

## 认证
设置 `TRANVIDEO_API_KEY` 环境变量启用 API Key 鉴权。
""",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(upload.router)
app.include_router(analysis.router)
app.include_router(export.router)

app.include_router(materials.router)

# ── Optional API Key authentication (enabled via TRANVIDEO_API_KEY env) ──
install_auth_middleware(app)

# ── Error handlers (after routers so app-level handlers take precedence) ──
register_error_handlers(app)


# ═══════════════════════════════════════════════════════════════════
#  Startup: stale-task recovery
# ═══════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def _recover_stale_tasks() -> None:
    """Ensure data directory exists, then scan for stale tasks."""
    from backend.store.job_store import get_data_dir, JobStore

    # ── Ensure data directory ──
    data_dir = get_data_dir()
    _log.info("Data directory: %s", data_dir)
    os.makedirs(os.path.join(data_dir, "job_store"), exist_ok=True)

    # ── Base directory ──
    base = get_data_dir()

    # ── Analysis namespace ──
    analysis_store = JobStore("analysis", base_dir=base)
    analysis_stale = analysis_store.list_stale()
    if analysis_stale:
        _log.warning(
            "Found %d stale analysis job(s) — they can be resumed via "
            "checkpoint. Use POST /recovery/analyze/{video_id} to recover.",
            len(analysis_stale),
        )
        for j in analysis_stale:
            age = j.get("stale_age_seconds", -1)
            _log.info(
                "  stale analysis job %s (status=%s, age=%.0fs, input=%s)",
                j["id"], j.get("status"), age, j.get("input_path", "?"),
            )
    else:
        _log.info("Analysis store: no stale jobs.")
    analysis_store.close()

    # ── Export namespace (cannot resume — mark as failed) ──
    export_store = JobStore("export", base_dir=base)
    export_stale = export_store.list_stale()
    if export_stale:
        n = export_store.reset_stale_to_failed()
        _log.warning(
            "Found %d stale export job(s) → marked as failed "
            "(rendering cannot resume mid-stream).",
            n,
        )
        for j in export_stale:
            age = j.get("stale_age_seconds", -1)
            _log.info("  stale export job %s (age=%.0fs) → failed", j["id"], age)
    else:
        _log.info("Export store: no stale jobs.")
    export_store.close()

    _log.info("Startup recovery scan complete.")


# ═══════════════════════════════════════════════════════════════════
#  Recovery endpoints
# ═══════════════════════════════════════════════════════════════════

@app.get("/recovery/status")
async def recovery_status() -> Dict[str, object]:
    """Return stale-task counts and job list for each namespace.

    Use this to see which analysis jobs are available for checkpoint
    recovery after a restart.
    """
    from backend.store.job_store import get_data_dir, JobStore

    base = get_data_dir()
    result: Dict[str, object] = {}

    for ns in ("analysis", "export"):
        store = JobStore(ns, base_dir=base)
        counts = store.count_by_status()
        stale = store.list_stale()
        store.close()
        result[ns] = {
            "counts": counts,
            "stale": stale,
            "stale_count": len(stale),
            "recoverable": ns == "analysis",  # only analysis supports resume
        }

    return result


@app.post("/recovery/analyze/{video_id}")
async def recover_analysis_job(video_id: str) -> Dict[str, object]:
    """Resume a stale analysis job from the last checkpoint.

    The pipeline will skip already-completed stages and only re-run
    the remaining work.  If the job is not stale (already completed
    or failed), this is a no-op.
    """
    from backend.store.job_store import get_data_dir, JobStore
    from understanding.pipeline_orchestrator import Pipeline

    base = get_data_dir()
    store = JobStore("analysis", base_dir=base)
    job = store.get_job(video_id)

    if job is None:
        store.close()
        return {"video_id": video_id, "status": "not_found"}

    status = job.get("status", "")
    if status not in ("pending", "processing", "queued"):
        store.close()
        return {
            "video_id": video_id,
            "status": status,
            "message": f"Job is already in terminal state '{status}' — no recovery needed.",
        }

    input_path = job.get("input_path", "")
    store.close()

    if not input_path or not os.path.exists(input_path):
        return {
            "video_id": video_id,
            "status": "failed",
            "message": f"Input file not found: {input_path}. Cannot recover.",
        }

    # Re-run pipeline (checkpoint skips done stages)
    pipeline = Pipeline(work_dir=os.path.dirname(input_path))
    try:
        result = pipeline.analyze_video(input_path, video_id=video_id)
        modules = len(result.get("module_tree", []))
        return {
            "video_id": video_id,
            "status": "completed",
            "modules": modules,
        }
    except Exception as exc:
        _log.exception("Recovery failed for %s", video_id)
        return {
            "video_id": video_id,
            "status": "failed",
            "error": str(exc),
        }


@app.get("/")
async def root() -> dict:
    """Health check endpoint."""
    return {
        "service": "transVideo",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health() -> dict:
    """Detailed health check."""
    return {"status": "healthy"}


# ═══════════════════════════════════════════════════════════════════
#  Prometheus /metrics
# ═══════════════════════════════════════════════════════════════════

@app.get("/metrics")
async def metrics() -> str:
    """Prometheus exposition-format metrics endpoint.

    Returns performance metrics (latency percentiles, failure rates,
    queue depth) in Prometheus text format.  No external Prometheus
    client library required.
    """
    return _build_metrics_text()
