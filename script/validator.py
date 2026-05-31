"""Script validator: integrity checks on MigratableScript JSON.

Validates timeline continuity, track conflicts, missing references,
duration consistency, and duplicate IDs.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

import jsonschema


class ScriptValidator:
    """Validates MigratableScript JSON against schema and integrity rules.

    Runs five integrity checks in addition to JSON Schema validation:

    1. **Timeline continuity** — gaps or overlaps between consecutive
       modules on the same track.
    2. **Track conflicts** — any overlapping modules on the same track
       (all-pairs scan).
    3. **Missing references** — modules referencing undefined track
       indices.
    4. **Duration consistency** — declared ``total_duration`` vs. the
       actual timeline end.
    5. **Duplicate IDs** — modules that share the same ``id`` field.

    Attributes:
        schema: JSON Schema dict loaded from :mod:`script.schema`.
    """

    def __init__(self, schema: Dict[str, Any]) -> None:
        self.schema = schema

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, script: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Run full validation: schema + five integrity checks.

        Args:
            script: MigratableScript dict to validate.

        Returns:
            List of issue dicts, each with:
                - ``severity``: ``"error"`` | ``"warning"``
                - ``message``: Human-readable description
                - ``path``: Dot-notation path to the problematic field
                - ``module_id`` (optional): id of the affected module
                - ``module_index`` (optional): list-index of the module
                  in the ``modules`` array
                - ``track_index`` (optional): track where the issue
                  was detected
            Empty list means the script is fully valid.
        """
        issues: List[Dict[str, Any]] = []

        # -- Schema validation -----------------------------------------
        schema_issues = self._validate_schema(script)
        issues.extend(schema_issues)

        if schema_issues:
            # Don't run integrity checks if schema is broken
            return issues

        # -- Integrity checks ------------------------------------------
        issues.extend(self._check_timeline_continuity(script))
        issues.extend(self._check_track_conflicts(script))
        issues.extend(self._check_missing_references(script))
        issues.extend(self._check_duration_consistency(script))
        issues.extend(self._check_duplicate_ids(script))

        return issues

    def is_valid(self, script: Dict[str, Any]) -> bool:
        """Check if script passes all validation rules.

        Args:
            script: MigratableScript dict.

        Returns:
            ``True`` if no errors found.
        """
        issues = self.validate(script)
        return not any(i["severity"] == "error" for i in issues)

    # ------------------------------------------------------------------
    # Schema validation
    # ------------------------------------------------------------------

    def _validate_schema(self, script: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Validate against the JSON Schema definition."""
        issues: List[Dict[str, Any]] = []
        try:
            jsonschema.validate(instance=script, schema=self.schema)
        except jsonschema.ValidationError as e:
            issues.append({
                "severity": "error",
                "message": e.message,
                "path": ".".join(str(p) for p in e.absolute_path),
            })
        except jsonschema.SchemaError as e:
            issues.append({
                "severity": "error",
                "message": f"Schema error: {e.message}",
                "path": "$schema",
            })
        return issues

    # ------------------------------------------------------------------
    # Integrity checks
    # ------------------------------------------------------------------

    def _check_timeline_continuity(
        self, script: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check that consecutive modules on each track have no gaps or
        overlaps in their start/end times."""
        issues: List[Dict[str, Any]] = []
        modules: List[Dict[str, Any]] = script.get("modules", [])
        if not modules:
            return issues

        # Build index lookup for reporting
        idx_map: Dict[str, int] = {
            m["id"]: i for i, m in enumerate(modules) if "id" in m
        }

        # Group by track
        tracks: Dict[int, List[Dict[str, Any]]] = {}
        for m in modules:
            track_idx = m.get("track_index", 0)
            tracks.setdefault(track_idx, []).append(m)

        for track_idx, track_modules in tracks.items():
            sorted_mods = sorted(
                track_modules, key=lambda m: m.get("start_time", 0.0)
            )
            for i in range(len(sorted_mods) - 1):
                curr = sorted_mods[i]
                nxt = sorted_mods[i + 1]
                curr_end = curr["start_time"] + curr["duration"]
                next_start = nxt["start_time"]

                delta = next_start - curr_end

                if abs(delta) > 0.01:  # floating-point tolerance
                    if delta < 0:
                        severity = "error"
                        detail = (
                            f"overlap of {abs(delta):.2f}s between "
                            f"'{curr.get('id')}' and '{nxt.get('id')}'"
                        )
                    else:
                        severity = "warning"
                        detail = (
                            f"gap of {delta:.2f}s between "
                            f"'{curr.get('id')}' and '{nxt.get('id')}'"
                        )

                    issues.append({
                        "severity": severity,
                        "message": f"Track {track_idx}: {detail}",
                        "path": f"modules.{curr.get('id')}",
                        "module_id": curr.get("id"),
                        "module_index": idx_map.get(curr.get("id", "")),
                        "track_index": track_idx,
                    })

        return issues

    def _check_track_conflicts(
        self, script: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check for any overlapping modules on the same track (all-pairs
        scan — catches overlaps between non-consecutive modules as well)."""
        issues: List[Dict[str, Any]] = []
        modules: List[Dict[str, Any]] = script.get("modules", [])

        idx_map: Dict[str, int] = {
            m["id"]: i for i, m in enumerate(modules) if "id" in m
        }

        # Group by track
        tracks: Dict[int, List[Dict[str, Any]]] = {}
        for m in modules:
            track_idx = m.get("track_index", 0)
            tracks.setdefault(track_idx, []).append(m)

        for track_idx, track_modules in tracks.items():
            for i in range(len(track_modules)):
                for j in range(i + 1, len(track_modules)):
                    a = track_modules[i]
                    b = track_modules[j]
                    a_end = a["start_time"] + a["duration"]
                    b_end = b["start_time"] + b["duration"]

                    if a["start_time"] < b_end and b["start_time"] < a_end:
                        issues.append({
                            "severity": "error",
                            "message": (
                                f"Track {track_idx}: overlap between "
                                f"'{a.get('id')}' and '{b.get('id')}'"
                            ),
                            "path": f"modules.{a.get('id')}",
                            "module_id": a.get("id"),
                            "module_index": idx_map.get(a.get("id", "")),
                            "track_index": track_idx,
                        })

        return issues

    def _check_missing_references(
        self, script: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check for modules that reference undefined track indices."""
        issues: List[Dict[str, Any]] = []
        modules: List[Dict[str, Any]] = script.get("modules", [])
        tracks: List[Dict[str, Any]] = script.get("tracks", [])

        idx_map: Dict[str, int] = {
            m["id"]: i for i, m in enumerate(modules) if "id" in m
        }

        # Build set of valid track indices
        valid_tracks: set = {t["index"] for t in tracks if "index" in t}
        # If no tracks are explicitly defined, track 0 is implicitly valid
        if not valid_tracks:
            valid_tracks = {0}

        for m in modules:
            ti = m.get("track_index")
            if ti is not None and ti not in valid_tracks:
                issues.append({
                    "severity": "warning",
                    "message": (
                        f"Module '{m.get('id')}' references undefined "
                        f"track {ti}"
                    ),
                    "path": f"modules.{m.get('id')}.track_index",
                    "module_id": m.get("id"),
                    "module_index": idx_map.get(m.get("id", "")),
                    "track_index": ti,
                })

        return issues

    def _check_duration_consistency(
        self, script: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check that total_duration matches the actual timeline span."""
        issues: List[Dict[str, Any]] = []
        modules: List[Dict[str, Any]] = script.get("modules", [])
        declared_duration = script.get("metadata", {}).get("total_duration", 0.0)

        if not modules:
            return issues

        actual_end = max(
            m["start_time"] + m["duration"] for m in modules
        )

        diff = abs(actual_end - declared_duration)
        if diff > 0.1:
            issues.append({
                "severity": "warning",
                "message": (
                    f"Declared total_duration ({declared_duration:.1f}s) "
                    f"differs from actual timeline end ({actual_end:.1f}s)"
                ),
                "path": "metadata.total_duration",
            })

        return issues

    def _check_duplicate_ids(
        self, script: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check for modules that share the same ``id`` field.

        Duplicate ids break module-level operations in
        :class:`ScriptManipulator` and indicate a data-integrity problem.
        """
        issues: List[Dict[str, Any]] = []
        modules: List[Dict[str, Any]] = script.get("modules", [])

        seen: Dict[str, int] = {}  # id -> first occurrence index
        for i, m in enumerate(modules):
            mid = m.get("id")
            if mid is None:
                continue
            if mid in seen:
                issues.append({
                    "severity": "error",
                    "message": (
                        f"Duplicate module id '{mid}' at indices "
                        f"{seen[mid]} and {i}"
                    ),
                    "path": f"modules[{i}].id",
                    "module_id": mid,
                    "module_index": i,
                })
            else:
                seen[mid] = i

        return issues

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    @staticmethod
    def from_file(
        script_path: str, schema: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Load and validate a script JSON file.

        Args:
            script_path: Path to the script JSON file.
            schema: JSON Schema dict.

        Returns:
            Tuple of ``(script_dict, issues_list)``.
        """
        with open(script_path, "r", encoding="utf-8") as f:
            script = json.load(f)

        validator = ScriptValidator(schema)
        issues = validator.validate(script)
        return script, issues
