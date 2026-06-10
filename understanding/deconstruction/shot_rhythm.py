"""Shot rhythm extractor — scene-boundary-based pacing analysis.

Zero ML dependencies — pure numpy arithmetic on scene boundary timestamps.

Extracts:
    - shot durations and count
    - duration histogram (4 bins: <1s, 1-3s, 3-5s, >5s)
    - rhythm pattern (快-慢-快 / 慢-快-慢 / 均匀 / 快切为主)
    - cut frequency by structure segment type
    - motion intensity from diff_curve (percentiles, mean, peak, dynamic ratio)
"""

from typing import Any, Dict, List, Optional

import numpy as np


# ── Public API ─────────────────────────────────────────────────────────

def extract(
    signal_data: Dict[str, Any],
    structure_segments: Optional[List[Dict[str, Any]]] = None,
    keyframes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Extract shot rhythm metrics from scene boundaries.

    Args:
        signal_data: Pipeline signal-layer output dict, must contain
            ``scene_boundaries`` (List[float] seconds) and ``total_duration``.
            Optional: ``diff_curve`` for motion intensity.
        structure_segments: Structure inferrer output (for per-type cut rate).
        keyframes: Sampled keyframes (unused, reserved for future dims).

    Returns:
        Dict with:
            - avg_shot_duration: float (seconds)
            - shot_count: int
            - duration_distribution: dict {bucket: fraction}
            - rhythm_pattern: str
            - cut_frequency_by_segment: dict {seg_type: cuts_per_sec}
            - motion_intensity: dict {p25, p75, mean, peak, variance, dynamic_ratio}
    """
    boundaries = signal_data.get("scene_boundaries", [])
    total_dur = signal_data.get("total_duration", 0.0)

    # ── 1. Shot durations ──
    shot_durations, shot_count = _compute_shot_durations(boundaries, total_dur)

    if shot_count == 0:
        return _empty_result()

    avg_shot_duration = float(np.mean(shot_durations))

    # ── 2. Duration histogram (4 bins) ──
    duration_distribution = _duration_histogram(shot_durations)

    # ── 3. Rhythm pattern ──
    rhythm_pattern = _classify_rhythm(shot_durations)

    # ── 4. Cut frequency by structure segment ──
    cut_frequency_by_segment = _cut_rate_by_segment(
        boundaries, structure_segments,
        total_dur,
    )

    # ── 5. Motion intensity ──
    motion_intensity = _motion_intensity(signal_data.get("diff_curve", []))

    return {
        "avg_shot_duration": round(avg_shot_duration, 2),
        "shot_count": shot_count,
        "duration_distribution": duration_distribution,
        "rhythm_pattern": rhythm_pattern,
        "cut_frequency_by_segment": cut_frequency_by_segment,
        "motion_intensity": motion_intensity,
    }


# ── Internal helpers ───────────────────────────────────────────────────

def _compute_shot_durations(
    boundaries: List[float],
    total_dur: float,
) -> tuple:
    """Compute shot durations from boundaries, padding head/tail."""
    if not boundaries:
        return [], 0

    sorted_boundaries = sorted(boundaries)
    durations: List[float] = []

    # Head: 0 → first boundary
    if sorted_boundaries[0] > 0:
        durations.append(sorted_boundaries[0])

    # Body: adjacent delta
    for i in range(len(sorted_boundaries) - 1):
        d = sorted_boundaries[i + 1] - sorted_boundaries[i]
        if d > 0:
            durations.append(d)

    # Tail: last boundary → end
    if total_dur > sorted_boundaries[-1]:
        durations.append(total_dur - sorted_boundaries[-1])

    return durations, len(durations)


def _duration_histogram(durations: List[float]) -> Dict[str, float]:
    """Bin durations into 4 buckets, return normalized fractions."""
    bins = {"<1s": 0, "1-3s": 0, "3-5s": 0, ">5s": 0}
    for d in durations:
        if d < 1.0:
            bins["<1s"] += 1
        elif d < 3.0:
            bins["1-3s"] += 1
        elif d < 5.0:
            bins["3-5s"] += 1
        else:
            bins[">5s"] += 1

    total = max(sum(bins.values()), 1)
    return {k: round(v / total, 3) for k, v in bins.items()}


def _classify_rhythm(durations: List[float]) -> str:
    """Classify pacing pattern by comparing front/middle/back thirds.

    Returns one of: 快-慢-快, 慢-快-慢, 均匀, 快切为主.
    """
    n = len(durations)
    if n < 6:
        return "快切为主" if np.mean(durations) < 1.5 else "均匀"

    k = max(1, n // 3)
    front = np.mean(durations[:k])
    middle = np.mean(durations[k:2 * k])
    back = np.mean(durations[2 * k:])

    # 20% threshold for "non-uniform"
    def _diff_pct(a, b):
        return abs(a - b) / max((a + b) / 2, 0.01)

    if _diff_pct(front, middle) < 0.20 and _diff_pct(middle, back) < 0.20:
        return "均匀"

    if front < middle and back < middle:
        return "慢-快-慢"
    if front > middle and back > middle:
        return "快-慢-快"

    overall_mean = np.mean(durations)
    if overall_mean < 1.5:
        return "快切为主"
    return "均匀"


def _cut_rate_by_segment(
    boundaries: List[float],
    structure_segments: Optional[List[Dict[str, Any]]],
    total_dur: float,
) -> Dict[str, float]:
    """Compute cuts-per-second for each structure segment type."""
    result: Dict[str, float] = {}
    if not structure_segments or not boundaries:
        return result

    for seg in structure_segments:
        seg_type = seg.get("structure_type", "unclassified")
        t0 = seg.get("start_time", 0.0)
        t1 = seg.get("end_time", t0)
        dur = max(t1 - t0, 0.01)
        cuts = sum(1 for b in boundaries if t0 <= b <= t1)
        rate = round(cuts / dur, 3)
        if seg_type not in result:
            result[seg_type] = rate
        else:
            result[seg_type] = max(result[seg_type], rate)

    return result


def _motion_intensity(diff_curve: List[float]) -> Dict[str, Any]:
    """Compute motion intensity stats from the diff curve."""
    if not diff_curve:
        return {
            "p25": 0.0, "p75": 0.0,
            "mean": 0.0, "peak": 0.0,
            "variance": 0.0, "dynamic_ratio": 0.0,
        }

    arr = np.asarray(diff_curve, dtype=float)
    mean_val = float(np.mean(arr))
    dynamic_ratio = float(np.sum(arr > 0.1) / max(len(arr), 1))

    return {
        "p25": round(float(np.percentile(arr, 25)), 4),
        "p75": round(float(np.percentile(arr, 75)), 4),
        "mean": round(mean_val, 4),
        "peak": round(float(np.max(arr)), 4),
        "variance": round(float(np.var(arr)), 6),
        "dynamic_ratio": round(dynamic_ratio, 3),
    }


def _empty_result() -> Dict[str, Any]:
    return {
        "avg_shot_duration": 0.0,
        "shot_count": 0,
        "duration_distribution": {"<1s": 0.0, "1-3s": 0.0, "3-5s": 0.0, ">5s": 0.0},
        "rhythm_pattern": "均匀",
        "cut_frequency_by_segment": {},
        "motion_intensity": {
            "p25": 0.0, "p75": 0.0,
            "mean": 0.0, "peak": 0.0,
            "variance": 0.0, "dynamic_ratio": 0.0,
        },
    }
