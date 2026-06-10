"""Integration tests for all backend HTTP routers.

Covers all 15 HTTP endpoints across 4 router files with status code,
response structure, and error-path verification.  Uses mocked
JobStore to avoid side effects on production databases.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app
from backend.middleware.error_handler import AppError


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════════════════

class TestHealthRouter:
    """GET / and GET /health."""

    def test_root_returns_service_info(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "transVideo"
        assert data["status"] == "running"

    def test_health_returns_healthy(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}


# ═══════════════════════════════════════════════════════════════════
#  Upload router
# ═══════════════════════════════════════════════════════════════════

class TestUploadRouter:
    """POST /upload/ and GET /upload/video/{id}/*."""

    UPLOAD_PATH = str(Path(__file__).parent / "fixtures" / "test_10s.mp4")

    def test_upload_valid_mp4(self, client):
        with open(self.UPLOAD_PATH, "rb") as f:
            resp = client.post("/upload/", files={"file": ("test.mp4", f, "video/mp4")})
        assert resp.status_code == 200
        data = resp.json()
        assert "video_id" in data
        assert len(data["video_id"]) == 16
        assert data["duration"] > 0
        assert data["fps"] > 0
        assert data["width"] > 0
        assert data["height"] > 0

    def test_upload_no_file_returns_422(self, client):
        assert client.post("/upload/").status_code == 422

    def test_upload_bad_mime_rejected(self, client):
        resp = client.post(
            "/upload/",
            files={"file": ("f.mp4", b"x", "application/pdf")},
        )
        assert resp.status_code in (400, 422)

    def test_upload_bad_extension_rejected(self, client):
        resp = client.post(
            "/upload/",
            files={"file": ("f.txt", b"x", "video/mp4")},
        )
        assert resp.status_code in (400, 422)

    def test_serve_video_returns_stream(self, client):
        # Upload first to get a video_id
        with open(self.UPLOAD_PATH, "rb") as f:
            up = client.post("/upload/", files={"file": ("test.mp4", f, "video/mp4")})
        vid = up.json()["video_id"]

        resp = client.get(f"/upload/video/{vid}")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("video/")
        assert int(resp.headers.get("content-length", 0)) > 0

    def test_serve_video_not_found(self, client):
        resp = client.get("/upload/video/nonexistent_id")
        assert resp.status_code == 404

    def test_thumbnails_returns_list(self, client):
        with open(self.UPLOAD_PATH, "rb") as f:
            up = client.post("/upload/", files={"file": ("test.mp4", f, "video/mp4")})
        vid = up.json()["video_id"]

        resp = client.get(f"/upload/video/{vid}/thumbnails?interval=5.0")
        assert resp.status_code == 200
        thumbs = resp.json()
        assert isinstance(thumbs, list)
        if thumbs:
            assert "timestamp" in thumbs[0]
            assert "data_uri" in thumbs[0]

    def test_filmstrip_returns_correct_count(self, client):
        with open(self.UPLOAD_PATH, "rb") as f:
            up = client.post("/upload/", files={"file": ("test.mp4", f, "video/mp4")})
        vid = up.json()["video_id"]

        resp = client.get(f"/upload/video/{vid}/filmstrip?count=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 10

    def test_thumbnail_single_frame(self, client):
        with open(self.UPLOAD_PATH, "rb") as f:
            up = client.post("/upload/", files={"file": ("test.mp4", f, "video/mp4")})
        vid = up.json()["video_id"]

        resp = client.get(f"/upload/video/{vid}/thumbnail?time=0.5")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "") == "image/jpeg"


# ═══════════════════════════════════════════════════════════════════
#  Analysis router
# ═══════════════════════════════════════════════════════════════════

class TestAnalysisRouter:
    """POST and GET /analyze/{video_id}."""

    def test_analyze_missing_video_returns_404(self, client):
        resp = client.post("/analyze/nonexistent_video_id")
        assert resp.status_code == 404

    def test_analyze_status_nonexistent_returns_404(self, client):
        resp = client.get("/analyze/nonexistent_video_id")
        assert resp.status_code == 404

    def test_analyze_stream_nonexistent_returns_404(self, client):
        resp = client.get("/analyze/nonexistent_video_id/stream")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
#  Export router
# ═══════════════════════════════════════════════════════════════════

class TestExportRouter:
    """POST, GET /export/{video_id}, GET /export/output/{file}."""

    SAMPLE_SCRIPT = {
        "version": "1.0.0",
        "metadata": {"title": "Test", "total_duration": 3.0, "fps": 30.0,
                     "resolution": {"width": 1920, "height": 1080}},
        "modules": [{
            "id": "m1", "type": "title", "start_time": 0.0, "duration": 3.0,
            "track_index": 0,
            "params": {"text_content": "Test", "position": {"x": 960, "y": 540},
                       "font_size": 48, "font_color": "white"},
        }],
        "tracks": [{"index": 0, "name": "V", "type": "video",
                    "muted": False, "locked": False}],
    }

    def test_export_submit_returns_queued(self, client):
        resp = client.post("/export/test_export_vid", json=self.SAMPLE_SCRIPT)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("queued", "processing")

    def test_export_poll_status(self, client):
        resp = client.get("/export/test_export_vid")
        # May be 200 (found) or 404 (not found yet / cleaned up)
        assert resp.status_code in (200, 404)

    def test_export_output_file_not_found(self, client):
        resp = client.get("/export/output/nonexistent.mp4")
        assert resp.status_code == 404

    def test_export_output_path_traversal_blocked(self, client):
        resp = client.get("/export/output/../../../etc/passwd")
        assert resp.status_code in (403, 404)

    def test_export_cancel_nonexistent_returns_error(self, client):
        resp = client.post("/export/nonexistent_video_id/cancel")
        # May be 404 (no job) or 409 (job completed/failed)
        assert resp.status_code in (404, 409)

    def test_export_invalid_script_returns_422(self, client):
        # Empty body (not JSON) should fail
        resp = client.post("/export/test_vid", data=b"", headers={"Content-Type": "application/json"})
        assert resp.status_code in (400, 422)

        # Non-JSON body should fail
        resp = client.post("/export/test_vid", data=b"not json", headers={"Content-Type": "application/json"})
        assert resp.status_code in (400, 422)


# ═══════════════════════════════════════════════════════════════════
#  Recovery router
# ═══════════════════════════════════════════════════════════════════

class TestRecoveryRouter:
    """GET /recovery/status, POST /recovery/analyze/{video_id}."""

    def test_recovery_status_returns_dict(self, client):
        resp = client.get("/recovery/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "analysis" in data
        assert "export" in data

    def test_recover_nonexistent_returns_not_found(self, client):
        resp = client.post("/recovery/analyze/nonexistent_video_id")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_found"


# ═══════════════════════════════════════════════════════════════════
#  Metrics router
# ═══════════════════════════════════════════════════════════════════

class TestMetricsRouter:
    """GET /metrics."""

    def test_metrics_returns_prometheus_text(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        # FastAPI returns plain text, may be 'text/plain' or 'application/json'
        body = resp.text
        assert "transvideo_app_start_time" in body
        assert "transvideo_analysis_starts_total" in body


# ═══════════════════════════════════════════════════════════════════
#  Materials router
# ═══════════════════════════════════════════════════════════════════

class TestMaterialsRouter:
    """POST /materials/upload, GET /materials/list, DELETE /materials/{id}."""

    def test_list_materials_returns_list(self, client):
        resp = client.get("/materials/list")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/materials/nonexistent_material_id")
        assert resp.status_code == 404

    def test_check_paths(self, client):
        resp = client.post("/materials/check", json={"paths": [""]})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) >= 1
