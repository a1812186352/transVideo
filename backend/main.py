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
from pathlib import Path
from typing import Dict, List

# Ensure project root is on sys.path so that `understanding`, `script`,
# `generation`, and `processing` packages are importable.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import upload, analysis, export, config, materials
from backend.middleware.error_handler import register_error_handlers

_log = logging.getLogger(__name__)

app = FastAPI(
    title="transVideo API",
    description="Video structure analysis, migratable script, and generation API",
    version="0.1.0",
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
app.include_router(config.router)
app.include_router(materials.router)

# ── Error handlers (after routers so app-level handlers take precedence) ──
register_error_handlers(app)


# ═══════════════════════════════════════════════════════════════════
#  Startup: stale-task recovery
# ═══════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def _recover_stale_tasks() -> None:
    """Scan job stores for tasks left in a non-terminal state after
    an ungraceful shutdown.

    - **Analysis jobs**: kept as-is — they can be resumed via the
      checkpoint system when the client re-triggers or calls
      ``GET /recovery/status`` + ``POST /recovery/analyze/{video_id}``.
    - **Export / render jobs**: marked ``failed`` because the render
      pipeline has no checkpoint mechanism.
    """
    from backend.store import JobStore

    base = str(_project_root)

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
    from backend.store import JobStore

    base = str(_project_root)
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
    from backend.store import JobStore
    from understanding.pipeline_orchestrator import Pipeline

    base = str(_project_root)
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
