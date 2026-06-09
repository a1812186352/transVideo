"""Analysis router: SSE streaming + polling for video analysis pipeline."""

import asyncio
import json
import logging
import os
import time
import queue
from typing import Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import StreamingResponse

from backend.middleware.error_handler import (
    AnalysisError,
    ConflictError,
    NotFoundError,
)
from backend.models.script import AnalysisResponse, MigratableScript
from backend.pipeline import Pipeline
from backend.store import JobStore

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze", tags=["analysis"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "instances")
BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")

_jobs = JobStore("analysis", base_dir=BASE_DIR)

# Per-video_id SSE queues — keyed by video_id, removed after analysis completes
_streams: Dict[str, queue.Queue] = {}


def _find_video(video_id: str) -> str:
    if not os.path.exists(UPLOAD_DIR):
        raise NotFoundError(message="No uploads directory")
    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(video_id):
            return os.path.join(UPLOAD_DIR, filename)
    raise NotFoundError(message=f"Video {video_id} not found")


def _push_event(video_id: str, event: dict) -> None:
    """Push an SSE event to the stream queue (thread-safe via queue.Queue)."""
    q = _streams.get(video_id)
    if q is None:
        return
    q.put(event)


def _run_analysis_streaming(video_id: str, video_path: str, video_type: str = "vlog") -> None:
    """Run pipeline in a background thread, push events to SSE queue."""
    _log.info("Analysis thread started for %s (type=%s)", video_id, video_type)
    t0 = time.time()
    try:
        pipeline = Pipeline(
            work_dir=os.path.dirname(video_path),
            on_progress=lambda tag, msg: _push_event(video_id, {"type": "progress", "tag": tag, "msg": msg}),
        )
        result = pipeline.analyze_video(video_path, video_id=video_id, video_type=video_type)
        _log.info("Pipeline done for %s, modules: %d", video_id, len(result.get("module_tree", [])))

        module_tree = result.get("module_tree", [])
        duration = result.get("signal_data", {}).get("total_duration", 0.0)
        fps = result.get("signal_data", {}).get("fps", 30.0)

        # Push each module as a segment event
        for i, mod in enumerate(module_tree):
            _push_event(video_id, {
                "type": "segment",
                "index": i,
                "module": mod,
            })

        # Build full script for job store
        from script.builder import ScriptBuilder
        builder = ScriptBuilder()
        script = builder.from_module_tree(
            modules=module_tree,
            title=f"Analysis of {video_id}",
            total_duration=duration,
            fps=fps,
            source_video_id=video_id,
        )

        elapsed = round(time.time() - t0, 2)
        # Persist result via new JobStore API
        _jobs.set_result(video_id, {"script": script if isinstance(script, dict) else script.model_dump()})
        _push_event(video_id, {"type": "done", "total": len(module_tree), "elapsed": elapsed})

    except AnalysisError:
        # Already recorded in job store by the pipeline's _fail handler;
        # just push the error event to SSE
        job = _jobs.get_job(video_id) or {}
        _push_event(video_id, {"type": "error", "message": job.get("error", "Analysis failed")})
    except Exception as e:
        _log.exception("Unexpected error in analysis thread for %s", video_id)
        _jobs.set_error(video_id, str(e))
        _push_event(video_id, {"type": "error", "message": str(e)})


# ── REST endpoints (keep existing) ──

@router.post("/{video_id}", response_model=AnalysisResponse)
async def analyze_video(
    video_id: str, background_tasks: BackgroundTasks, video_type: str = "vlog"
) -> AnalysisResponse:
    existing = _jobs.get_job(video_id)
    if existing and existing.get("status") == "processing":
        raise ConflictError(message="Analysis already in progress for this video")

    video_path = _find_video(video_id)

    # Create job record via new API
    _jobs.create_job(
        job_id=video_id,
        type="analysis",
        input_path=video_path,
        status="processing",
    )

    # Create thread-safe queue for SSE events
    _streams[video_id] = queue.Queue()

    # Run analysis in separate thread so it doesn't block the event loop
    import concurrent.futures
    _executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    _executor.submit(_run_analysis_streaming, video_id, video_path, video_type)

    return AnalysisResponse(video_id=video_id, status="processing")


@router.get("/{video_id}", response_model=AnalysisResponse)
async def get_analysis_status(video_id: str) -> AnalysisResponse:
    job = _jobs.get_job(video_id)
    if not job:
        raise NotFoundError(message=f"No analysis job found for {video_id}")

    status = job.get("status", "unknown")
    script_dict = None

    # Script is stored inside the result field
    result = job.get("result", {})
    if isinstance(result, dict):
        script_dict = result.get("script")

    script = MigratableScript(**script_dict) if script_dict else None
    return AnalysisResponse(
        video_id=video_id, status=status, script=script, error=job.get("error"),
    )


# ── SSE streaming endpoint ──

@router.get("/{video_id}/stream")
async def stream_analysis(video_id: str, request: Request):
    """SSE endpoint: pushes segment events in real-time as analysis runs."""
    q = _streams.get(video_id)
    if q is None:
        # If analysis already completed, check job store
        job = _jobs.get_job(video_id)
        if job and job.get("status") == "completed":
            result = job.get("result", {})
            script_dict = result.get("script", {}) if isinstance(result, dict) else {}
            modules = script_dict.get("modules", [])

            async def replay():
                for i, mod in enumerate(modules):
                    yield f"data: {json.dumps({'type': 'segment', 'index': i, 'module': mod})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'total': len(modules), 'elapsed': 0})}\n\n"
            return StreamingResponse(replay(), media_type="text/event-stream")

        raise NotFoundError(message="No active analysis stream")

    # queue.Queue is thread-safe — read in thread, yield in event loop
    event_queue = q  # alias for clarity

    async def stream():
        loop = asyncio.get_running_loop()
        last_hb = time.time()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Read from thread-safe queue via to_thread
                    event = await asyncio.to_thread(event_queue.get, timeout=1)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("done", "error"):
                        break
                except queue.Empty:
                    # Send heartbeat every 15s
                    if time.time() - last_hb > 15:
                        yield ": heartbeat\n\n"
                        last_hb = time.time()
        finally:
            pass  # keep queue for reconnection; analysis thread will push to it

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
