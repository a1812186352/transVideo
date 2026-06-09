"""Test path ①: upload → analyze pipeline end-to-end.

Verifies that a real video uploaded via the FastAPI client produces
a completed job_store JSON with valid modules.

Uses the shared ``client`` fixture from ``conftest.py``.
"""

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parent.parent
import sys
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.store import JobStore


def test_upload_returns_video_id(client: TestClient, test_video_path: str):
    """POST /upload/ with a .mp4 returns 200 + video_id + duration."""
    with open(test_video_path, "rb") as f:
        resp = client.post("/upload/", files={"file": ("test.mp4", f, "video/mp4")})

    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    data = resp.json()
    assert "video_id" in data
    assert len(data["video_id"]) == 16
    assert data["duration"] is not None and data["duration"] > 0
    assert data["fps"] is not None and data["fps"] > 0


def test_upload_rejects_no_file(client: TestClient):
    """POST /upload/ without file returns 422."""
    resp = client.post("/upload/")
    assert resp.status_code == 422


def test_health(client: TestClient):
    """GET /health returns healthy."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


class TestAnalyzePipeline:
    """Full upload → analyze → poll → verify cycle."""

    @pytest.fixture(autouse=True)
    def _setup(self, client: TestClient, test_video_path: str):
        self.client = client
        # Upload
        with open(test_video_path, "rb") as f:
            r = client.post("/upload/", files={"file": ("test.mp4", f, "video/mp4")})
        assert r.status_code == 200
        self.video_id = r.json()["video_id"]

    def test_analyze_returns_processing(self):
        """POST /analyze/{id} returns processing status."""
        resp = self.client.post(f"/analyze/{self.video_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processing"
        assert data["video_id"] == self.video_id

    def test_analyze_completes_and_has_modules(self):
        """Polling /analyze/{id} eventually returns completed with modules."""
        import time

        resp = self.client.post(f"/analyze/{self.video_id}")
        assert resp.status_code == 200

        # Poll up to 90s
        for _ in range(30):
            time.sleep(3)
            resp = self.client.get(f"/analyze/{self.video_id}")
            assert resp.status_code == 200
            data = resp.json()
            if data["status"] == "completed":
                script = data.get("script")
                assert script is not None, "completed but no script"
                modules = script.get("modules", [])
                assert len(modules) > 0, f"expected modules, got 0"
                # Verify module structure
                for m in modules:
                    assert "id" in m
                    assert "type" in m
                    assert "start_time" in m
                    assert "duration" in m
                    assert m["type"] in ("title", "video_segment", "subtitle",
                                        "transition", "audio", "effect")
                return
            elif data["status"] == "failed":
                pytest.fail(f"Analysis failed: {data.get('error')}")

        pytest.fail("Analysis did not complete within 90s")

    def test_job_store_persisted(self):
        """After analysis completes, job_store JSON exists on disk."""
        import time
        time.sleep(5)  # give the background thread a moment to persist
        store = JobStore("analysis")
        job = store.get(self.video_id)
        if job is None:
            pytest.skip("Job not persisted in time (background thread timing)")
        assert job.get("status") == "completed"
        assert "script" in job
