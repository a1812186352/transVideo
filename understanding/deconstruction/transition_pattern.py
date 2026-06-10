"""Transition pattern extraction — type distribution, density, visual signals.

Zero ML — pure statistics on structure_segments and keyframes.
"""

from typing import Any, Dict, List, Optional


def extract(
    signal_data: Dict[str, Any],
    structure_segments: Optional[List[Dict[str, Any]]] = None,
    keyframes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Extract transition pattern metrics.

    Args:
        signal_data: Pipeline output.
        structure_segments: Structure inferrer output.
        keyframes: Sampled keyframes.

    Returns:
        Dict with: type_distribution, total_count, density_per_second,
        usage_context, visual_cut_signals.
    """
    if not structure_segments:
        return {"available": False}

    # Collect transition + effect segments
    trans_segs = [
        s for s in structure_segments
        if s.get("structure_type") in ("transition", "effect")
    ]

    if not trans_segs:
        return {"available": True, "total_count": 0}

    total_dur = signal_data.get("total_duration", 1.0)

    # ── Type distribution ──
    type_dist = _type_distribution(trans_segs)

    # ── Usage context ──
    usage_ctx = _usage_context(trans_segs)

    # ── Visual cut signals ──
    visual = _visual_cut_signals(keyframes)

    return {
        "available": True,
        "type_distribution": type_dist,
        "total_count": len(trans_segs),
        "density_per_second": round(len(trans_segs) / max(total_dur, 0.01), 3),
        "usage_context": usage_ctx,
        "visual_cut_signals": visual,
    }


def _type_distribution(trans_segs: List[dict]) -> Dict[str, float]:
    counts: Dict[str, int] = {}
    for s in trans_segs:
        st = s.get("sub_type", "")
        if not st:
            st = s.get("structure_type", "unknown")
        counts[st] = counts.get(st, 0) + 1
    total = max(sum(counts.values()), 1)
    return {k: round(v / total, 3) for k, v in counts.items()}


def _usage_context(trans_segs: List[dict]) -> Dict[str, List[str]]:
    """Map each sub_type to the evidence contexts in which it appears."""
    result: Dict[str, set] = {}
    for s in trans_segs:
        st = s.get("sub_type", s.get("structure_type", "unknown"))
        ev = s.get("evidence", [])
        if st not in result:
            result[st] = set()
        result[st].update(ev)
    return {k: sorted(v) for k, v in result.items()}


def _visual_cut_signals(
    keyframes: Optional[List[dict]],
) -> Dict[str, Any]:
    if not keyframes:
        return {"high_visual_change_ratio": 0.0, "avg_histogram_distance": 0.0, "max_histogram_distance": 0.0}

    hd_vals = [k.get("histogram_distance", 0.0) for k in keyframes if isinstance(k, dict)]
    if not hd_vals:
        return {"high_visual_change_ratio": 0.0, "avg_histogram_distance": 0.0, "max_histogram_distance": 0.0}

    high = sum(1 for v in hd_vals if v > 0.3) / len(hd_vals)
    return {
        "high_visual_change_ratio": round(high, 3),
        "avg_histogram_distance": round(sum(hd_vals) / len(hd_vals), 4),
        "max_histogram_distance": round(max(hd_vals), 4),
    }
