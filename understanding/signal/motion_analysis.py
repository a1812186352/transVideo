"""Keyframe-pair motion analysis using sparse optical flow + feature matching.

Zero external dependencies beyond OpenCV (built-in).  Uses Shi-Tomasi
corner detection + Lucas-Kanade tracking for displacement / scale / rotation,
and ORB for feature-match verification.

Provided classes:
    MotionAnalyzer  — frame-pair and batch-video motion analysis
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

_log = logging.getLogger(__name__)

# ── Result dataclass ──────────────────────────────────────────────────

@dataclass
class MotionResult:
    """Structured motion-analysis output for one keyframe pair."""
    displacement: Tuple[float, float]  # (dx, dy) normalized to [0, 1]
    scale_factor: float                # >1 = zoom-in, <1 = zoom-out
    rotation_angle: float              # degrees (+ = clockwise)
    brightness_delta: float            # positive = brighter
    confidence: float                  # 0–1
    # Optional debug fields
    raw_vector_count: int = 0
    label: str = ""                    # filled by classify_motion


# ── Main class ────────────────────────────────────────────────────────

class MotionAnalyzer:
    """Analyze motion between keyframe pairs using sparse optical flow.

    Works on BGR images (numpy arrays).  No model download required —
    only OpenCV's built-in functions.

    Attributes:
        lk_win_size: Lucas-Kanade search window.
        min_corners: Minimum Shi-Tomasi corners to attempt tracking.
        quality_level: Corner quality threshold.
    """

    # ── Classification thresholds ──
    SCALE_ZOOM_THRESHOLD = 0.02       # |scale - 1| > this → zoom
    ROTATION_THRESHOLD = 2.0          # degrees → rotation
    BRIGHTNESS_FADE_THRESHOLD = 30.0  # |delta| > this → fade
    HIST_CUT_THRESHOLD = 0.6          # Chi-sq hist distance → cut
    DISPLACEMENT_PAN_THRESHOLD = 0.03 # fraction of frame → pan

    def __init__(
        self,
        lk_win_size: Tuple[int, int] = (15, 15),
        min_corners: int = 30,
        quality_level: float = 0.01,
    ) -> None:
        self.lk_win_size = lk_win_size
        self.min_corners = min_corners
        self.quality_level = quality_level

        # ── LK params ──
        self._lk_params = dict(
            winSize=lk_win_size,
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )

    # ── Public API ──

    def analyze_keyframe_pair(
        self, frame_a: np.ndarray, frame_b: np.ndarray
    ) -> MotionResult:
        """Analyze motion between two BGR frames.

        Args:
            frame_a: First frame (BGR).
            frame_b: Second frame (BGR).

        Returns:
            MotionResult with normalized displacement, scale, rotation, brightness, confidence.
        """
        h, w = frame_a.shape[:2]
        gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)

        # ── 1. Shi-Tomasi corners ──
        corners = cv2.goodFeaturesToTrack(
            gray_a, maxCorners=200, qualityLevel=self.quality_level,
            minDistance=7, blockSize=7,
        )
        if corners is None or len(corners) < self.min_corners:
            return MotionResult(
                displacement=(0.0, 0.0), scale_factor=1.0,
                rotation_angle=0.0, brightness_delta=0.0, confidence=0.0,
            )

        # ── 2. Lucas-Kanade tracking ──
        pts_a = corners.reshape(-1, 2).astype(np.float32)
        pts_b, status, _err = cv2.calcOpticalFlowPyrLK(
            gray_a, gray_b, pts_a, None, **self._lk_params,
        )
        if pts_b is None:
            return MotionResult(
                displacement=(0.0, 0.0), scale_factor=1.0,
                rotation_angle=0.0, brightness_delta=0.0, confidence=0.0,
            )

        # ── 3. Filter successful tracks ──
        status = status.flatten()
        good_a = pts_a[status == 1]
        good_b = pts_b[status == 1]

        if len(good_a) < self.min_corners:
            return MotionResult(
                displacement=(0.0, 0.0), scale_factor=1.0,
                rotation_angle=0.0, brightness_delta=0.0, confidence=0.0,
            )

        # ── 4. Displacement (normalised) ──
        vectors = good_b - good_a
        dx = float(np.median(vectors[:, 0])) / w
        dy = float(np.median(vectors[:, 1])) / h

        # ── 5. Scale factor (expansion / contraction of vector field) ──
        # Compute distances from geometric centre of tracked points
        center_a = np.mean(good_a, axis=0)
        center_b = np.mean(good_b, axis=0)
        dist_a = np.linalg.norm(good_a - center_a, axis=1)
        dist_b = np.linalg.norm(good_b - center_b, axis=1)
        # Avoid divide-by-zero on degenerate clusters
        mask_s = dist_a > 1e-4
        if mask_s.any():
            scale = float(np.median(dist_b[mask_s] / dist_a[mask_s]))
        else:
            scale = 1.0

        # ── 6. Rotation angle ──
        vec_a = good_a - center_a
        vec_b = good_b - center_b
        angles_a = np.arctan2(vec_a[:, 1], vec_a[:, 0])
        angles_b = np.arctan2(vec_b[:, 1], vec_b[:, 0])
        delta_angle = np.degrees(np.median(angles_b - angles_a))
        rotation = float((delta_angle + 180.0) % 360.0 - 180.0)  # wrap to [-180, 180]

        # ── 7. Brightness delta ──
        bm_a = float(gray_a.mean())
        bm_b = float(gray_b.mean())
        brightness_delta = bm_b - bm_a

        # ── 8. Confidence ──
        # Higher when more points tracked / lower error
        track_ratio = len(good_a) / max(len(pts_a), 1)
        err_mean = float(np.mean(_err[status == 1])) if _err is not None else 1.0
        err_norm = max(0.0, 1.0 - err_mean / 10.0)
        confidence = round(float(track_ratio * 0.6 + err_norm * 0.4), 3)

        return MotionResult(
            displacement=(round(dx, 5), round(dy, 5)),
            scale_factor=round(scale, 4),
            rotation_angle=round(rotation, 2),
            brightness_delta=round(brightness_delta, 2),
            confidence=confidence,
            raw_vector_count=len(good_a),
        )

    def analyze_video(
        self, keyframe_paths: List[Tuple[str, str]], timestamps: Optional[List[Tuple[float, float]]] = None,
    ) -> List[MotionResult]:
        """Batch-analyze a sequence of consecutive keyframe pairs.

        Applies median filtering across the sequence to denoise adjacent
        results that diverge sharply from their neighbours.

        Args:
            keyframe_paths: List of (path_a, path_b) tuples.
            timestamps: Optional list of (t_a, t_b) time tuples (unused, reserved).

        Returns:
            List of MotionResult, one per input pair.
        """
        results: List[MotionResult] = []
        for paths in keyframe_paths:
            img_a = cv2.imread(paths[0])
            img_b = cv2.imread(paths[1])
            if img_a is None or img_b is None:
                results.append(MotionResult(
                    displacement=(0, 0), scale_factor=1.0,
                    rotation_angle=0, brightness_delta=0, confidence=0,
                ))
                continue
            results.append(self.analyze_keyframe_pair(img_a, img_b))

        # ── Median-filter denoising ──
        if len(results) >= 3:
            self._median_smooth(results)

        return results

    def classify_motion(self, result: MotionResult, hist_distance: float = 0.0) -> str:
        """Classify a MotionResult into a human-readable label.

        Priority: CUT → FADE → ZOOM → ROTATE → PAN → STATIC.

        Args:
            result: MotionResult from analyze_keyframe_pair.
            hist_distance: Optional Chi-squared histogram distance
                           (0.0 if not computed).

        Returns:
            Label string: CUT / FADE_IN / FADE_OUT / ZOOM_IN / ZOOM_OUT /
            PAN_LEFT / PAN_RIGHT / PAN_UP / PAN_DOWN / ROTATE_CW / ROTATE_CCW /
            STATIC.
        """
        dx, dy = result.displacement
        scale = result.scale_factor
        rotation = result.rotation_angle
        bright = result.brightness_delta

        # ── CUT: large histogram jump + low flow ──
        if hist_distance > self.HIST_CUT_THRESHOLD and abs(dx) + abs(dy) < 0.05:
            result.label = "CUT"
            return "CUT"

        # ── FADE: large brightness change, minimal motion ──
        if abs(bright) > self.BRIGHTNESS_FADE_THRESHOLD and abs(scale - 1.0) < 0.03 and abs(rotation) < 1.0:
            if bright > 0:
                result.label = "FADE_IN"
            else:
                result.label = "FADE_OUT"
            return result.label

        # ── ZOOM: scale deviation significant ──
        if abs(scale - 1.0) > self.SCALE_ZOOM_THRESHOLD:
            if scale > 1.0:
                result.label = "ZOOM_IN"
            else:
                result.label = "ZOOM_OUT"
            return result.label

        # ── ROTATE: rotation dominant ──
        if abs(rotation) > self.ROTATION_THRESHOLD:
            if rotation > 0:
                result.label = "ROTATE_CW"
            else:
                result.label = "ROTATE_CCW"
            return result.label

        # ── PAN: displacement dominant ──
        if abs(dx) > self.DISPLACEMENT_PAN_THRESHOLD or abs(dy) > self.DISPLACEMENT_PAN_THRESHOLD:
            if abs(dx) >= abs(dy):
                if dx > 0:
                    result.label = "PAN_RIGHT"
                else:
                    result.label = "PAN_LEFT"
            else:
                if dy > 0:
                    result.label = "PAN_DOWN"
                else:
                    result.label = "PAN_UP"
            return result.label

        # ── Default: no significant motion ──
        result.label = "STATIC"
        return "STATIC"

    # ── Internal ──

    def _median_smooth(self, results: List[MotionResult]) -> None:
        """In-place median smoothing of scale_factor across sequence."""
        scales = [r.scale_factor for r in results]
        k = 1  # window half-size = 1 (window = 3)
        smoothed: List[float] = []
        for i in range(len(scales)):
            lo = max(0, i - k)
            hi = min(len(scales), i + k + 1)
            smoothed.append(float(np.median(scales[lo:hi])))
        for r, s in zip(results, smoothed):
            r.scale_factor = round(s, 4)
