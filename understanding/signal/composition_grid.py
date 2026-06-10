"""Composition grid analysis — 3×3 zone mapping from YOLO bounding boxes.

Pure utility module — no classes, no dependencies beyond numpy.
Exports a single aggregation function :func:`analyze_composition_grid`.

Grid zones (3×3)::

    ┌─────────┬─────────┬─────────┐
    │ top_left│  top    │top_right│
    ├─────────┼─────────┼─────────┤
    │  left   │ center  │  right  │
    ├─────────┼─────────┼─────────┤
    │btm_left │ bottom  │btm_right│
    └─────────┴─────────┴─────────┘

Diagonal bands:  main (top-left → bottom-right), anti (top-right → bottom-left).
"""

from typing import Any, Dict, List, Tuple

from understanding.pipeline_config import (
    GRID_COLS, GRID_ROWS,
    GRID_COL_BOUNDARY, GRID_ROW_BOUNDARY,
    CENTER_SYMMETRY_CENTERED, CENTER_SYMMETRY_SHIFTED,
    CENTER_SYMMETRY_IMBALANCE,
    DIAGONAL_BAND_WIDTH, DIAGONAL_HIT_THRESHOLD,
    SUBJECT_COVERAGE_SPARSE, SUBJECT_COVERAGE_FULL,
    PERSON_WEIGHT_MULTIPLIER,
)

# ── Zone grid constants ────────────────────────────────────────────────

_ZONE_COLS = ["left", "center", "right"]
_ZONE_ROWS = ["top", "middle", "bottom"]

_ZONE_NAMES = [
    "top_left", "top", "top_right",
    "left",    "center", "right",
    "bottom_left", "bottom", "bottom_right",
]

# ── Public API ─────────────────────────────────────────────────────────

def analyze_composition_grid(
    bboxes: List[dict],
    frame_width: int,
    frame_height: int,
    face_count: int = 0,
) -> Dict[str, Any]:
    """Analyse spatial distribution of YOLO bounding boxes on a 3×3 grid.

    Args:
        bboxes: List of YOLO detection dicts, each with
            ``class_name`` (str) and ``bbox`` [x1, y1, x2, y2]
            in **pixel** coordinates.
        frame_width, frame_height: Image dimensions.
        face_count: Number of detected faces (for heuristic override).

    Returns:
        Dict with keys:

        - **grid_dominant_zone**    (str)     zone with max weighted area
        - **grid_dominant_ratio**   (float)   its fraction of total occupied
        - **center_symmetry**       (str)     "居中" | "偏移" | "边缘" | "空"
        - **center_ratio**          (float)   bbox area in center zone ÷ total
        - **diagonal_presence**     (bool)    ≥20% of weighted area on diagonal
        - **diagonal_ratio**        (float)   fraction on stronger diagonal
        - **subject_coverage**      (float)   total bbox area ÷ frame area
        - **subject_coverage_label** (str)    "点缀" | "适中" | "饱满" | "空"
        - **zones**                 (dict)    9 zone → weighted area mapping
    """
    frame_area = frame_width * frame_height

    # ── Accumulate weighted area per zone ──
    zone_areas: Dict[str, float] = {z: 0.0 for z in _ZONE_NAMES}
    total_area = 0.0
    diag_main_total = 0.0
    diag_anti_total = 0.0

    for obj in bboxes:
        b = obj.get("bbox", [])
        if len(b) < 4:
            continue
        x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
        w, h = float(x2 - x1), float(y2 - y1)
        if w <= 0 or h <= 0:
            continue

        area = w * h
        cls_name = obj.get("class_name", "")

        # Person weighting
        weight = PERSON_WEIGHT_MULTIPLIER if cls_name == "person" else 1.0
        weighted = area * weight
        total_area += weighted

        # Centre point (normalised)
        cx = (x1 + x2) / 2.0 / frame_width
        cy = (y1 + y2) / 2.0 / frame_height

        # ── Map to zone ──
        zone = _bbox_to_zone(cx, cy)
        zone_areas[zone] += weighted

        # ── Diagonal check ──
        if _on_diag_main(cx, cy):
            diag_main_total += weighted
        if _on_diag_anti(cx, cy):
            diag_anti_total += weighted

    # ── Derive results ──
    if total_area <= 0:
        return _empty_result()

    # Dominant zone
    dominant_zone = max(zone_areas, key=zone_areas.get)
    dominant_ratio = zone_areas[dominant_zone] / total_area

    # Center symmetry
    center_area = zone_areas.get("center", 0.0)
    center_ratio = center_area / total_area

    if center_ratio > CENTER_SYMMETRY_CENTERED:
        center_symmetry = "居中"
    elif center_ratio > CENTER_SYMMETRY_SHIFTED:
        # Check if area is concentrated in one side
        left_area = sum(zone_areas[z] for z in _ZONE_NAMES if "left" in z)
        right_area = sum(zone_areas[z] for z in _ZONE_NAMES if "right" in z)
        top_area = sum(zone_areas[z] for z in _ZONE_NAMES if z.startswith("top"))
        bottom_area = sum(zone_areas[z] for z in _ZONE_NAMES if z.startswith("bottom"))
        if face_count > 0:  # face-driven → person subject → likely centered
            center_symmetry = "居中"
        elif max(left_area, right_area) / total_area > CENTER_SYMMETRY_IMBALANCE:
            center_symmetry = "偏移"
        elif max(top_area, bottom_area) / total_area > CENTER_SYMMETRY_IMBALANCE:
            center_symmetry = "偏移"
        else:
            center_symmetry = "居中"
    else:
        center_symmetry = "边缘"

    # Diagonal presence
    diag_ratio = max(diag_main_total, diag_anti_total) / total_area
    diagonal_presence = diag_ratio >= DIAGONAL_HIT_THRESHOLD

    # Subject coverage
    subject_coverage = total_area / max(frame_area, 1)
    if subject_coverage < SUBJECT_COVERAGE_SPARSE:
        coverage_label = "点缀"
    elif subject_coverage < SUBJECT_COVERAGE_FULL:
        coverage_label = "适中"
    else:
        coverage_label = "饱满"

    return {
        "grid_dominant_zone": dominant_zone,
        "grid_dominant_ratio": round(dominant_ratio, 3),
        "center_symmetry": center_symmetry,
        "center_ratio": round(center_ratio, 3),
        "diagonal_presence": diagonal_presence,
        "diagonal_ratio": round(diag_ratio, 3),
        "subject_coverage": round(subject_coverage, 4),
        "subject_coverage_label": coverage_label,
        "zones": {z: round(v / total_area, 3) for z, v in zone_areas.items()},
    }


# ── Helpers ─────────────────────────────────────────────────────────────

def _bbox_to_zone(cx: float, cy: float) -> str:
    """Map a normalised centre point (0-1, 0-1) to a 3×3 grid label."""
    # Column
    if cx < GRID_COL_BOUNDARY:
        col = "left"
    elif cx > GRID_ROW_BOUNDARY:  # 0.67 = right boundary
        col = "right"
    else:
        col = "center"

    # Row
    if cy < GRID_COL_BOUNDARY:
        row = "top"
    elif cy > GRID_ROW_BOUNDARY:
        row = "bottom"
    else:
        row = "middle"

    # Combine
    if row == "middle" and col == "center":
        return "center"
    if row == "middle":
        return col
    if col == "center":
        return row
    return f"{row}_{col}"


def _on_diag_main(cx: float, cy: float) -> bool:
    """True if centre lies on the main diagonal band (top-left → bottom-right).

    Diagonal band is defined as |cx - cy| < DIAGONAL_BAND_WIDTH.
    """
    return abs(cx - cy) < DIAGONAL_BAND_WIDTH


def _on_diag_anti(cx: float, cy: float) -> bool:
    """True if centre lies on the anti-diagonal band (top-right → bottom-left).

    Anti-diagonal: cx + cy ≈ 1  →  |(cx + cy) - 1| < DIAGONAL_BAND_WIDTH.
    """
    return abs((cx + cy) - 1.0) < DIAGONAL_BAND_WIDTH


def _empty_result() -> Dict[str, Any]:
    """Return a safe empty result when no valid bounding boxes are present."""
    return {
        "grid_dominant_zone": "空",
        "grid_dominant_ratio": 0.0,
        "center_symmetry": "空",
        "center_ratio": 0.0,
        "diagonal_presence": False,
        "diagonal_ratio": 0.0,
        "subject_coverage": 0.0,
        "subject_coverage_label": "空",
        "zones": {z: 0.0 for z in _ZONE_NAMES},
    }
