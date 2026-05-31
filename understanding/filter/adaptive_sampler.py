"""Adaptive keyframe sampler based on frame-difference curve and scene boundaries.

Implements the adaptive sampling strategy: sparse in flat regions (interviews,
lectures), dense in high-activity regions (fast cuts, motion), with boundary
frames captured on both sides of transitions.

Performance note: The percentile threshold computation uses ``sorted()`` on the
full diff_curve list.  For very long videos (2+ hours at high fps) the diff
curve may contain 200k+ values; ``sorted()`` handles this scale acceptably in
pure Python (~20-50 ms) but could be replaced with ``numpy.percentile()`` if
sub-millisecond performance is required.
"""

from typing import Any, Dict, List


class AdaptiveSampler:
    """Samples keyframes adaptively based on frame-difference intensity.

    The sampler uses a percentile-based threshold on the diff curve to
    distinguish high-activity from low-activity segments, then applies
    different sampling intervals accordingly.

    When the diff curve is essentially flat (e.g. static-camera lecture
    videos), percentile-based thresholding is meaningless --- use
    :meth:`sample_by_count` instead, which detects flatness and falls
    back to uniform sampling.

    Attributes:
        percentile_threshold: Percentile of diff curve used as high-activity
            threshold (default 75).
        dense_interval: Sampling interval in dense regions (default 5 frames).
        sparse_interval: Sampling interval in sparse regions (default 30 frames).
        boundary_margin: Frames to capture on each side of a boundary (default 1).
    """

    def __init__(
        self,
        percentile_threshold: float = 75.0,
        dense_interval: int = 5,
        sparse_interval: int = 30,
        boundary_margin: int = 1,
    ) -> None:
        self.percentile_threshold = percentile_threshold
        self.dense_interval = dense_interval
        self.sparse_interval = sparse_interval
        self.boundary_margin = boundary_margin

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_boundary_frames(
        self, scene_boundaries: List[float], fps: float, n_frames: int
    ) -> set:
        """Return set of frame indices within boundary_margin of each boundary.

        Uses ``round()`` (not ``int()``) for timestamp-to-frame conversion to
        avoid off-by-one errors from floating-point imprecision (e.g. ``5.0 *
        30`` may be ``149.999...`` internally).

        Args:
            scene_boundaries: Boundary timestamps in seconds.
            fps: Frames per second.
            n_frames: Total number of frames in the video.

        Returns:
            Set of frame indices that fall within ``boundary_margin`` of any
            scene boundary.
        """
        frames: set = set()
        for boundary_time in scene_boundaries:
            boundary_frame = round(boundary_time * fps)
            for offset in range(-self.boundary_margin, self.boundary_margin + 1):
                frame_idx = boundary_frame + offset
                if 0 <= frame_idx < n_frames:
                    frames.add(frame_idx)
        return frames

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sample(
        self,
        diff_curve: List[float],
        scene_boundaries: List[float],
        fps: float,
    ) -> List[int]:
        """Determine keyframe indices using diff curve and scene boundaries.

        Strategy:
        1. Compute threshold as Nth percentile of diff_curve.
        2. Walk through frames; if diff > threshold, mark as dense region.
        3. In dense regions, sample every dense_interval frames.
        4. In sparse regions, sample every sparse_interval frames.
        5. Around each scene boundary, force-capture boundary_margin frames
           before and after the boundary timestamp.

        Edge cases:
        - Empty *diff_curve* (0 or 1 frame): returns ``[]``.
        - All-zero diff curve: threshold == 0, so ``max(prev, next) > 0`` is
          False for every frame, and every position is treated as sparse.
        - *scene_boundaries* timestamps outside ``[0, duration]`` are safely
          clamped by the ``0 <= frame_idx < n_frames`` guard in
          :meth:`_get_boundary_frames`.

        Args:
            diff_curve: Frame-difference values (len = total_frames - 1).
            scene_boundaries: Candidate boundary timestamps in seconds.
            fps: Frames per second of the source video.

        Returns:
            Sorted list of unique frame indices (0-based) to sample.
        """
        if not diff_curve:
            return []

        n_frames = len(diff_curve) + 1  # diff_curve[i] sits between frame i and i+1

        # Percentile threshold via explicit sort (see module docstring for
        # numpy alternative on very large diff curves).
        sorted_diffs = sorted(diff_curve)
        idx = int(len(sorted_diffs) * self.percentile_threshold / 100.0)
        idx = min(idx, len(sorted_diffs) - 1)
        threshold = sorted_diffs[idx] if sorted_diffs else 0.0

        # Walk frames: at each position peek at the local diff value to
        # decide whether to use the dense or sparse jump interval.
        keyframes: set = set()
        i = 0
        while i < n_frames:
            # Frame *i* sits between diff_curve[i-1] (before) and
            # diff_curve[i] (after).  Clamp edge frames to 0.0.
            prev_diff = diff_curve[i - 1] if i > 0 else 0.0
            next_diff = diff_curve[i] if i < len(diff_curve) else 0.0
            is_dense = max(prev_diff, next_diff) > threshold

            keyframes.add(i)
            interval = self.dense_interval if is_dense else self.sparse_interval
            i += interval

        # Force-add boundary frames (boundary itself plus margin on each side).
        keyframes.update(
            self._get_boundary_frames(scene_boundaries, fps, n_frames)
        )

        return sorted(keyframes)

    def sample_by_count(
        self,
        diff_curve: List[float],
        scene_boundaries: List[float],
        fps: float,
        target_count: int,
        flat_tolerance: float = 0.05,
    ) -> List[int]:
        """Sample keyframes targeting a specific count, with flat-curve fallback.

        When the diff curve is essentially flat (all values within
        *flat_tolerance* relative to the maximum), percentile-based
        thresholding is meaningless.  In that case this method falls back
        to uniform sampling that evenly distributes *target_count* frames
        across the timeline.

        Otherwise it delegates to :meth:`sample` (adaptive sampling).

        Args:
            diff_curve: Frame-difference values.
            scene_boundaries: Candidate boundary timestamps in seconds.
            fps: Frames per second.
            target_count: Desired number of keyframes.  If *target_count*
                exceeds the total number of frames every frame is returned.
                Non-positive values return an empty list.
            flat_tolerance: Relative tolerance for flatness detection
                (default 0.05, i.e. 5 %).

        Returns:
            Sorted list of unique frame indices (0-based).
        """
        if not diff_curve:
            return []

        if target_count <= 0:
            return []

        n_frames = len(diff_curve) + 1

        # ---- detect flat curve ----
        max_diff = max(diff_curve)
        min_diff = min(diff_curve)
        # Relative range: (max-min) / max, with guard against zero max.
        is_flat = (max_diff - min_diff) <= flat_tolerance * max(max_diff, 1e-9)

        if is_flat:
            if target_count >= n_frames:
                keyframes: set = set(range(n_frames))
            else:
                step = (n_frames - 1) / max(target_count - 1, 1)
                keyframes = {round(i * step) for i in range(target_count)}
                # Clamp rounding results to valid range.
                keyframes = {k for k in keyframes if 0 <= k < n_frames}
        else:
            keyframes = set(self.sample(diff_curve, scene_boundaries, fps))

        # Always force-include boundary frames.
        keyframes.update(
            self._get_boundary_frames(scene_boundaries, fps, n_frames)
        )

        return sorted(keyframes)

    def sample_with_context(
        self,
        diff_curve: List[float],
        scene_boundaries: List[float],
        fps: float,
    ) -> List[Dict[str, Any]]:
        """Sample keyframes and return each with timestamp and signal context.

        Each returned dict contains:

        - ``frame_index`` (int): 0-based frame number.
        - ``timestamp`` (float): time in seconds (``frame_index / fps``).
        - ``diff_value`` (float): frame-difference value at this index.
        - ``is_boundary`` (bool): True if this frame lies within the
          boundary margin of a scene cut.

        The last frame of the video has no corresponding *diff_curve*
        entry (since ``len(diff_curve) == total_frames - 1``), so its
        ``diff_value`` is reported as ``0.0``.

        Args:
            diff_curve: Frame-difference values.
            scene_boundaries: Candidate boundary timestamps in seconds.
            fps: Frames per second of the source video.

        Returns:
            List of dicts, one per sampled keyframe.
        """
        keyframe_indices = self.sample(diff_curve, scene_boundaries, fps)

        n_frames = len(diff_curve) + 1
        boundary_frames = self._get_boundary_frames(scene_boundaries, fps, n_frames)

        result: List[Dict[str, Any]] = []
        for idx in keyframe_indices:
            diff_val = diff_curve[idx] if idx < len(diff_curve) else 0.0
            result.append({
                "frame_index": idx,
                "timestamp": idx / fps,
                "diff_value": float(diff_val),
                "is_boundary": idx in boundary_frames,
            })

        return result
