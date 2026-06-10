"""Deconstructor — multi-dimension video analysis scheduler.

Orchestrates independent extractors (shot rhythm, …) over signal data.
Each dimension runs in isolation; failures are isolated and produce
empty results so the full schema is always delivered.
"""

import logging
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)


class Deconstructor:
    """Run post-pipeline deconstruction dimensions on signal data.

    Each dimension is lazy-loaded on first call and recovered from
    exceptions independently — one dimension failing never blocks others.

    Dimensions (registered):
        - shot_rhythm      scene-boundary pacing + motion intensity
    """

    def __init__(self) -> None:
        self._shot_rhythm: Any = None
        self._subtitle_style: Any = None
        self._visual_packaging: Any = None
        self._transition_pattern: Any = None
        self._music_sync: Any = None

    # ── Public API ─────────────────────────────────────────────────

    def deconstruct(
        self,
        signal_data: Dict[str, Any],
        structure_segments: Optional[List[Dict[str, Any]]] = None,
        keyframes: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Run all registered deconstruction dimensions.

        Args:
            signal_data: Full pipeline signal-layer output.
            structure_segments: Structure inferrer output.
            keyframes: Sampled keyframe metadata.

        Returns:
            Dict with one key per dimension (e.g. "shot_rhythm").
            Failed dimensions contain empty placeholder dicts.
        """
        return {
            "shot_rhythm": self._run_shot_rhythm(
                signal_data, structure_segments, keyframes,
            ),
            "subtitle_style": self._run_subtitle_style(
                signal_data, structure_segments, keyframes,
            ),
            "visual_packaging": self._run_visual_packaging(
                signal_data, structure_segments, keyframes,
            ),
            "transition_pattern": self._run_transition_pattern(
                signal_data, structure_segments, keyframes,
            ),
            "music_sync": self._run_music_sync(
                signal_data, structure_segments, keyframes,
            ),
        }

    # ── Dimension runners ──────────────────────────────────────────

    def _run_shot_rhythm(
        self,
        signal_data: Dict[str, Any],
        structure_segments: Optional[List[Dict[str, Any]]],
        keyframes: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if self._shot_rhythm is None:
            try:
                from understanding.deconstruction.shot_rhythm import extract
                self._shot_rhythm = extract
            except Exception as exc:
                _log.warning("shot_rhythm import failed: %s", exc)
                self._shot_rhythm = False

        if self._shot_rhythm is False:
            return {}

        try:
            return self._shot_rhythm(signal_data, structure_segments, keyframes)
        except Exception as exc:
            _log.warning("shot_rhythm extraction failed: %s", exc)
            return {}

    def _run_subtitle_style(
        self,
        signal_data: Dict[str, Any],
        structure_segments: Optional[List[Dict[str, Any]]],
        keyframes: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if self._subtitle_style is None:
            try:
                from understanding.deconstruction.subtitle_style import extract
                self._subtitle_style = extract
            except Exception as exc:
                _log.warning("subtitle_style import failed: %s", exc)
                self._subtitle_style = False

        if self._subtitle_style is False:
            return {"available": False}

        try:
            return self._subtitle_style(signal_data, structure_segments, keyframes)
        except Exception as exc:
            _log.warning("subtitle_style extraction failed: %s", exc)
            return {"available": False}

    def _run_visual_packaging(
        self,
        signal_data: Dict[str, Any],
        structure_segments: Optional[List[Dict[str, Any]]],
        keyframes: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if self._visual_packaging is None:
            try:
                from understanding.deconstruction.visual_packaging import extract
                self._visual_packaging = extract
            except Exception as exc:
                _log.warning("visual_packaging import failed: %s", exc)
                self._visual_packaging = False

        if self._visual_packaging is False:
            return {"available": False}

        try:
            return self._visual_packaging(signal_data, structure_segments, keyframes)
        except Exception as exc:
            _log.warning("visual_packaging extraction failed: %s", exc)
            return {"available": False}

    def _run_transition_pattern(
        self,
        signal_data: Dict[str, Any],
        structure_segments: Optional[List[Dict[str, Any]]],
        keyframes: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if self._transition_pattern is None:
            try:
                from understanding.deconstruction.transition_pattern import extract
                self._transition_pattern = extract
            except Exception as exc:
                _log.warning("transition_pattern import failed: %s", exc)
                self._transition_pattern = False
        if self._transition_pattern is False:
            return {"available": False}
        try:
            return self._transition_pattern(signal_data, structure_segments, keyframes)
        except Exception as exc:
            _log.warning("transition_pattern failed: %s", exc)
            return {"available": False}

    def _run_music_sync(
        self,
        signal_data: Dict[str, Any],
        structure_segments: Optional[List[Dict[str, Any]]],
        keyframes: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if self._music_sync is None:
            try:
                from understanding.deconstruction.music_sync import extract
                self._music_sync = extract
            except Exception as exc:
                _log.warning("music_sync import failed: %s", exc)
                self._music_sync = False
        if self._music_sync is False:
            return {"available": False}
        try:
            return self._music_sync(signal_data, structure_segments, keyframes)
        except Exception as exc:
            _log.warning("music_sync failed: %s", exc)
            return {"available": False}


class EmptyDeconstruction:
    """Return fallback placeholder dicts for the full Deconstructor schema.

    Used when the Deconstructor itself can't be loaded.
    """

    @staticmethod
    def deconstruct(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        from understanding.deconstruction.shot_rhythm import _empty_result
        return {"shot_rhythm": _empty_result()}
