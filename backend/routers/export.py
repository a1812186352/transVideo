"""Export router: receives edited script JSON and triggers video generation.

Provides REST + SSE endpoints for render job lifecycle:
  - POST   /api/export/{video_id}    — submit render job
  - GET    /api/export/{video_id}    — poll job status
  - GET    /api/export/{video_id}/progress — SSE real-time progress
  - POST   /api/export/{video_id}/cancel   — cancel running job
  - GET    /api/export/output/{filename}   — serve rendered file
"""

import asyncio
import json
import logging
import os
import shutil
import time
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, StreamingResponse

from backend.models.script import ExportResponse, MigratableScript
from backend.store import JobStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])

# ── Paths ──

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")
BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")

# ── Persisted job store (SQLite-backed, survives restarts) ──

_export_jobs = JobStore("export", base_dir=BASE_DIR)

# ── In-memory cancel flags (cleared on job completion) ──

_cancel_flags: Dict[str, bool] = {}

# ── SSE stream queues ──

_progress_queues: Dict[str, asyncio.Queue] = {}
_MAX_PROGRESS_QUEUE_SIZE = 128


# ═══════════════════════════════════════════════════════════════════
#  Background render task
# ═══════════════════════════════════════════════════════════════════

async def _run_export(video_id: str, script: MigratableScript) -> None:
    """Background task: render the script to MP4 via CompositeEngine."""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, f"{video_id}_output.mp4")

        script_data = script if isinstance(script, dict) else script.model_dump()
        metadata = script_data.get("metadata", {})
        total_duration = metadata.get("total_duration", 0.0)

        # ── Check disk space (need at least 500 MB free) ──
        try:
            usage = shutil.disk_usage(OUTPUT_DIR)
            if usage.free < 500 * 1024 * 1024:
                raise RuntimeError(
                    f"Insufficient disk space: {usage.free // 1024 // 1024} MB free, "
                    f"at least 500 MB required"
                )
        except OSError:
            pass  # disk_usage not available on all platforms

        # ── Estimate ETA from total_duration ──
        eta = max(int(total_duration * 2.5), 120)  # rough: 2.5x realtime

        _export_jobs.set_status(video_id, "processing")
        _export_jobs.update_progress(video_id, 0.0)
        _push_progress(video_id, 0, "初始化渲染引擎", eta)

        from generation import get_engine

        engine = get_engine(
            "composite",
            work_dir=OUTPUT_DIR,
            fps=metadata.get("fps", 30),
            crf=23,
        )

        def _progress(pct: int, stage: str, eta_sec: int) -> None:
            _export_jobs.update_progress(video_id, pct / 100.0)
            _push_progress(video_id, pct, stage, eta_sec if eta_sec else eta)
            # Check cancel flag at each progress tick
            if _cancel_flags.get(video_id, False):
                raise RuntimeError("Canceled by user")

        # ── Render ──
        result_path = await engine.render(
            script_json=script_data,
            output_path=output_path,
            progress_callback=_progress,
            timeout=1800,  # 30 min default
        )

        filename = os.path.basename(result_path)
        _export_jobs.set_result(video_id, {
            "output_path": f"export/output/{filename}",
            "filename": filename,
        })
        _push_progress(video_id, 100, "渲染完成", 0)
        logger.info("Export %s completed → %s", video_id, filename)

    except RuntimeError as e:
        err = str(e)
        # Distinguish cancellation from other errors
        if _cancel_flags.pop(video_id, False):
            _export_jobs.set_status(video_id, "canceled")
            _push_progress(video_id, 0, "已取消", 0)
            logger.info("Export %s canceled by user", video_id)
        else:
            _export_jobs.set_error(video_id, err)
            _push_progress(video_id, 0, f"失败: {err}", 0)
            logger.error("Export %s failed: %s", video_id, err)
    except Exception as e:
        err = str(e)
        _export_jobs.set_error(video_id, err)
        _push_progress(video_id, 0, f"异常: {err}", 0)
        logger.exception("Export %s crashed", video_id)
    finally:
        # Clean up SSE queue
        _progress_queues.pop(video_id, None)
        _cancel_flags.pop(video_id, None)

        # Clean up legacy HTML artifacts from HyperFramesEngine
        html_pattern = f"_render_*.html"
        try:
            for f in os.listdir(OUTPUT_DIR):
                if f.startswith("_render_") and f.endswith(".html"):
                    os.remove(os.path.join(OUTPUT_DIR, f))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
#  REST endpoints
# ═══════════════════════════════════════════════════════════════════

@router.post("/{video_id}", response_model=ExportResponse)
async def export_video(
    video_id: str,
    script: MigratableScript,
    background_tasks: BackgroundTasks,
) -> ExportResponse:
    """Submit a render job.

    Accepts the user-edited script JSON and starts rendering via
    CompositeEngine.  Rendering runs in a background task.
    """
    existing = _export_jobs.get(video_id)
    if existing and existing.get("status") in ("queued", "processing"):
        raise HTTPException(status_code=409, detail="Export already in progress")

    _export_jobs.create_job(
        job_id=video_id,
        type="export",
        input_path="",
        status="queued",
    )
    _cancel_flags[video_id] = False
    background_tasks.add_task(_run_export, video_id, script)

    return ExportResponse(video_id=video_id, status="queued")


@router.get("/{video_id}", response_model=ExportResponse)
async def get_export_status(video_id: str) -> ExportResponse:
    """Poll the status of an export job."""
    job = _export_jobs.get(video_id)
    if not job:
        raise HTTPException(status_code=404, detail="No export job found")

    return ExportResponse(
        video_id=video_id,
        status=job.get("status", "unknown"),
        output_path=job.get("output_path"),
        error=job.get("error"),
    )


@router.get("/output/{filename}")
async def get_output_file(filename: str):
    """Serve a rendered output video file (path-traversal safe)."""
    resolved = os.path.normpath(os.path.join(OUTPUT_DIR, filename))
    output_dir_norm = os.path.normpath(OUTPUT_DIR)

    if not str(resolved).startswith(output_dir_norm):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.isfile(resolved):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(resolved, media_type="video/mp4")


# ═══════════════════════════════════════════════════════════════════
#  SSE progress stream
# ═══════════════════════════════════════════════════════════════════

@router.get("/{video_id}/progress")
async def stream_progress(video_id: str, request: Request):
    """SSE endpoint: pushes render progress every ~5% change.

    Events:
      ``{"progress": 23, "stage": "提取视频段并裁剪", "eta": 180}``
    """
    q: asyncio.Queue = _progress_queues.get(video_id)
    if q is None:
        q = asyncio.Queue(maxsize=_MAX_PROGRESS_QUEUE_SIZE)
        _progress_queues[video_id] = q

    async def _event_stream():
        last_pct = -1
        while True:
            if await request.is_disconnected():
                break
            try:
                pct, stage, eta = await asyncio.wait_for(q.get(), timeout=15.0)
            except asyncio.TimeoutError:
                # Heartbeat
                yield ": heartbeat\n\n"
                continue

            # Throttle: only push when progress changes by ≥5%
            if abs(pct - last_pct) >= 5 or pct == 100 or pct == 0:
                last_pct = pct
                data = json.dumps({"progress": pct, "stage": stage, "eta": eta})
                yield f"data: {data}\n\n"

            # Signal completion
            if pct == 100:
                yield "data: {\"progress\":100,\"stage\":\"完成\",\"eta\":0}\n\n"
                break

        _progress_queues.pop(video_id, None)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _push_progress(video_id: str, pct: int, stage: str, eta: int) -> None:
    """Push a progress update to the SSE queue (non-blocking)."""
    q = _progress_queues.get(video_id)
    if q is None:
        return
    try:
        q.put_nowait((pct, stage, eta))
    except asyncio.QueueFull:
        pass  # drop update if queue is full


# ═══════════════════════════════════════════════════════════════════
#  Cancel
# ═══════════════════════════════════════════════════════════════════

@router.post("/{video_id}/cancel", response_model=ExportResponse)
async def cancel_export(video_id: str) -> ExportResponse:
    """Cancel a running export job.

    Sets a cancel flag that the render task checks on each progress
    tick.  The task will exit at the next opportunity (typically
    within 2-5 seconds).
    """
    job = _export_jobs.get(video_id)
    if not job:
        raise HTTPException(status_code=404, detail="No export job found")

    status = job.get("status", "")
    if status not in ("queued", "processing"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel job in status '{status}'",
        )

    _cancel_flags[video_id] = True
    _push_progress(video_id, 0, "取消中…", 0)

    return ExportResponse(video_id=video_id, status="canceled")
