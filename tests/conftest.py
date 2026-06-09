"""Shared fixtures for transVideo integration and end-to-end tests.

Provides:
- :func:`test_video_path` — 10s synthetic test MP4
- :func:`client` — FastAPI TestClient for HTTP-level testing
- :func:`e2e_test_video` — small .mov from ``instances/`` for E2E
- :func:`builder` / :func:`valid_script` / :func:`broken_script` — script-level fixtures
- :func:`temp_job_dir` — isolated job_store directory per test
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest
from fastapi.testclient import TestClient

# ── Ensure project root is discoverable before any module import ──
# We append to sys.path early so that direct imports from conftest
# or sub-modules like helpers work even when a 'tests' package
# exists in site-packages.

# Ensure project root is on sys.path so all modules are importable
_project_root = Path(__file__).resolve().parent.parent
import sys
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.main import app
from script.builder import ScriptBuilder
from script.schema import MIGRATABLE_SCRIPT_SCHEMA

# ── Add tests/ dir to sys.path so ``_e2e_helpers`` can be imported
#    without the ``tests.`` prefix (which shadows to site-packages).
if str(_project_root / "tests") not in sys.path:
    sys.path.insert(0, str(_project_root / "tests"))
import _e2e_helpers  # noqa: E402


# ── Paths ──

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_VIDEO = str(FIXTURES_DIR / "test_10s.mp4")
INSTANCES_DIR = _project_root / "instances"


# ── Fixtures ──

@pytest.fixture(scope="session")
def test_video_path() -> str:
    """Path to the 10s synthetic test video."""
    assert os.path.isfile(TEST_VIDEO), f"Test video not found: {TEST_VIDEO}"
    return TEST_VIDEO


@pytest.fixture(scope="session")
def script_schema() -> Dict[str, Any]:
    """The JSON Schema for MigratableScript."""
    return MIGRATABLE_SCRIPT_SCHEMA


@pytest.fixture(scope="session")
def builder() -> ScriptBuilder:
    return ScriptBuilder()


@pytest.fixture(scope="session")
def client() -> TestClient:
    """FastAPI TestClient — synchronous HTTP-level testing.

    The test client handles background tasks (used by export)
    transparently.  Use for all REST endpoint tests.
    """
    return TestClient(app)


@pytest.fixture(scope="session")
def e2e_test_video() -> str:
    """Pick the first available .mov from ``instances/`` for E2E testing.

    Falls back to ``tests/fixtures/test_10s.mp4`` if no .mov is found.
    """
    if INSTANCES_DIR.is_dir():
        mov_files = sorted(INSTANCES_DIR.glob("*.mov"))
        if mov_files:
            return str(mov_files[0])
    # Fallback
    assert os.path.isfile(TEST_VIDEO), f"Test video not found: {TEST_VIDEO}"
    return TEST_VIDEO


@pytest.fixture
def temp_job_dir() -> Generator[str, None, None]:
    """Temporary directory that isolates job_store side effects."""
    with tempfile.TemporaryDirectory(prefix="transvideo_test_") as tmp:
        yield tmp


@pytest.fixture
def valid_script(builder: ScriptBuilder) -> Dict[str, Any]:
    """A minimal valid MigratableScript with 2 modules."""
    modules = [
        {
            "id": "mod_0001",
            "type": "title",
            "label": "开场",
            "start_time": 0.0,
            "duration": 3.0,
            "track_index": 1,
            "params": {"text_content": "测试视频", "animation": "fade_in"},
        },
        {
            "id": "mod_0002",
            "type": "video_segment",
            "label": "正片",
            "start_time": 3.0,
            "duration": 7.0,
            "track_index": 0,
            "source": {"type": "video", "path": TEST_VIDEO},
        },
    ]
    return builder.from_module_tree(
        modules=modules,
        title="Test Project",
        total_duration=10.0,
        fps=30.0,
        source_video_id="test_001",
    )


@pytest.fixture
def broken_script(builder: ScriptBuilder) -> Dict[str, Any]:
    """A script with intentional errors: overlapping modules + missing required field."""
    modules = [
        {
            "id": "mod_a",
            "type": "video_segment",
            "start_time": 0.0,
            "duration": 5.0,
            "track_index": 0,
        },
        {
            "id": "mod_b",
            "type": "video_segment",
            # missing start_time — schema violation
            "duration": 5.0,
            "track_index": 0,
        },
    ]
    return builder.from_module_tree(
        modules=modules,
        title="Broken",
        total_duration=5.0,
        fps=30.0,
    )


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════
#  E2E-specific fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def isolated_job_stores():
    """Redirect production JobStores to a temp directory per test.

    Monkeypatches the ``_store_root`` of the module-level JobStore
    singletons in ``backend.routers.analysis`` and
    ``backend.routers.export`` so that analysis and export jobs
    are persisted to an isolated SQLite database.

    Uses ``tempfile.mkdtemp()`` rather than ``tmp_path`` to avoid
    permissions issues on Windows CI runners.
    """
    import sqlite3
    import shutil
    import backend.routers.analysis as analysis_mod
    import backend.routers.export as export_mod
    from backend.store import JobStore

    _tmp_root = tempfile.mkdtemp(prefix="transvideo_e2e_")
    _orig_stores = {}

    def _redirect_store(store: JobStore, namespace: str, tmp_root: str):
        # Snapshot original state so we can restore in teardown
        _orig_stores[namespace] = {
            "store_root": store._store_root,
            "db_path": store._db_path,
            "conn": store._conn,
        }

        # Build isolated DB
        store_dir = os.path.join(tmp_root, "job_store")
        os.makedirs(store_dir, exist_ok=True)
        db_path = os.path.join(store_dir, f"{namespace}.db")

        # Close old connection
        try:
            store._conn.close()
        except Exception:
            pass

        # Point to new location
        store._store_root = store_dir
        store._db_path = db_path
        store._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            isolation_level=None,
        )
        store._conn.row_factory = sqlite3.Row
        store._conn.execute("PRAGMA journal_mode=WAL")
        store._conn.execute("PRAGMA foreign_keys=ON")
        store._init_schema()
        store._cache.clear()
        store._progress_last_write.clear()

    _redirect_store(analysis_mod._jobs, "analysis", _tmp_root)
    _redirect_store(export_mod._export_jobs, "export", _tmp_root)

    yield

    # Restore original connections
    for namespace, orig in _orig_stores.items():
        store = analysis_mod._jobs if namespace == "analysis" else export_mod._export_jobs
        try:
            store._conn.close()
        except Exception:
            pass
        store._store_root = orig["store_root"]
        store._db_path = orig["db_path"]
        store._conn = sqlite3.connect(
            orig["db_path"],
            check_same_thread=False,
            isolation_level=None,
        )
        store._conn.row_factory = sqlite3.Row
        store._conn.execute("PRAGMA journal_mode=WAL")
        store._conn.execute("PRAGMA foreign_keys=ON")
        store._cache.clear()
        store._progress_last_write.clear()

    # Remove temp dir
    try:
        shutil.rmtree(_tmp_root, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def export_ready_script() -> Dict[str, Any]:
    """An export-ready script with explicit position fields.

    The render engine crashes when ``params.position`` is ``None``
    (Pydantic serializes the default).  This fixture provides a
    script that works around that bug.
    """
    return _e2e_helpers.make_export_script(
        source_video_id="test_fixture",
        source_path=TEST_VIDEO,
        title="E2E Fixture",
        duration=10.0,
        fps=30.0,
    )
