"""Unit tests for video type classifier — understanding/signal/video_classifier.py.

Tests the 16-type heuristic rule engine with various signal_summary inputs.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from understanding.signal.video_classifier import VideoTypeClassifier, create_classifier


@pytest.fixture
def classifier():
    return create_classifier()


# ═══════════════════════════════════════════════════════════════════
#  Edge cases
# ═══════════════════════════════════════════════════════════════════

class TestClassifierEdgeCases:
    """Empty signal, fallback, and boundary conditions."""

    def test_empty_signal_returns_vlog_fallback(self, classifier):
        result = classifier.classify({})
        assert result["video_type"] == "vlog"
        assert result["method"] == "heuristic_fallback"
        assert result["confidence"] == 0.3

    def test_none_signal_returns_vlog_fallback(self, classifier):
        result = classifier.classify(None)
        assert result["video_type"] == "vlog"

    def test_top3_has_three_candidates(self, classifier):
        result = classifier.classify({"optical_flow_avg": 20.0, "edge_density_avg": 0.15})
        assert len(result["top3_candidates"]) == 3

    def test_scores_are_sorted_descending(self, classifier):
        result = classifier.classify({"optical_flow_avg": 20.0, "edge_density_avg": 0.15})
        scores = [c["score"] for c in result["top3_candidates"]]
        assert scores == sorted(scores, reverse=True)


# ═══════════════════════════════════════════════════════════════════
#  Heuristic rules
# ═══════════════════════════════════════════════════════════════════

class TestClassifierHeuristics:
    """Verify that specific signal profiles map to expected video types."""

    def test_high_motion_high_edges_favors_gaming(self, classifier):
        """flow > 10 and ed > 0.08 → gaming gets +0.35."""
        result = classifier.classify({
            "optical_flow_avg": 25.0,
            "edge_density_avg": 0.12,
        })
        assert result["video_type"] == "gaming"
        assert result["confidence"] >= 0.35

    def test_high_face_count_favors_vlog(self, classifier):
        """fc > 0.5 → vlog gets +0.20."""
        result = classifier.classify({
            "face_count_avg": 2.0,
        })
        assert result["video_type"] in ("vlog", "lecture", "parenting", "beauty_fashion")

    def test_neutral_clean_frames_favors_commercial(self, classifier):
        result = classifier.classify({
            "is_dominantly_neutral": True,
        })
        assert result["video_type"] in ("commercial", "lecture", "knowledge")

    def test_exciting_bgm_favors_gaming(self, classifier):
        """BGM matching alone gives +0.15 gaming; neutral defaults avoid lecture bias."""
        result = classifier.classify({
            "bgm_type": "激昂紧张",
            "bpm": 100,
            "optical_flow_avg": 5.0,
            "edge_density_avg": 0.05,
            "is_dominantly_neutral": False,
        })
        assert result["video_type"] in ("gaming", "sports")

    def test_cheerful_bgm_favors_vlog(self, classifier):
        result = classifier.classify({
            "bgm_type": "明快活泼",
            "bpm": 100,
            "optical_flow_avg": 5.0,
            "edge_density_avg": 0.05,
            "is_dominantly_neutral": False,
        })
        assert result["video_type"] in ("vlog", "travel", "food")

    def test_calm_bgm_favors_lecture(self, classifier):
        result = classifier.classify({
            "bgm_type": "舒缓沉静",
        })
        assert result["video_type"] in ("lecture", "travel", "agriculture")

    def test_high_bpm_favors_gaming(self, classifier):
        """High BPM + medium motion avoids default lecture classification."""
        result = classifier.classify({
            "bpm": 140,
            "optical_flow_avg": 5.0,
            "edge_density_avg": 0.05,
            "is_dominantly_neutral": False,
        })
        assert result["video_type"] in ("gaming", "sports")

    def test_low_bpm_favors_lecture(self, classifier):
        result = classifier.classify({
            "bpm": 50,
        })
        assert result["video_type"] in ("lecture", "travel")

    def test_low_motion_low_edges_favors_static_types(self, classifier):
        result = classifier.classify({
            "optical_flow_avg": 1.0,
            "edge_density_avg": 0.02,
        })
        assert result["video_type"] in ("lecture", "knowledge", "commercial")


# ═══════════════════════════════════════════════════════════════════
#  Combined signals (realistic scenarios)
# ═══════════════════════════════════════════════════════════════════

class TestClassifierCombined:
    """Realistic combinations of multiple signal features."""

    def test_gaming_scenario(self, classifier):
        result = classifier.classify({
            "optical_flow_avg": 30.0,
            "edge_density_avg": 0.15,
            "bgm_type": "激昂",
            "bpm": 140,
            "face_count_avg": 0.0,
            "is_dominantly_neutral": False,
        })
        assert result["video_type"] == "gaming"

    def test_lecture_scenario(self, classifier):
        result = classifier.classify({
            "optical_flow_avg": 1.0,
            "edge_density_avg": 0.02,
            "bgm_type": "舒缓",
            "bpm": 60,
            "face_count_avg": 0.0,
            "is_dominantly_neutral": True,
        })
        assert result["video_type"] == "lecture"

    def test_vlog_scenario(self, classifier):
        result = classifier.classify({
            "optical_flow_avg": 5.0,
            "edge_density_avg": 0.05,
            "bgm_type": "明快",
            "bpm": 100,
            "face_count_avg": 1.5,
            "is_dominantly_neutral": False,
        })
        assert result["video_type"] in ("vlog", "travel", "food")
