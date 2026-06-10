"""Unit tests for composition grid analysis — understanding/signal/composition_grid.py.

Tests the 3×3 zone mapping, diagonal detection, center symmetry,
subject coverage, and edge cases (empty, single bbox, full frame).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from understanding.signal.composition_grid import (
    analyze_composition_grid,
    _bbox_to_zone,
    _on_diag_main,
    _on_diag_anti,
)


# ═══════════════════════════════════════════════════════════════════
#  Zone mapping (_bbox_to_zone)
# ═══════════════════════════════════════════════════════════════════

class TestBboxToZone:
    """Verify normalized (cx, cy) → zone label mapping for all 9 zones."""

    def test_center(self):
        assert _bbox_to_zone(0.5, 0.5) == "center"

    def test_top_left(self):
        assert _bbox_to_zone(0.1, 0.1) == "top_left"

    def test_top(self):
        assert _bbox_to_zone(0.5, 0.1) == "top"

    def test_top_right(self):
        assert _bbox_to_zone(0.9, 0.1) == "top_right"

    def test_left(self):
        assert _bbox_to_zone(0.1, 0.5) == "left"

    def test_right(self):
        assert _bbox_to_zone(0.9, 0.5) == "right"

    def test_bottom_left(self):
        assert _bbox_to_zone(0.1, 0.9) == "bottom_left"

    def test_bottom(self):
        assert _bbox_to_zone(0.5, 0.9) == "bottom"

    def test_bottom_right(self):
        assert _bbox_to_zone(0.9, 0.9) == "bottom_right"

    def test_on_boundary_col(self):
        """Points exactly on col boundary (0.33) map to 'center' column."""
        assert _bbox_to_zone(0.33, 0.5) == "center"

    def test_on_boundary_row(self):
        """Points exactly on row boundary (0.67) map to 'middle' row."""
        assert _bbox_to_zone(0.5, 0.67) == "center"


# ═══════════════════════════════════════════════════════════════════
#  Diagonal helpers
# ═══════════════════════════════════════════════════════════════════

class TestDiagonalHelpers:
    """Diagonal band (DIAGONAL_BAND_WIDTH=0.12)."""

    def test_main_diag_center(self):
        assert _on_diag_main(0.5, 0.5) is True

    def test_main_diag_near(self):
        assert _on_diag_main(0.5, 0.55) is True   # |0.5-0.55| = 0.05 < 0.12

    def test_main_diag_far(self):
        assert _on_diag_main(0.5, 0.8) is False   # |0.5-0.8| = 0.30 > 0.12

    def test_anti_diag_center(self):
        assert _on_diag_anti(0.3, 0.7) is True    # 0.3+0.7 = 1.0

    def test_anti_diag_near(self):
        assert _on_diag_anti(0.25, 0.75) is True  # |(0.25+0.75)-1| = 0

    def test_anti_diag_far(self):
        assert _on_diag_anti(0.2, 0.3) is False   # |0.5-1| = 0.5 > 0.12


# ═══════════════════════════════════════════════════════════════════
#  Full analysis (analyze_composition_grid)
# ═══════════════════════════════════════════════════════════════════

class TestAnalyzeCompositionGrid:
    """Full pipeline integration of bbox → zone → symmetry → coverage."""

    FRAME_W, FRAME_H = 1920, 1080

    def test_empty_bboxes_returns_safe_default(self):
        result = analyze_composition_grid([], self.FRAME_W, self.FRAME_H)
        assert result["grid_dominant_zone"] == "空"
        assert result["center_symmetry"] == "空"
        assert result["subject_coverage_label"] == "空"
        assert result["subject_coverage"] == 0.0
        assert result["diagonal_presence"] is False

    @pytest.mark.parametrize("cx,cy,expected_zone", [
        (960, 540, "center"),    # exact center
        (200, 100, "top_left"),  # top-left
        (1800, 950, "bottom_right"),  # bottom-right
    ])
    def test_single_bbox_zone_mapping(self, cx, cy, expected_zone):
        bboxes = [{
            "class_name": "person",
            "bbox": [cx - 50, cy - 50, cx + 50, cy + 50],
        }]
        result = analyze_composition_grid(bboxes, self.FRAME_W, self.FRAME_H)
        assert result["grid_dominant_zone"] == expected_zone
        # Single bbox → dominant ratio ≈ 1.0
        assert result["grid_dominant_ratio"] > 0.9

    def test_person_weight_double(self):
        """Person-class bbox gets 1.5× weight multiplier."""
        bboxes = [
            {"class_name": "person", "bbox": [400, 400, 500, 500]},
        ]
        without_person = analyze_composition_grid(
            [{"class_name": "car", "bbox": [400, 400, 500, 500]}],
            self.FRAME_W, self.FRAME_H,
        )
        with_person = analyze_composition_grid(
            bboxes, self.FRAME_W, self.FRAME_H,
        )
        # Person version should have higher subject_coverage (1.5× area)
        assert with_person["subject_coverage"] > without_person["subject_coverage"]

    def test_center_symmetry_centered(self):
        """Large center bbox → '居中'."""
        bboxes = [{
            "class_name": "car",
            "bbox": [700, 300, 1200, 700],  # large center area
        }]
        result = analyze_composition_grid(bboxes, self.FRAME_W, self.FRAME_H)
        assert result["center_symmetry"] == "居中"
        assert result["center_ratio"] > 0.6

    def test_center_symmetry_shifted(self):
        """Off-center bbox → '偏移'."""
        bboxes = [{
            "class_name": "car",
            "bbox": [100, 300, 600, 700],  # shifted to left
        }]
        result = analyze_composition_grid(bboxes, self.FRAME_W, self.FRAME_H)
        # Center area should be small
        assert result["center_symmetry"] in ("偏移", "边缘")

    def test_diagonal_presence_detected(self):
        """BBoxes on the diagonal → diagonal_presence=True."""
        bboxes = [
            {"class_name": "car", "bbox": [100, 100, 150, 150]},     # top-left
            {"class_name": "car", "bbox": [1700, 850, 1800, 950]},   # bottom-right
        ]
        result = analyze_composition_grid(bboxes, self.FRAME_W, self.FRAME_H)
        assert result["diagonal_presence"] is True

    def test_subject_coverage_sparse(self):
        """Tiny bbox → '点缀' coverage."""
        bboxes = [{
            "class_name": "car",
            "bbox": [950, 530, 970, 550],  # tiny 20×20 bbox
        }]
        result = analyze_composition_grid(bboxes, self.FRAME_W, self.FRAME_H)
        assert result["subject_coverage_label"] == "点缀"
        assert result["subject_coverage"] < 0.05

    def test_subject_coverage_full(self):
        """Near-full-frame bbox → '饱满' coverage."""
        bboxes = [{
            "class_name": "car",
            "bbox": [0, 0, 1900, 1070],  # nearly full frame
        }]
        result = analyze_composition_grid(bboxes, self.FRAME_W, self.FRAME_H)
        assert result["subject_coverage_label"] == "饱满"
