"""Job recovery after process restart.

Extracted from ``pipeline_orchestrator.py`` to reduce file size.
Provides standalone ``recover_job`` and ``recover_stale`` functions.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def recover_job(
    video_id: str,
    work_dir: str = "",
    video_type: str = "vlog",
) -> Dict[str, Any]:
    """Resume a job after process restart.

    Loads the job record from the JobStore, resolves the input
    video path, and re-runs ``Pipeline.analyze_video`` — the checkpoint
    system automatically skips already-completed stages.

    Args:
        video_id: Job identifier.
        work_dir: Working directory (default: data dir).
        video_type: Video type preset key.

    Returns:
        The assembled result dict.

    Raises:
        ValueError: If the job record or input file is missing.
    """
    from backend.store import JobStore  # noqa: E402
    from understanding.pipeline_orchestrator import Pipeline  # noqa: E402

    store = JobStore("analysis", base_dir=work_dir)
    job = store.get(video_id)
    if job is None:
        raise ValueError(f"Job {video_id} not found in store")

    input_path = job.get("input_path", "")
    if not input_path or not os.path.exists(input_path):
        raise ValueError(f"Input file for job {video_id} not found: {input_path}")

    pipeline = Pipeline(work_dir=os.path.dirname(input_path))
    return pipeline.analyze_video(input_path, video_id=video_id, video_type=video_type)


def recover_stale(work_dir: str = "") -> List[Dict[str, Any]]:
    """List stale jobs (pending/processing/queued) from the analysis store.

    Returns job dicts that may need attention after a process restart.
    """
    from backend.store import JobStore  # noqa: E402

    store = JobStore("analysis", base_dir=work_dir)
    return store.list_stale()
