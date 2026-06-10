"""Unit tests for frame difference analysis — understanding/signal/frame_diff.py.

Tests the opencv_capture context manager and calc_diff_curve logic
with mocked OpenCV VideoCapture.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from understanding.signal.frame_diff import (
    FrameDiffAnalyzer,
    opencv_capture,
)


# ═══════════════════════════════════════════════════════════════════
#  opencv_capture context manager
# ═══════════════════════════════════════════════════════════════════

class TestOpenCVCapture:
    """Context manager behavior: open, yield, release on exit/error."""

    @patch("cv2.VideoCapture")
    def test_success_path(self, mock_vc):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_vc.return_value = mock_cap

        with opencv_capture("/fake/video.mp4") as cap:
            assert cap is mock_cap
            mock_vc.assert_called_once_with("/fake/video.mp4")

        mock_cap.release.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_release_on_exception(self, mock_vc):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_vc.return_value = mock_cap

        with pytest.raises(RuntimeError):
            with opencv_capture("/fake/video.mp4") as cap:
                raise RuntimeError("test error")

        mock_cap.release.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_raises_on_unopenable(self, mock_vc):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_vc.return_value = mock_cap

        with pytest.raises(FileNotFoundError, match="Cannot open video"):
            with opencv_capture("/fake/video.mp4") as cap:
                pass

        mock_cap.release.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
#  FrameDiffAnalyzer.calc_diff_curve
# ═══════════════════════════════════════════════════════════════════

class TestCalcDiffCurve:
    """Diff curve computation with mocked VideoCapture."""

    @patch("cv2.VideoCapture")
    def test_empty_video_returns_empty_list(self, mock_vc):
        """A video with no readable frame returns []."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # First read fails immediately
        mock_cap.read.return_value = (False, None)
        mock_vc.return_value = mock_cap

        analyzer = FrameDiffAnalyzer()
        assert analyzer.calc_diff_curve("/fake/empty.mp4") == []

    @patch("cv2.VideoCapture")
    def test_single_frame_returns_empty(self, mock_vc):
        """A video with only 1 frame returns [] (no consecutive pairs)."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # Return one frame then fail
        mock_cap.read.side_effect = [
            (True, np.zeros((100, 100, 3), dtype=np.uint8)),
            (False, None),
        ]
        mock_vc.return_value = mock_cap

        analyzer = FrameDiffAnalyzer()
        assert analyzer.calc_diff_curve("/fake/single.mp4") == []

    @patch("cv2.calcHist")
    @patch("cv2.normalize")
    @patch("cv2.cvtColor")
    @patch("cv2.compareHist")
    @patch("cv2.VideoCapture")
    def test_two_frames_with_frame_skip_one(
        self, mock_vc, mock_compare, mock_cvt, mock_norm, mock_calc,
    ):
        """2 frames, frame_skip=1 → 1 diff value returned."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # Two frames then done
        mock_cap.read.side_effect = [
            (True, np.ones((10, 10, 3), dtype=np.uint8)),
            (True, np.ones((10, 10, 3), dtype=np.uint8) * 2),
            (False, None),
        ]
        mock_vc.return_value = mock_cap
        mock_compare.return_value = 0.5  # chi-squared distance
        mock_cvt.return_value = np.ones((10, 10, 3), dtype=np.uint8)
        mock_calc.return_value = np.array([[0.5]], dtype=np.float32)
        mock_norm.return_value = None

        analyzer = FrameDiffAnalyzer(bins=8, frame_skip=1)
        curve = analyzer.calc_diff_curve("/fake/two.mp4")
        assert len(curve) == 1
        assert curve[0] == 0.5

    @patch("cv2.calcHist")
    @patch("cv2.normalize")
    @patch("cv2.cvtColor")
    @patch("cv2.compareHist")
    @patch("cv2.VideoCapture")
    def test_frame_skip_skips_intermediate_frames(
        self, mock_vc, mock_compare, mock_cvt, mock_norm, mock_calc,
    ):
        """With frame_skip=3, only every 3rd frame pair is compared."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # 5 frames: F0→F1 skip, F1→F2 skip, F2→F3 compare, F3→F4 skip
        frames = [
            (True, np.ones((10, 10, 3), dtype=np.uint8) * i)
            for i in range(5)
        ]
        frames.append((False, None))
        mock_cap.read.side_effect = frames
        mock_vc.return_value = mock_cap
        mock_compare.side_effect = [0.3, 0.7]  # two comparisons
        mock_cvt.return_value = np.ones((10, 10, 3), dtype=np.uint8)
        mock_calc.return_value = np.array([[0.5]], dtype=np.float32)
        mock_norm.return_value = None

        analyzer = FrameDiffAnalyzer(bins=8, frame_skip=3)
        curve = analyzer.calc_diff_curve("/fake/skip.mp4")
        # 5 frames → F0 base → F3 compare → F4 base but no next frame
        # So: F0 base, F3 compare (diff at index 0)
        assert len(curve) == 1  # only one comparison happens


# ═══════════════════════════════════════════════════════════════════
#  FrameDiffAnalyzer._compute_hsv_histogram
# ═══════════════════════════════════════════════════════════════════

class TestComputeHSVHistogram:
    """Internal histogram computation with mocked cv2."""

    @patch("cv2.calcHist")
    @patch("cv2.normalize")
    @patch("cv2.cvtColor")
    def test_returns_flattened_normalized_hist(
        self, mock_cvt, mock_norm, mock_calc,
    ):
        mock_cvt.return_value = np.ones((10, 10, 3), dtype=np.uint8)
        mock_calc.return_value = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
        mock_norm.return_value = None

        analyzer = FrameDiffAnalyzer(bins=2, frame_skip=1)
        hist = analyzer._compute_hsv_histogram(np.zeros((10, 10, 3), dtype=np.uint8))

        assert hist.shape == (4,)  # 2×2 flattened
        assert hist[0] == 0.1
