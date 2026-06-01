"""Content-based keyframe sampler — second channel alongside frame-diff.

Captures *informative static frames* (LOGO endings, title cards, white-background
text screens) that the diff-based percentile sampler misses because they have
near-zero frame-to-frame difference.

Logic:
    Every ``interval_sec`` (default 5) seconds, extract one frame, compute its
    Shannon entropy (grayscale histogram) and Canny edge density.  If the frame
    has enough visual information (entropy > threshold) but is visually simple
    (edge_density < threshold), it is included as a content-representative keyframe.

These frames are later merged with diff-based keyframes in the pipeline orchestrator.
"""

import os
from typing import Any, Dict, List

import cv2
import numpy as np


# ── Configurable defaults (override via pipeline_config.py) ──

CONTENT_SAMPLE_INTERVAL_SEC = 5.0       # seconds between frame extractions
CONTENT_ENTROPY_THRESHOLD = 4.5         # Shannon entropy (grayscale, 256 bins)
CONTENT_EDGE_DENSITY_MAX = 0.08         # Canny edge density below this → "static"


class ContentSampler:
    """Extract content-representative frames on a fixed time-grid.

    Unlike diff-based sampling which favours *change*, this sampler
    favours *information density in static frames* — ideal for capturing
    LOGO reveals, end-cards, and text-heavy title screens.

    Attributes:
        interval_sec: Seconds between candidate frames.
        entropy_threshold: Minimum Shannon entropy to qualify.
        edge_density_max: Maximum Canny edge density (lower = more static).
    """

    def __init__(
        self,
        interval_sec: float = CONTENT_SAMPLE_INTERVAL_SEC,
        entropy_threshold: float = CONTENT_ENTROPY_THRESHOLD,
        edge_density_max: float = CONTENT_EDGE_DENSITY_MAX,
    ) -> None:
        self.interval_sec = interval_sec
        self.entropy_threshold = entropy_threshold
        self.edge_density_max = edge_density_max

    # ── Public API ──

    def sample(
        self,
        video_path: str,
        fps: float,
        total_duration: float,
    ) -> List[Dict[str, Any]]:
        """Walk the video timeline every *interval_sec* and return informative
        static frames.

        Each returned dict follows the same shape as
        ``AdaptiveSampler.sample_with_context()``:

            - frame_index (int)
            - timestamp (float)
            - diff_value (float) — always 0.0 for content frames
            - is_boundary (bool) — always False for content frames
            - source (str) — ``"content"``

        Args:
            video_path: Absolute path to the source video.
            fps: Frames per second (from signal layer).
            total_duration: Total video duration in seconds.

        Returns:
            List of dicts (one per qualifying content frame).  May be empty
            if no frames pass the entropy + edge thresholds.
        """
        if not os.path.exists(video_path) or total_duration <= 0 or fps <= 0:
            return []

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_interval = max(1, int(self.interval_sec * fps))
        n_frames = min(int(total_duration * fps), total_frames)

        results: List[Dict[str, Any]] = []

        for t_sec in np.arange(0, total_duration, self.interval_sec):
            frame_idx = int(t_sec * fps)
            if frame_idx >= n_frames:
                break

            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            entropy, edge_density = self._compute_frame_stats(frame)

            if entropy > self.entropy_threshold and edge_density < self.edge_density_max:
                results.append({
                    "frame_index": frame_idx,
                    "timestamp": float(t_sec),
                    "diff_value": 0.0,
                    "is_boundary": False,
                    "source": "content",
                    "_entropy": round(entropy, 3),
                    "_edge_density": round(edge_density, 4),
                })

        cap.release()
        return results

    # ── Frame stats ──

    @staticmethod
    def _compute_frame_stats(frame: np.ndarray) -> tuple:
        """Compute (Shannon entropy, Canny edge density) for a BGR frame.

        Args:
            frame: BGR image as numpy array.

        Returns:
            (entropy: float, edge_density: float).  Returns (0.0, 0.0) on
            degenerate input.
        """
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return 0.0, 0.0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # ── Shannon entropy (256-bin histogram) ──
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        hist = hist / (hist.sum() + 1e-10)
        entropy = float(-sum(
            p * np.log2(p + 1e-10) for p in hist.flatten() if p > 0
        ))

        # ── Canny edge density ──
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.count_nonzero(edges)) / (w * h)

        return entropy, edge_density
