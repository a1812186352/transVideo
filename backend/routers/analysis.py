"""Analysis router: triggers the video analysis pipeline."""

import os
from fastapi import APIRouter, HTTPException, BackgroundTasks

from backend.models.script import AnalysisResponse, MigratableScript
from backend.pipeline import Pipeline
from backend.store import JobStore

router = APIRouter(prefix="/analyze", tags=["analysis"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "instances")
BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")

# File-persisted job status (survives process restarts)
_jobs = JobStore("analysis", base_dir=BASE_DIR)


def _find_video(video_id: str) -> str:
    """Find the uploaded video file by video_id prefix.

    Returns:
        Absolute path to the video file.

    Raises:
        HTTPException 404: If no matching file found.
    """
    if not os.path.exists(UPLOAD_DIR):
        raise HTTPException(status_code=404, detail="No uploads directory")

    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(video_id):
            return os.path.join(UPLOAD_DIR, filename)

    raise HTTPException(status_code=404, detail=f"Video {video_id} not found")


async def _run_analysis(video_id: str, video_path: str) -> None:
    """Background task: run pipeline and store result."""
    try:
        pipeline = Pipeline(work_dir=os.path.dirname(video_path))
        result = pipeline.analyze_video(video_path)

        # Build script from module tree
        from script.builder import ScriptBuilder
        builder = ScriptBuilder()
        script = builder.from_module_tree(
            modules=result.get("module_tree", []),
            title=f"Analysis of {video_id}",
            total_duration=result.get("signal_data", {}).get("total_duration", 0.0),
            fps=result.get("signal_data", {}).get("fps", 30.0),
            source_video_id=video_id,
        )

        _jobs[video_id] = {
            "status": "completed",
            "script": script,  # already a dict from ScriptBuilder
        }
    except Exception as e:
        _jobs[video_id] = {
            "status": "failed",
            "error": str(e),
        }


@router.post("/{video_id}", response_model=AnalysisResponse)
async def analyze_video(
    video_id: str, background_tasks: BackgroundTasks
) -> AnalysisResponse:
    """Trigger analysis pipeline for an uploaded video.

    The analysis runs asynchronously in the background. Poll this endpoint
    to check status until 'completed' or 'failed'.

    Args:
        video_id: The ID returned from the upload endpoint.

    Returns:
        AnalysisResponse with current status.

    Raises:
        HTTPException 404: If video not found.
        HTTPException 409: If analysis is already in progress.
    """
    existing = _jobs.get(video_id)
    if existing and existing.get("status") == "processing":
        raise HTTPException(status_code=409, detail="Analysis already in progress")

    video_path = _find_video(video_id)

    _jobs[video_id] = {"status": "processing"}
    background_tasks.add_task(_run_analysis, video_id, video_path)

    return AnalysisResponse(video_id=video_id, status="processing")


@router.get("/{video_id}", response_model=AnalysisResponse)
async def get_analysis_status(video_id: str) -> AnalysisResponse:
    """Get the status and result of an analysis job.

    Args:
        video_id: The ID returned from the upload endpoint.

    Returns:
        AnalysisResponse with current status and script if completed.
    """
    job = _jobs.get(video_id)
    if not job:
        raise HTTPException(status_code=404, detail="No analysis job found")

    status = job.get("status", "unknown")
    script_dict = job.get("script")
    script = MigratableScript(**script_dict) if script_dict else None

    return AnalysisResponse(
        video_id=video_id,
        status=status,
        script=script,
        error=job.get("error"),
    )
