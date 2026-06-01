"""Analysis router: SSE streaming + polling for video analysis pipeline."""

import asyncio
import json
import os
import time
import queue
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse

from backend.models.script import AnalysisResponse, MigratableScript
from backend.pipeline import Pipeline
from backend.store import JobStore

router = APIRouter(prefix="/analyze", tags=["analysis"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "instances")
BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")

_jobs = JobStore("analysis", base_dir=BASE_DIR)

# Per-video_id SSE queues — keyed by video_id, removed after analysis completes
_streams: dict[str, queue.Queue] = {}


def _find_video(video_id: str) -> str:
    if not os.path.exists(UPLOAD_DIR):
        raise HTTPException(status_code=404, detail="No uploads directory")
    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(video_id):
            return os.path.join(UPLOAD_DIR, filename)
    raise HTTPException(status_code=404, detail=f"Video {video_id} not found")


def _push_event(video_id: str, event: dict) -> None:
    """Push an SSE event to the stream queue (thread-safe via queue.Queue)."""
    q = _streams.get(video_id)
    if q is None:
        return
    q.put(event)


def _run_analysis_streaming(video_id: str, video_path: str) -> None:
    """Run pipeline in a background thread, push events to SSE queue."""
    import logging
    _log = logging.getLogger(__name__)
    print(f"[SSE] Analysis thread started for {video_id}", flush=True)
    t0 = time.time()
    try:
        pipeline = Pipeline(
            work_dir=os.path.dirname(video_path),
            on_progress=lambda tag, msg: _push_event(video_id, {"type": "progress", "tag": tag, "msg": msg}),
        )
        result = pipeline.analyze_video(video_path)
        print(f"[SSE] Pipeline done for {video_id}, modules: {len(result.get('module_tree',[]))}", flush=True)
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
        _jobs[video_id] = {"status": "completed", "script": script}
        _push_event(video_id, {"type": "done", "total": len(module_tree), "elapsed": elapsed})

    except Exception as e:
        _jobs[video_id] = {"status": "failed", "error": str(e)}
        _push_event(video_id, {"type": "error", "message": str(e)})
    finally:
        # Keep queue alive briefly so the final event can be read, then clean up
        pass


# ── REST endpoints (keep existing) ──

@router.post("/{video_id}", response_model=AnalysisResponse)
async def analyze_video(
    video_id: str, background_tasks: BackgroundTasks
) -> AnalysisResponse:
    existing = _jobs.get(video_id)
    if existing and existing.get("status") == "processing":
        raise HTTPException(status_code=409, detail="Analysis already in progress")

    video_path = _find_video(video_id)
    _jobs[video_id] = {"status": "processing"}

    # Create thread-safe queue for SSE events
    _streams[video_id] = queue.Queue()

    # Run analysis in separate thread so it doesn't block the event loop
    import concurrent.futures
    _executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    _executor.submit(_run_analysis_streaming, video_id, video_path)

    return AnalysisResponse(video_id=video_id, status="processing")


@router.get("/{video_id}", response_model=AnalysisResponse)
async def get_analysis_status(video_id: str) -> AnalysisResponse:
    job = _jobs.get(video_id)
    if not job:
        raise HTTPException(status_code=404, detail="No analysis job found")
    status = job.get("status", "unknown")
    script_dict = job.get("script")
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
        job = _jobs.get(video_id)
        if job and job.get("status") == "completed":
            script_dict = job.get("script", {})
            modules = script_dict.get("modules", [])

            async def replay():
                for i, mod in enumerate(modules):
                    yield f"data: {json.dumps({'type': 'segment', 'index': i, 'module': mod})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'total': len(modules), 'elapsed': 0})}\n\n"
            return StreamingResponse(replay(), media_type="text/event-stream")

        raise HTTPException(status_code=404, detail="No active analysis stream")

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
