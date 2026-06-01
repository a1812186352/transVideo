"""Test path ②: script builder → validator correctness.

Validates that ScriptBuilder produces schema-compliant output and
ScriptValidator correctly catches errors.
"""

import json
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parent.parent
import sys
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from script.schema import MIGRATABLE_SCRIPT_SCHEMA
from script.validator import ScriptValidator


# ── Helpers ──

@pytest.fixture(scope="module")
def validator(script_schema) -> ScriptValidator:
    return ScriptValidator(script_schema)


# ── Schema validation ──

class TestScriptBuilder:

    def test_create_empty_script_has_required_fields(self, builder):
        """create_empty_script returns valid structure even with no modules."""
        script = builder.create_empty_script(title="Empty")
        assert script["version"] == "1.0.0"
        assert script["metadata"]["title"] == "Empty"
        assert script["modules"] == []

    def test_from_module_tree_generates_unique_ids(self, builder):
        """Duplicate module IDs are auto-repaired."""
        modules = [
            {"id": "dup", "type": "title", "start_time": 0.0, "duration": 2.0,
             "track_index": 0},
            {"id": "dup", "type": "video_segment", "start_time": 2.0, "duration": 3.0,
             "track_index": 0},
        ]
        script = builder.from_module_tree(modules, title="Dedup")
        ids = [m["id"] for m in script["modules"]]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {ids}"

    def test_from_module_tree_missing_ids_get_generated(self, builder):
        """Modules without an 'id' field get one assigned."""
        modules = [
            {"type": "title", "start_time": 0.0, "duration": 2.0, "track_index": 0},
        ]
        script = builder.from_module_tree(modules, title="AutoID")
        assert script["modules"][0]["id"].startswith("mod_")

    def test_generate_id_is_unique(self, builder):
        """Sequential calls to generate_id produce different values."""
        a = builder.generate_id()
        b = builder.generate_id()
        assert a != b


class TestScriptValidator:

    def test_valid_script_passes_all_checks(self, validator, valid_script):
        """A well-formed script produces zero issues."""
        issues = validator.validate(valid_script)
        errors = [i for i in issues if i["severity"] == "error"]
        assert errors == [], f"Unexpected errors: {errors}"

    def test_valid_script_is_valid(self, validator, valid_script):
        assert validator.is_valid(valid_script) is True

    def test_broken_script_has_schema_error(self, validator, broken_script):
        """Script missing 'start_time' on a required module fails schema."""
        issues = validator.validate(broken_script)
        schema_issues = [i for i in issues if "start_time" in i.get("message", "")]
        assert len(schema_issues) >= 1, f"Expected schema error, got: {issues}"

    def test_broken_script_not_valid(self, validator, broken_script):
        assert validator.is_valid(broken_script) is False

    def test_duplicate_id_detected(self, validator):
        """Two modules sharing the same id raise an error.

        Bypass ScriptBuilder (which auto-repairs duplicate IDs) and
        construct the script dict directly.
        """
        script = {
            "version": "1.0.0",
            "metadata": {
                "title": "Collision",
                "created_at": "2026-01-01T00:00:00Z",
                "total_duration": 3.0,
            },
            "modules": [
                {"id": "collision", "type": "title", "start_time": 0.0,
                 "duration": 2.0, "track_index": 0},
                {"id": "collision", "type": "effect", "start_time": 2.0,
                 "duration": 1.0, "track_index": 0},
            ],
        }
        issues = validator.validate(script)
        errs = [i for i in issues if "Duplicate" in i.get("message", "")]
        assert len(errs) >= 1, f"Expected duplicate error, got: {issues}"

    def test_overlap_detected(self, validator, builder):
        """Overlapping modules on same track raise an error."""
        modules = [
            {"id": "m1", "type": "video_segment", "start_time": 0.0,
             "duration": 5.0, "track_index": 0},
            {"id": "m2", "type": "video_segment", "start_time": 3.0,
             "duration": 5.0, "track_index": 0},  # overlaps m1
        ]
        script = builder.from_module_tree(modules, title="Overlap")
        issues = validator.validate(script)
        overlap = [i for i in issues if "overlap" in i.get("message", "").lower()]
        assert len(overlap) >= 1, f"Expected overlap errors, got: {issues}"

    def test_timeline_gap_is_warning_not_error(self, validator, builder):
        """Non-contiguous modules on same track produce a warning."""
        modules = [
            {"id": "m1", "type": "video_segment", "start_time": 0.0,
             "duration": 3.0, "track_index": 0},
            {"id": "m2", "type": "video_segment", "start_time": 5.0,
             "duration": 2.0, "track_index": 0},  # 2s gap
        ]
        script = builder.from_module_tree(modules, title="Gap")
        issues = validator.validate(script)
        gaps = [i for i in issues if "gap" in i.get("message", "").lower()]
        warnings = [i for i in issues if i["severity"] == "warning"]
        assert len(gaps) >= 1, f"Expected gap warnings, got: {issues}"
        assert all(i["severity"] == "warning" for i in gaps)
