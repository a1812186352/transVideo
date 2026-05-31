"""Script builder: constructs a MigratableScript JSON from structured modules.

Takes a module tree (list of Module dicts) and metadata, assembles the
complete script JSON, and can write it to disk.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


class ScriptBuilder:
    """Builds a MigratableScript JSON from module tree and metadata.

    Attributes:
        version: Schema version string (default '1.0.0').
    """

    def __init__(self, version: str = "1.0.0") -> None:
        self.version = version
        self._id_counter: int = 0

    # ------------------------------------------------------------------
    # ID utilities
    # ------------------------------------------------------------------

    def generate_id(self, prefix: str = "mod") -> str:
        """Generate a unique module identifier.

        Each call increments an internal counter, guaranteeing uniqueness
        within a builder instance.

        Args:
            prefix: Prefix for the ID string.

        Returns:
            A unique ID string such as ``"mod_0001"``.
        """
        self._id_counter += 1
        return f"{prefix}_{self._id_counter:04d}"

    def ensure_unique_ids(
        self, modules: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Ensure every module in the list has a unique ``id`` field.

        Modules missing an id or sharing an id with another module are
        assigned a freshly generated id.

        Args:
            modules: List of module dicts (may be mutated in place).

        Returns:
            The same list with guaranteed unique ids.
        """
        seen: Set[str] = set()
        for m in modules:
            mid = m.get("id", "")
            if not mid or mid in seen:
                m["id"] = self.generate_id()
            seen.add(m["id"])
        return modules

    # ------------------------------------------------------------------
    # Script factories
    # ------------------------------------------------------------------

    def create_empty_script(
        self,
        title: str = "Untitled Project",
        description: str = "",
        author: str = "",
        total_duration: float = 0.0,
        fps: float = 30.0,
        resolution: Optional[Dict[str, int]] = None,
        tags: Optional[List[str]] = None,
        tracks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create a minimal script dict with no modules.

        This is a convenience entry-point for scripts that will be
        populated incrementally via :class:`ScriptManipulator`.  Note
        that the JSON Schema enforces ``minItems: 1`` on the modules
        array, so the returned dict is structurally valid but not yet
        schema-valid until at least one module is added.

        Args:
            title: Project title.
            description: Project description.
            author: Author name.
            total_duration: Total project duration in seconds.
            fps: Frames per second.
            resolution: Dict with ``"width"`` and ``"height"`` keys.
            tags: List of tag strings.
            tracks: List of Track dicts.

        Returns:
            A :class:`dict` representing a MigratableScript with an
            empty modules array.
        """
        if resolution is None:
            resolution = {"width": 1920, "height": 1080}

        return {
            "version": self.version,
            "metadata": {
                "title": title,
                "description": description,
                "author": author,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "total_duration": total_duration,
                "source_video_id": "",
                "fps": fps,
                "resolution": resolution,
                "tags": tags or [],
            },
            "modules": [],
            "tracks": tracks or [],
        }

    def from_module_tree(
        self,
        modules: List[Dict[str, Any]],
        title: str = "Untitled Project",
        description: str = "",
        author: str = "",
        total_duration: float = 0.0,
        fps: float = 30.0,
        resolution: Optional[Dict[str, int]] = None,
        source_video_id: str = "",
        tags: Optional[List[str]] = None,
        tracks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Assemble a complete script from a list of modules.

        Empty *modules* lists are accepted but will cause schema
        validation to fail (``minItems: 1``).  Callers that intend to
        build a valid script should supply at least one module.

        Duplicate or missing module ids are repaired before assembly so
        that every module is guaranteed to have a unique identifier.

        Args:
            modules: List of Module dicts conforming to the JSON Schema.
            title: Project title.
            description: Project description.
            author: Author name.
            total_duration: Total project duration in seconds.
            fps: Frames per second.
            resolution: Dict with ``"width"`` and ``"height"`` keys.
            source_video_id: ID of the source video.
            tags: List of tag strings.
            tracks: List of Track dicts.

        Returns:
            Complete MigratableScript dict.
        """
        if resolution is None:
            resolution = {"width": 1920, "height": 1080}

        # Normalise ids so callers never need to worry about collisions.
        sanitized = self.ensure_unique_ids(list(modules))

        script: Dict[str, Any] = {
            "version": self.version,
            "metadata": {
                "title": title,
                "description": description,
                "author": author,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "total_duration": total_duration,
                "source_video_id": source_video_id,
                "fps": fps,
                "resolution": resolution,
                "tags": tags or [],
            },
            "modules": sanitized,
            "tracks": tracks or [],
        }

        return script

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_file(self, script: Dict[str, Any], path: str) -> None:
        """Write a script dict to a JSON file.

        Args:
            script: Complete MigratableScript dict.
            path: Output file path.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(script, f, indent=2, ensure_ascii=False)

    def to_string(self, script: Dict[str, Any]) -> str:
        """Serialize a script dict to a JSON string.

        Args:
            script: Complete MigratableScript dict.

        Returns:
            JSON string.
        """
        return json.dumps(script, indent=2, ensure_ascii=False)
