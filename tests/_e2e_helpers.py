"""E2E test helpers — standalone functions for the upload→analyze→export pipeline.

These are placed in a module with a leading underscore to avoid
conflict with a ``tests`` package that may exist in site-packages.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

_project_root = Path(__file__).resolve().parent.parent

# ── Timeout constants (overridable via env for CI) ──

ANALYSIS_TIMEOUT = float(os.environ.get("E2E_ANALYSIS_TIMEOUT", "150"))
EXPORT_TIMEOUT = float(os.environ.get("E2E_EXPORT_TIMEOUT", "300"))


# ═══════════════════════════════════════════════════════════════════
#  Upload helpers
# ═══════════════════════════════════════════════════════════════════

def upload_video(client: TestClient, video_path: str) -> dict:
    """Upload a video file and return the response JSON.

    Args:
        client: FastAPI TestClient.
        video_path: Absolute path to a video file.

    Returns:
        Upload response dict with ``video_id``, ``duration``, etc.

    Raises:
        AssertionError: If upload does not return 200.
    """
    fname = os.path.basename(video_path)
    mime = "video/quicktime" if fname.endswith(".mov") else "video/mp4"
    with open(video_path, "rb") as f:
        resp = client.post("/upload/", files={"file": (fname, f, mime)})
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()


# ═══════════════════════════════════════════════════════════════════
#  Polling helpers
# ═══════════════════════════════════════════════════════════════════

def poll_analysis(
    client: TestClient,
    video_id: str,
    timeout: float = ANALYSIS_TIMEOUT,
    interval: float = 3.0,
) -> dict:
    """Poll ``GET /analyze/{video_id}`` until completed or failed.

    Non-200 responses (e.g. 404 for a job that hasn't been created
    yet) are treated as transient and retried.

    Args:
        client: FastAPI TestClient.
        video_id: Video ID returned from upload.
        timeout: Max seconds to wait.
        interval: Seconds between poll attempts.

    Returns:
        Analysis response dict with ``script``.

    Raises:
        TimeoutError: If analysis does not complete within *timeout*.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/analyze/{video_id}")
        if resp.status_code != 200:
            time.sleep(interval)
            continue
        data = resp.json()
        if data["status"] == "completed":
            return data
        if data["status"] == "failed":
            pytest.fail(f"Analysis failed: {data.get('error')}")
        time.sleep(interval)
    raise TimeoutError(f"Analysis did not complete within {timeout}s")


def poll_export(
    client: TestClient,
    video_id: str,
    timeout: float = EXPORT_TIMEOUT,
    interval: float = 2.0,
) -> dict:
    """Poll ``GET /export/{video_id}`` until completed or failed.

    Args:
        client: FastAPI TestClient.
        video_id: Video ID for the export job.
        timeout: Max seconds to wait.
        interval: Seconds between poll attempts.

    Returns:
        Export response dict with ``output_path``.

    Raises:
        TimeoutError: If export does not complete within *timeout*.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/export/{video_id}")
        assert resp.status_code == 200, f"Poll failed: {resp.text}"
        data = resp.json()
        if data["status"] == "completed":
            return data
        if data["status"] == "failed":
            pytest.fail(
                f"Export failed: {data.get('error')!r}. "
                f"Output may still exist at: {data.get('output_path')}"
            )
        time.sleep(interval)
    raise TimeoutError(f"Export did not complete within {timeout}s")


# ═══════════════════════════════════════════════════════════════════
#  Output file helpers
# ═══════════════════════════════════════════════════════════════════

def find_output_file(video_id: str) -> Optional[str]:
    """Find a rendered output file for *video_id* on disk.

    Searches ``output/`` for any file whose name starts with the
    given *video_id* and ends with ``.mp4``.
    """
    output_dir = _project_root / "output"
    if not output_dir.is_dir():
        return None
    for fname in os.listdir(str(output_dir)):
        if fname.startswith(video_id) and fname.endswith(".mp4"):
            return str(output_dir / fname)
    return None


def get_export_output_path(data: dict) -> Optional[str]:
    """Extract output_path from export response data.

    The JobStore ``save()`` stores unknown fields (incl ``output_path``)
    inside the ``result`` JSON column, so the API response may have it
    nested.  We check both the top-level field and the ``result`` dict.
    """
    return data.get("output_path") or (data.get("result") or {}).get("output_path")


# ═══════════════════════════════════════════════════════════════════
#  Script helpers
# ═══════════════════════════════════════════════════════════════════

def sanitize_script_for_export(script: dict) -> None:
    """Mutate *script* in-place to work around render engine bugs.

    The FFmpeg render engine crashes when:
    - ``params`` is ``None``  (``mod.get("params", {}).get(...)`` → ``None.get(...)``)
    - ``position`` is ``None`` (``pos.get("x", ...)`` → ``None.get(...)``)
    - ``font_size`` / ``font_color`` are ``None``

    This function sets safe defaults for all modules.
    """
    for mod in script.get("modules", []):
        if mod.get("params") is None:
            mod["params"] = {}
        p = mod["params"]
        if p.get("position") is None:
            p["position"] = {"x": 960, "y": 540}
        if p.get("font_size") is None:
            p["font_size"] = 48
        if p.get("font_color") is None:
            p["font_color"] = "white"


def check_module_structure(module: dict) -> None:
    """Assert a single module has all required fields."""
    assert "id" in module, f"Module missing 'id': {module.get('label', '?')}"
    assert "type" in module, f"Module {module['id']} missing 'type'"
    assert "start_time" in module, f"Module {module['id']} missing 'start_time'"
    assert "duration" in module, f"Module {module['id']} missing 'duration'"
    assert module["type"] in (
        "title", "video_segment", "subtitle", "transition", "audio", "effect",
    ), f"Module {module['id']} has invalid type: {module['type']}"


# ═══════════════════════════════════════════════════════════════════
#  File format verification
# ═══════════════════════════════════════════════════════════════════

def verify_mp4_file(path: str) -> dict:
    """Verify *path* is a valid MP4 with at least one video stream.

    Checks the file header for the ``ftyp`` box, then runs ``ffprobe``
    to extract stream info.

    Returns:
        The parsed ffprobe JSON output.

    Raises:
        AssertionError: If the file is not a valid MP4.
    """
    assert os.path.isfile(path), f"File not found: {path}"
    assert os.path.getsize(path) > 1024, f"File too small: {os.path.getsize(path)} bytes"

    # Check MP4 magic bytes — starts with ftyp box
    with open(path, "rb") as f:
        header = f.read(12)
    assert header[4:8] == b"ftyp", (
        f"File does not appear to be valid MP4 (header={header.hex()})"
    )

    # ffprobe verification
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, timeout=30,
    )
    assert probe.returncode == 0, f"ffprobe failed: {probe.stderr}"
    probe_data = json.loads(probe.stdout)

    fmt = probe_data.get("format", {})
    assert "duration" in fmt, "ffprobe returned no duration"
    assert float(fmt["duration"]) > 0, f"Non-positive duration in output"

    streams = probe_data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    assert len(video_streams) >= 1, "Output has no video stream"

    return probe_data


# ═══════════════════════════════════════════════════════════════════
#  Script builder — export-ready script with proper positions
# ═══════════════════════════════════════════════════════════════════

def make_export_script(
    source_video_id: str,
    source_path: str,
    title: str = "E2E Test",
    duration: float = 10.0,
    fps: float = 30.0,
) -> dict:
    """Build a minimal export-ready script with 2 modules (title + video_segment).

    All ``params`` fields are set explicitly to avoid render engine bugs.
    """
    return {
        "version": "1.0.0",
        "metadata": {
            "title": title,
            "total_duration": duration,
            "fps": fps,
            "resolution": {"width": 1920, "height": 1080},
            "source_video_id": source_video_id,
        },
        "modules": [
            {
                "id": "mod_title",
                "type": "title",
                "label": "开场",
                "start_time": 0.0,
                "duration": 3.0,
                "track_index": 1,
                "params": {
                    "text_content": title,
                    "animation": "fade_in",
                    "position": {"x": 960, "y": 540},
                    "font_size": 48,
                    "font_color": "white",
                },
            },
            {
                "id": "mod_video",
                "type": "video_segment",
                "label": "正片",
                "start_time": 3.0,
                "duration": duration - 3.0,
                "track_index": 0,
                "source": {
                    "type": "video",
                    "path": source_path,
                    "start_offset": 0.0,
                    "end_offset": duration - 3.0,
                },
                "params": {
                    "position": {"x": 0, "y": 0},
                },
            },
        ],
        "tracks": [
            {"index": 0, "name": "视频轨", "type": "video", "muted": False, "locked": False},
            {"index": 1, "name": "文字轨", "type": "text", "muted": False, "locked": False},
        ],
    }
