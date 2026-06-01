"""Test path ③: manipulator → re-validate.

Verifies that ScriptManipulator operations (add, remove, reorder, duplicate,
shift, compact) maintain a valid script after each mutation.
"""

from copy import deepcopy
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parent.parent
import sys
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from script.manipulator import ScriptManipulator
from script.validator import ScriptValidator
from script.schema import MIGRATABLE_SCRIPT_SCHEMA


@pytest.fixture(scope="module")
def manipulator() -> ScriptManipulator:
    return ScriptManipulator()


@pytest.fixture(scope="module")
def validator(script_schema) -> ScriptValidator:
    return ScriptValidator(script_schema)


def _check_valid(validator: ScriptValidator, script: dict, label: str):
    """Assert a script passes validation."""
    issues = validator.validate(script)
    errors = [i for i in issues if i["severity"] == "error"]
    assert errors == [], f"{label}: validation errors: {errors}"


class TestManipulatorOps:

    def test_add_module(self, manipulator, validator, valid_script):
        modules = deepcopy(valid_script["modules"])
        new_mod = {
            "id": "new_mod",
            "type": "effect",
            "start_time": 0.0,
            "duration": 1.0,
            "track_index": 0,
        }
        result = manipulator.add_module(modules, new_mod, position=0)
        assert len(result) == len(modules) + 1
        assert result[0]["id"] == "new_mod"
        valid_script["modules"] = result
        _check_valid(validator, valid_script, "after add_module at position 0")

    def test_remove_module_by_id(self, manipulator, validator, valid_script):
        modules = deepcopy(valid_script["modules"])
        # Remove the second module
        target_id = modules[1]["id"]
        result = manipulator.remove_module(modules, target_id)
        assert len(result) == len(modules) - 1
        assert target_id not in [m["id"] for m in result]

    def test_remove_nonexistent_returns_unchanged(self, manipulator, valid_script):
        modules = deepcopy(valid_script["modules"])
        result = manipulator.remove_module(modules, "nonexistent_id")
        assert len(result) == len(modules)

    def test_reorder_modules(self, manipulator, validator, valid_script):
        modules = deepcopy(valid_script["modules"])
        if len(modules) < 2:
            pytest.skip("Need ≥2 modules to test reorder")
        # Move first module to end (swap via reorder)
        first_id = modules[0]["id"]
        result = manipulator.reorder(modules, first_id, len(modules) - 1)
        assert result[-1]["id"] == first_id
        valid_script["modules"] = result
        _check_valid(validator, valid_script, "after reorder")

    def test_duplicate_module(self, manipulator, validator, valid_script):
        modules = deepcopy(valid_script["modules"])
        if not modules:
            pytest.skip("Need ≥1 module to duplicate")
        target_id = modules[0]["id"]
        result_list, new_id = manipulator.duplicate_module(modules, target_id)
        assert new_id is not None
        assert len(result_list) == len(modules) + 1
        # Duplicated module should have a different id
        ids = [m["id"] for m in result_list]
        assert ids.count(target_id) == 1  # original still there once
        assert len(ids) == len(set(ids))  # all unique

    def test_shift_all_modules(self, manipulator, validator, valid_script):
        modules = deepcopy(valid_script["modules"])
        offset = 2.0
        result = manipulator.shift_all_modules(modules, offset)
        for m in result:
            assert m["start_time"] >= offset
        valid_script["modules"] = result
        _check_valid(validator, valid_script, "after shift_all")

    def test_compact_timeline(self, manipulator, validator, valid_script):
        """Compact should remove gaps (if gap exists) or keep unchanged."""
        modules = deepcopy(valid_script["modules"])
        result = manipulator.compact_timeline(modules)
        assert len(result) == len(modules)
        # All start_times should be non-negative and in order
        times = [m["start_time"] for m in result]
        assert all(t >= 0 for t in times)
        assert times == sorted(times)
        valid_script["modules"] = result
        _check_valid(validator, valid_script, "after compact")

    def test_chain_operations_stay_valid(self, manipulator, validator, valid_script):
        """Multiple operations in sequence should keep script valid."""
        modules = deepcopy(valid_script["modules"])

        # Chain: add → duplicate → remove → shift → compact
        new_mod = {"id": "chain_test", "type": "transition", "start_time": 0.0,
                   "duration": 0.5, "track_index": 0}
        modules = manipulator.add_module(modules, new_mod, position=0)
        modules, _ = manipulator.duplicate_module(modules, modules[1]["id"])
        modules = manipulator.remove_module(modules, "chain_test")
        modules = manipulator.shift_all_modules(modules, 1.0)
        modules = manipulator.compact_timeline(modules)

        # compact_timeline removes gaps but doesn't reorder;
        # verify all start_times are non-negative
        for m in modules:
            assert m["start_time"] >= 0

        valid_script["modules"] = modules
        _check_valid(validator, valid_script, "after chain")
