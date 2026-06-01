"""Shared fixtures for transVideo integration tests."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

# Ensure project root is on sys.path so all modules are importable
_project_root = Path(__file__).resolve().parent.parent
import sys
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from script.builder import ScriptBuilder
from script.schema import MIGRATABLE_SCRIPT_SCHEMA


# ── Paths ──

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_VIDEO = str(FIXTURES_DIR / "test_10s.mp4")


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
