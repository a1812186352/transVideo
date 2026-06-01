"""Frame difference analysis using OpenCV HSV histogram comparison.

Produces a frame-difference curve for downstream adaptive sampling.
"""

import cv2
import numpy as np
from typing import List, Tuple


class FrameDiffAnalyzer:
    """Computes frame-to-frame HSV histogram difference curve.

    Attributes:
        bins: Number of histogram bins per channel (default 32 for H, 32 for S).
        frame_skip: Sample every Nth frame (default 5 — 60fps → 12fps effective).
    """

    def __init__(self, bins: int = 32, frame_skip: int = 5) -> None:
        self.bins = bins
        self.frame_skip = frame_skip
        # Enable OpenCL acceleration if available
        if cv2.ocl.haveOpenCL():
            cv2.ocl.setUseOpenCL(True)

    def calc_diff_curve(self, video_path: str) -> List[float]:
        """Compute frame-difference values for the entire video.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            List of float values, one per consecutive frame pair.
            diff_curve[i] is the chi-squared distance between frame i and i+1.

        Raises:
            FileNotFoundError: If video_path does not exist.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path}")

        diff_curve: List[float] = []
        ret, prev_frame = cap.read()
        if not ret:
            cap.release()
            return diff_curve

        prev_hist = self._compute_hsv_histogram(prev_frame)

        skipped = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            skipped += 1
            if skipped < self.frame_skip:
                continue
            skipped = 0
            curr_hist = self._compute_hsv_histogram(frame)
            diff = cv2.compareHist(prev_hist, curr_hist, cv2.HISTCMP_CHISQR)
            diff_curve.append(float(diff))
            prev_hist = curr_hist

        cap.release()
        return diff_curve

    def calc_diff_curve_with_timestamps(
        self, video_path: str
    ) -> Tuple[List[float], List[float]]:
        """Compute frame-difference values with per-frame timestamps in seconds.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            Tuple of (diff_curve, timestamps) where timestamps[i] corresponds
            to the time of frame i+1 (the frame after the diff).
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30.0

        diff_curve: List[float] = []
        timestamps: List[float] = []

        ret, prev_frame = cap.read()
        if not ret:
            cap.release()
            return diff_curve, timestamps

        prev_hist = self._compute_hsv_histogram(prev_frame)
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            if frame_idx % self.frame_skip != 0:
                continue
            curr_hist = self._compute_hsv_histogram(frame)
            diff = cv2.compareHist(prev_hist, curr_hist, cv2.HISTCMP_CHISQR)
            diff_curve.append(float(diff))
            timestamps.append(frame_idx / fps)
            prev_hist = curr_hist

        cap.release()
        return diff_curve, timestamps

    def _compute_hsv_histogram(self, frame: np.ndarray) -> np.ndarray:
        """Convert BGR frame to HSV and compute normalized histogram.

        Args:
            frame: BGR image array from cv2.VideoCapture.

        Returns:
            Flattened normalized histogram array.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist(
            [hsv], [0, 1], None, [self.bins, self.bins], [0, 180, 0, 256]
        )
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist.flatten()
