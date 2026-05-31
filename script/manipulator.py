"""Script manipulator: CRUD operations on the module tree.

Provides add, remove, reorder, duplicate, time-shift, and compact
operations that maintain timeline consistency.
"""

import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


class ScriptManipulator:
    """Performs manipulation operations on MigratableScript module arrays.

    All operations return a new copy of the modules list; the original
    is not mutated in place.
    """

    # ------------------------------------------------------------------
    # Basic CRUD
    # ------------------------------------------------------------------

    def add_module(
        self,
        modules: List[Dict[str, Any]],
        new_module: Dict[str, Any],
        position: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Insert a new module at the specified position.

        Args:
            modules: Current list of modules.
            new_module: Module dict to insert.
            position: Index at which to insert. Defaults to end of list.

        Returns:
            New modules list with the module inserted.
        """
        result = deepcopy(modules)
        if position is None or position >= len(result):
            result.append(deepcopy(new_module))
        else:
            result.insert(max(0, position), deepcopy(new_module))
        return result

    def remove_module(
        self,
        modules: List[Dict[str, Any]],
        module_id: str,
        compact: bool = False,
    ) -> List[Dict[str, Any]]:
        """Remove a module by its id.

        Args:
            modules: Current list of modules.
            module_id: The id of the module to remove.
            compact: If True, shift downstream modules on the same track
                backward to close the gap left by the removed module.

        Returns:
            New modules list with the module removed.
        """
        result = [deepcopy(m) for m in modules if m.get("id") != module_id]

        if compact and len(result) < len(modules):
            removed = next(
                (m for m in modules if m.get("id") == module_id), None
            )
            if removed is not None:
                result = self._compact_track(
                    result,
                    removed.get("track_index", 0),
                    removed.get("start_time", 0.0),
                    removed.get("duration", 0.0),
                )

        return result

    def reorder(
        self,
        modules: List[Dict[str, Any]],
        module_id: str,
        new_position: int,
    ) -> List[Dict[str, Any]]:
        """Move a module to a new position in the list.

        Args:
            modules: Current list of modules.
            module_id: The id of the module to move.
            new_position: Target index (0-based). Clamped to valid range.

        Returns:
            New modules list with the module repositioned.
        """
        result = deepcopy(modules)
        # Find the module
        target_idx: Optional[int] = None
        target_module: Optional[Dict[str, Any]] = None
        for i, m in enumerate(result):
            if m.get("id") == module_id:
                target_idx = i
                target_module = m
                break

        if target_idx is None:
            return result

        # Remove from current position
        result.pop(target_idx)

        # Insert at new position (recalculate index after removal)
        insert_pos = max(0, min(new_position, len(result)))
        result.insert(insert_pos, deepcopy(target_module))

        return result

    def update_param(
        self,
        modules: List[Dict[str, Any]],
        module_id: str,
        param_name: str,
        param_value: Any,
    ) -> List[Dict[str, Any]]:
        """Update a single parameter of a module.

        Args:
            modules: Current list of modules.
            module_id: The id of the module to update.
            param_name: Dot-separated path to the parameter
                (e.g. ``"params.font_size"``, ``"source.path"``).
            param_value: New value to set.

        Returns:
            New modules list with the parameter updated.
        """
        result = deepcopy(modules)
        for m in result:
            if m.get("id") == module_id:
                self._set_nested(m, param_name.split("."), param_value)
                break
        return result

    # ------------------------------------------------------------------
    # Bulk / convenience operations
    # ------------------------------------------------------------------

    def duplicate_module(
        self,
        modules: List[Dict[str, Any]],
        module_id: str,
        new_id: Optional[str] = None,
        time_offset: float = 0.0,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Duplicate an existing module.

        The copy is placed immediately after the original in the module
        list.  Its ``start_time`` is optionally shifted by *time_offset*.

        Args:
            modules: Current list of modules.
            module_id: The id of the module to duplicate.
            new_id: Id for the duplicated module.  Auto-generated when
                omitted.
            time_offset: Seconds to add to the copy's ``start_time``
                (useful for placing it after the original on the
                timeline).

        Returns:
            Tuple of ``(new_modules_list, new_module_id)``.  If the
            source module is not found the original list is returned
            unchanged and *new_module_id* is ``None``.
        """
        result = deepcopy(modules)

        target_idx: Optional[int] = None
        for i, m in enumerate(result):
            if m.get("id") == module_id:
                target_idx = i
                break

        if target_idx is None:
            return result, None

        clone = deepcopy(result[target_idx])
        assigned_id = new_id or self._make_id()
        clone["id"] = assigned_id

        if "start_time" in clone:
            clone["start_time"] = max(0.0, clone["start_time"] + time_offset)

        # Insert right after the original
        result.insert(target_idx + 1, clone)
        return result, assigned_id

    def shift_all_modules(
        self,
        modules: List[Dict[str, Any]],
        offset_seconds: float,
    ) -> List[Dict[str, Any]]:
        """Shift every module's start time by a fixed offset.

        This is a bulk operation useful for inserting or removing time
        at the very beginning of the timeline (e.g. adding a global
        intro clip).

        Args:
            modules: Current list of modules.
            offset_seconds: Seconds to add to every module's
                ``start_time`` (positive = later, negative = earlier).

        Returns:
            New modules list with all start times shifted.  Start times
            are clamped to a minimum of 0.0.
        """
        result = deepcopy(modules)
        for m in result:
            if "start_time" in m:
                m["start_time"] = max(0.0, m["start_time"] + offset_seconds)
        return result

    def shift_timeline(
        self,
        modules: List[Dict[str, Any]],
        after_module_id: str,
        offset_seconds: float,
    ) -> List[Dict[str, Any]]:
        """Shift all modules *after* a given module by an offset.

        Useful when a module's duration changes and downstream modules
        need to be nudged forward or backward.

        Args:
            modules: Current list of modules.
            after_module_id: Id of the module after which to shift.
            offset_seconds: Time to add (positive = forward, negative =
                backward).

        Returns:
            New modules list with shifted start times.
        """
        result = deepcopy(modules)
        shift = False
        for m in result:
            if shift and "start_time" in m:
                m["start_time"] = max(0.0, m["start_time"] + offset_seconds)
            if m.get("id") == after_module_id:
                shift = True
        return result

    def compact_timeline(
        self, modules: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove gaps between consecutive modules on each track.

        Modules on each track are sorted by ``start_time`` and then
        shifted so that each module begins exactly where the previous
        one ends, producing a gapless sequence per track.

        Args:
            modules: Current list of modules.

        Returns:
            New modules list with gapless timelines per track.
        """
        result = deepcopy(modules)

        # Group by track
        by_track: Dict[int, List[Dict[str, Any]]] = {}
        for m in result:
            ti = m.get("track_index", 0)
            by_track.setdefault(ti, []).append(m)

        for _track_idx, tmods in by_track.items():
            tmods.sort(key=lambda m: m.get("start_time", 0.0))
            cursor = 0.0
            for m in tmods:
                m["start_time"] = cursor
                cursor += m.get("duration", 0.0)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_id() -> str:
        """Generate a short unique id string."""
        return f"mod_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _set_nested(obj: Dict[str, Any], path: List[str], value: Any) -> None:
        """Set a value in a nested dict by key path."""
        for key in path[:-1]:
            if key not in obj:
                obj[key] = {}
            obj = obj[key]
        obj[path[-1]] = value

    @staticmethod
    def _compact_track(
        modules: List[Dict[str, Any]],
        track_index: int,
        removed_start: float,
        removed_duration: float,
    ) -> List[Dict[str, Any]]:
        """Shift modules on *track_index* that start after *removed_start*
        backward by *removed_duration* seconds."""
        gap = removed_duration
        for m in modules:
            if (
                m.get("track_index") == track_index
                and m.get("start_time", 0.0) > removed_start
            ):
                m["start_time"] = max(0.0, m["start_time"] - gap)
        return modules
