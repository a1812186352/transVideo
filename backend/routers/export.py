"""Export router: receives edited script JSON and triggers video generation."""

import os
from fastapi import APIRouter, HTTPException, BackgroundTasks

from backend.models.script import ExportResponse, MigratableScript
from backend.store import JobStore

router = APIRouter(prefix="/export", tags=["export"])

# Output directory
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")
BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")

# File-persisted job status (survives process restarts)
_export_jobs = JobStore("export", base_dir=BASE_DIR)


async def _run_export(video_id: str, script: MigratableScript) -> None:
    """Background task: render the script to MP4."""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, f"{video_id}_output.mp4")

        from generation.renderer import HyperFramesRenderer
        renderer = HyperFramesRenderer(work_dir=OUTPUT_DIR)
        # script may arrive as dict (background task serialization) or Pydantic model
        script_data = script if isinstance(script, dict) else script.model_dump()
        result_path = renderer.render(
            script_json=script_data,
            output_path=output_path,
        )

        _export_jobs[video_id] = {
            "status": "completed",
            "output_path": result_path,
        }
    except Exception as e:
        _export_jobs[video_id] = {
            "status": "failed",
            "error": str(e),
        }


@router.post("/{video_id}", response_model=ExportResponse)
async def export_video(
    video_id: str,
    script: MigratableScript,
    background_tasks: BackgroundTasks,
) -> ExportResponse:
    """Export a video using the provided MigratableScript.

    Accepts the user-edited script JSON and triggers the rendering
    pipeline. Export runs asynchronously.

    Args:
        video_id: The ID returned from the upload endpoint.
        script: Complete MigratableScript with user edits applied.

    Returns:
        ExportResponse with queued status.

    Raises:
        HTTPException 409: If export is already in progress.
    """
    existing = _export_jobs.get(video_id)
    if existing and existing.get("status") in ("queued", "processing"):
        raise HTTPException(status_code=409, detail="Export already in progress")

    _export_jobs[video_id] = {"status": "queued"}
    background_tasks.add_task(_run_export, video_id, script)

    return ExportResponse(video_id=video_id, status="queued")


@router.get("/{video_id}", response_model=ExportResponse)
async def get_export_status(video_id: str) -> ExportResponse:
    """Get the status of an export job.

    Args:
        video_id: The ID returned from the upload endpoint.

    Returns:
        ExportResponse with current status and output path if completed.
    """
    job = _export_jobs.get(video_id)
    if not job:
        raise HTTPException(status_code=404, detail="No export job found")

    return ExportResponse(
        video_id=video_id,
        status=job.get("status", "unknown"),
        output_path=job.get("output_path"),
        error=job.get("error"),
    )
