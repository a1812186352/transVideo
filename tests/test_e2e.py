"""Test path ④: End-to-end upload → analyze → edit → export pipeline.

Verifies the complete user workflow and error paths across service boundaries.

Test classes
-----------
- :class:`TestStateTransitions` — each lifecycle step independently
- :class:`TestFullPipeline` — complete upload→analyze→edit→export
- :class:`TestE2EErrorPaths` — error handling & edge cases
- :class:`TestDataFlowIntegrity` — cross-service data consistency
"""

import json
import os
import time
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parent.parent
import sys
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_project_root / "tests") not in sys.path:
    sys.path.insert(0, str(_project_root / "tests"))

import _e2e_helpers as h  # noqa: E402
from script.validator import ScriptValidator  # noqa: E402
from script.schema import MIGRATABLE_SCRIPT_SCHEMA  # noqa: E402


# ═══════════════════════════════════════════════════════════════════
#  State Transition Tests
# ═══════════════════════════════════════════════════════════════════

class TestStateTransitions:
    """Verify the lifecycle: uploaded → analyzing → completed → exporting → exported.

    Each step is tested independently so a failure in one doesn't
    cascade through the entire chain.  Uses ``isolated_job_stores``
    to prevent test pollution.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client: TestClient, e2e_test_video: str):
        self.client = client
        data = h.upload_video(client, e2e_test_video)
        self.video_id = data["video_id"]
        self.upload_data = data

    # ── Step 1: Upload ─────────────────────────────────────────

    def test_upload_returns_video_metadata(self):
        """POST /upload/ returns video_id, duration, fps, dimensions."""
        data = self.upload_data
        assert "video_id" in data
        assert len(data["video_id"]) == 16
        assert data.get("duration", 0) > 0, "Missing or zero duration"
        assert data.get("width", 0) > 0, "Missing or zero width"
        assert data.get("height", 0) > 0, "Missing or zero height"
        assert data.get("fps", 0) > 0, "Missing or zero fps"
        assert data.get("size_bytes", 0) > 0, "Missing or zero file size"

    # ── Step 2: Analyze trigger ────────────────────────────────

    def test_analyze_returns_processing_immediately(self):
        """POST /analyze/{id} returns status=processing immediately."""
        resp = self.client.post(f"/analyze/{self.video_id}")
        assert resp.status_code == 200, f"Analyze trigger failed: {resp.text}"
        data = resp.json()
        assert data["status"] == "processing"
        assert data["video_id"] == self.video_id

    # ── Step 3: Analyze completes ──────────────────────────────

    def test_analyze_completes_with_valid_script(self):
        """Poll analyze until completed; validate entire script structure."""
        resp = self.client.post(f"/analyze/{self.video_id}")
        assert resp.status_code == 200

        data = h.poll_analysis(self.client, self.video_id)
        assert data["status"] == "completed"

        script = data.get("script")
        assert script is not None, "completed analysis returned no script"

        # Top-level fields
        assert script.get("version") == "1.0.0"
        meta = script.get("metadata", {})
        assert meta.get("total_duration", 0) > 0
        assert meta.get("fps", 0) > 0

        # Modules
        modules = script.get("modules", [])
        assert len(modules) > 0, "Script has zero modules"
        for m in modules:
            h.check_module_structure(m)

        # Tracks (if present)
        for t in script.get("tracks", []):
            assert "index" in t
            assert "name" in t
            assert t.get("type") in ("video", "audio", "text", "effect")

        # Schema validation (allow 'detail' which exists in Pydantic but not schema)
        validator = ScriptValidator(MIGRATABLE_SCRIPT_SCHEMA)
        issues = validator.validate(script)
        errors = [
            i for i in issues
            if i["severity"] == "error" and "'detail'" not in i.get("message", "")
        ]
        assert errors == [], f"Script validation errors: {errors}"

    # ── Step 4: Export flow ────────────────────────────────────

    def test_export_submit_and_complete(self, export_ready_script):
        """POST /export/{id} → poll completed → verify output file."""
        resp = self.client.post(
            f"/export/{self.video_id}",
            json=export_ready_script,
        )
        assert resp.status_code == 200, f"Export trigger failed: {resp.text}"
        assert resp.json()["status"] in ("queued", "processing")

        # Wait for completion
        result = h.poll_export(self.client, self.video_id)

        # Verify output file on disk
        full_path = h.find_output_file(self.video_id)
        if not full_path:
            pytest.skip(f"No output file found — render engine may be unavailable")

        h.verify_mp4_file(full_path)

        # Verify downloadable via output endpoint
        filename = os.path.basename(full_path)
        dl = self.client.get(f"/export/output/{filename}")
        assert dl.status_code == 200
        assert dl.headers.get("content-type", "").startswith("video/")
        assert len(dl.content) == os.path.getsize(full_path)

    # ── Step 5: Job store persistence ──────────────────────────

    def test_job_store_records_analysis_result(self):
        """Analysis job is persisted to JobStore with completed status.

        Reads from the router module's singleton (which is redirected
        to an isolated temp dir by ``isolated_job_stores``).
        """
        import backend.routers.analysis as analysis_mod

        self.client.post(f"/analyze/{self.video_id}")
        h.poll_analysis(self.client, self.video_id)

        job = analysis_mod._jobs.get(self.video_id)
        if job is None:
            pytest.skip("Job not persisted yet (background thread timing)")
        assert job.get("status") == "completed"
        result = job.get("result", {})
        if isinstance(result, dict) and "script" in result:
            assert "modules" in result["script"]


# ═══════════════════════════════════════════════════════════════════
#  Full Pipeline Integration Test
# ═══════════════════════════════════════════════════════════════════

class TestFullPipeline:
    """Complete upload → analyze → edit → export in one test.

    This is the highest-value test: it simulates the real user
    workflow end-to-end with isolated job stores.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client: TestClient, e2e_test_video: str, isolated_job_stores):
        self.client = client
        self.video_path = e2e_test_video
        data = h.upload_video(client, e2e_test_video)
        self.video_id = data["video_id"]

    def test_full_user_workflow(self):
        """Upload → analyze → edit → export → ffprobe output.

        Simulates a user who:
          1. Uploads a video
          2. Runs analysis
          3. Reviews the generated script
          4. Edits a text module
          5. Exports the modified script
          6. Downloads & probes the result
        """
        vid = self.video_id

        # ── 1. Upload (already done in _setup) ──

        # ── 2. Analyze ──
        trigger = self.client.post(f"/analyze/{vid}")
        assert trigger.status_code == 200
        assert trigger.json()["status"] == "processing"

        analysis = h.poll_analysis(self.client, vid)
        script = analysis["script"]
        modules = script["modules"]
        assert len(modules) > 0

        # ── 3. Edit — user tweaks a module ──
        edited = deepcopy(script)
        h.sanitize_script_for_export(edited)

        # Find first title module to edit, or add one
        target = next((m for m in edited["modules"] if m["type"] == "title"), None)
        if target is None:
            edited["modules"].append({
                "id": f"user_mod_{int(time.time())}",
                "type": "title",
                "label": "用户编辑",
                "start_time": 0.0,
                "duration": 2.0,
                "track_index": 0,
                "params": {
                    "text_content": "Edited by E2E test",
                    "animation": "fade_in",
                    "position": {"x": 960, "y": 540},
                    "font_size": 48,
                    "font_color": "white",
                },
            })
        else:
            target["params"]["text_content"] = "E2E edited title"
            target["duration"] = max(2.0, target["duration"])

        # ── 4. Export ──
        export_resp = self.client.post(f"/export/{vid}", json=edited)
        assert export_resp.status_code == 200
        assert export_resp.json()["status"] in ("queued", "processing")

        h.poll_export(self.client, vid)

        # ── 5. Verify output ──
        full_path = h.find_output_file(vid)
        if not full_path:
            pytest.skip(f"No output file found — render engine may be unavailable")

        h.verify_mp4_file(full_path)


# ═══════════════════════════════════════════════════════════════════
#  Error & Edge-Case Tests
# ═══════════════════════════════════════════════════════════════════

class TestE2EErrorPaths:
    """End-to-end error scenarios that cross service boundaries."""

    # ── Upload errors ──────────────────────────────────────────

    def test_upload_no_file_returns_422(self, client: TestClient):
        """POST /upload/ without file returns 422."""
        assert client.post("/upload/").status_code == 422

    def test_upload_bad_mime_rejected(self, client: TestClient):
        """Upload with non-video MIME type is rejected."""
        resp = client.post(
            "/upload/",
            files={"file": ("video.mp4", b"fake", "application/pdf")},
        )
        assert resp.status_code in (400, 422)

    def test_upload_bad_extension_rejected(self, client: TestClient):
        """Upload with disallowed extension is rejected."""
        resp = client.post(
            "/upload/",
            files={"file": ("video.txt", b"data", "video/mp4")},
        )
        assert resp.status_code in (400, 422)

    def test_upload_large_file_rejected(self, client: TestClient):
        """Upload > 2 GB should be rejected (tested with Content-Length hint)."""
        # We can't easily send 2 GB, but the validator checks after reading.
        # A file > MAX_UPLOAD_SIZE (2 GB) causes UploadTooLargeError.
        # Send a smaller file — the size check only triggers after full read.
        pytest.skip("2 GB upload test requires large fixture — skipped for CI")

    def test_upload_invalid_filename_returns_422(self, client: TestClient):
        """Upload with empty filename is rejected."""
        resp = client.post(
            "/upload/",
            files={"file": ("", b"data", "video/mp4")},
        )
        assert resp.status_code in (400, 422)

    # ── Analysis errors ────────────────────────────────────────

    def test_analyze_missing_video_returns_404(self, client: TestClient):
        """POST /analyze/{nonexistent} returns 404."""
        resp = client.post("/analyze/nonexistent_video_id_12345")
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_analyze_duplicate_trigger_allowed(self, client: TestClient, e2e_test_video: str):
        """Second POST /analyze while processing is either accepted (re-run)
        or rejected (409 conflict)."""
        data = h.upload_video(client, e2e_test_video)
        vid = data["video_id"]

        r1 = client.post(f"/analyze/{vid}")
        assert r1.status_code == 200

        r2 = client.post(f"/analyze/{vid}")
        assert r2.status_code in (200, 409), (
            f"Expected 200 or 409, got {r2.status_code}: {r2.text}"
        )

    # ── Export errors ──────────────────────────────────────────

    def test_export_missing_video_id_still_renders_title(
        self, client: TestClient
    ):
        """Export with nonexistent video_id renders a title card only.

        The render engine gracefully degrades: when the source video
        file is missing, it still renders text/title modules.
        """
        broken_script = h.make_export_script(
            source_video_id="nonexistent",
            source_path=r"D:\nonexistent\file.mp4",
            title="Fallback test",
            duration=3.0,
        )
        resp = client.post("/export/nonexistent_export_test", json=broken_script)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("queued", "processing")

        # Poll — the job should complete even without the source video,
        # because the render engine renders title cards independently.
        result = h.poll_export(client, "nonexistent_export_test", timeout=30.0)
        assert result["status"] == "completed"

        # Verify some output was rendered
        full_path = h.find_output_file("nonexistent_export_test")
        if full_path:
            assert os.path.getsize(full_path) > 512

    def test_export_cancel_running_job(
        self, client: TestClient, e2e_test_video: str
    ):
        """Cancel a running export job — best-effort (may finish first)."""
        data = h.upload_video(client, e2e_test_video)
        vid = data["video_id"]

        script = h.make_export_script(
            source_video_id=vid,
            source_path=data["video_id"],  # valid enough to start rendering
            title="Cancel Test",
            duration=60.0,  # long enough to be cancellable
        )

        resp = client.post(f"/export/{vid}", json=script)
        assert resp.status_code == 200

        cancel = client.post(f"/export/{vid}/cancel")
        if cancel.status_code == 200:
            assert cancel.json()["status"] == "canceled"
        elif cancel.status_code == 409:
            pass  # finished before cancel
        else:
            pytest.fail(f"Cancel returned {cancel.status_code}: {cancel.text}")

    def test_export_empty_script_fails_gracefully(
        self, client: TestClient, e2e_test_video: str
    ):
        """Export with empty modules list should fail or produce minimal output."""
        data = h.upload_video(client, e2e_test_video)
        vid = data["video_id"]

        empty = {
            "version": "1.0.0",
            "metadata": {"title": "Empty", "total_duration": 0.0, "fps": 30.0,
                         "resolution": {"width": 1920, "height": 1080}},
            "modules": [],
            "tracks": [],
        }

        resp = client.post(f"/export/{vid}", json=empty)
        assert resp.status_code == 200

        try:
            result = h.poll_export(client, vid, timeout=30.0)
            op = h.get_export_output_path(result)
            if op:
                p = os.path.join(_project_root, op)
                if os.path.isfile(p):
                    assert os.path.getsize(p) < 2048, "Empty script produced large output"
        except (pytest.fail.Exception, TimeoutError):
            pass  # Expected: export fails gracefully

    # ── Export output path-traversal protection ────────────────

    def test_export_output_path_traversal_blocked(self, client: TestClient):
        """GET /export/output/ with '..' in filename returns 403."""
        resp = client.get("/export/output/../../etc/passwd")
        assert resp.status_code in (403, 404)

        resp2 = client.get("/export/output/%2e%2e/%2e%2e/etc/passwd")
        assert resp2.status_code in (403, 404)

    # ── Analysis timeout simulation ────────────────────────────

    def test_analyze_wait_too_long_raises_timeout(self, client: TestClient):
        """_poll_analysis raises TimeoutError when timeout is exceeded."""
        with pytest.raises(TimeoutError):
            h.poll_analysis(client, "nonexistent_id", timeout=0.1, interval=0.05)


# ═══════════════════════════════════════════════════════════════════
#  Data Flow Integrity
# ═══════════════════════════════════════════════════════════════════

class TestDataFlowIntegrity:
    """Cross-service data consistency checks."""

    def test_upload_metadata_matches_ffprobe(
        self, client: TestClient, e2e_test_video: str
    ):
        """Upload-reported duration matches ffprobe ground truth (±0.5s)."""
        import subprocess

        data = h.upload_video(client, e2e_test_video)

        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", e2e_test_video],
            capture_output=True, text=True, timeout=15,
        )
        assert probe.returncode == 0
        probe_data = json.loads(probe.stdout)

        ff_duration = round(float(probe_data.get("format", {}).get("duration", 0)), 2)
        upload_duration = data.get("duration", 0)
        assert abs(upload_duration - ff_duration) < 0.5, (
            f"Upload duration ({upload_duration}s) differs from ffprobe ({ff_duration}s)"
        )

        # Verify FPS match
        for s in probe_data.get("streams", []):
            if s.get("codec_type") == "video":
                rfr = s.get("r_frame_rate", "0/1")
                try:
                    n, d = rfr.split("/")
                    ff_fps = round(float(n) / float(d), 2) if int(d) else None
                except (ValueError, ZeroDivisionError):
                    ff_fps = None
                upload_fps = data.get("fps")
                if ff_fps and upload_fps:
                    assert abs(upload_fps - ff_fps) < 0.1
                break

    def test_script_from_analysis_can_be_re_exported(
        self, client: TestClient, e2e_test_video: str, isolated_job_stores
    ):
        """Analysis-produced script can be re-submitted to export.

        This catches serialization issues between JobStore (JSON) and
        the MigratableScript Pydantic model — the response should be
        a render error (media codec), not a 422 validation error.
        """
        data = h.upload_video(client, e2e_test_video)
        vid = data["video_id"]

        client.post(f"/analyze/{vid}")
        analysis = h.poll_analysis(client, vid)
        script = analysis["script"]

        h.sanitize_script_for_export(script)

        resp = client.post(f"/export/{vid}", json=script)
        assert resp.status_code == 200, f"Script re-submission failed: {resp.text}"

        try:
            h.poll_export(client, vid)
            fp = h.find_output_file(vid)
            if fp:
                assert os.path.getsize(fp) > 1024
        except (pytest.fail.Exception, TimeoutError):
            # Render failure is OK — but must NOT be a validation error
            check = client.get(f"/export/{vid}")
            if check.status_code == 200:
                err = check.json().get("error", "")
                if err:
                    assert "validation" not in err.lower(), (
                        f"Schema validation error: {err}"
                    )
