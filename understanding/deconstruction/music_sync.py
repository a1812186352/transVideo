"""BGM beat-sync & music structure extraction.

Uses BPM for beat grid alignment, energy_curve for structure detection,
and scene_boundaries for cut-point sync analysis.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def extract(
    signal_data: Dict[str, Any],
    structure_segments: Optional[List[Dict[str, Any]]] = None,
    keyframes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Extract BGM beat-sync and music structure metrics.

    Args:
        signal_data: Pipeline output with ``audio_data`` (bpm, beat_times,
            energy_curve) and ``scene_boundaries``.
        structure_segments: Unused.
        keyframes: Unused.

    Returns:
        Dict with: bpm, beat_interval, sync_density, sync_pattern,
        avg_offset_from_beat, music_structure, energy_cut_correlation.
    """
    audio = signal_data.get("audio_data", {})
    bpm = audio.get("bpm", 0)
    boundaries = signal_data.get("scene_boundaries", [])
    energy_curve = audio.get("energy_curve", [])
    duration = audio.get("duration", signal_data.get("total_duration", 0))

    if bpm <= 0 or not boundaries:
        return {"available": True if bpm > 0 else False}

    beat_interval = 60.0 / bpm

    # ── 1. Beat alignment ──
    sync_ratio, avg_offset = _beat_alignment(boundaries, bpm, beat_interval)
    sync_pattern = "强拍对齐" if sync_ratio > 0.7 else "弱对齐" if sync_ratio > 0.3 else "无对齐"

    # ── 2. Music structure ──
    music_structure = _music_structure(energy_curve, duration)

    # ── 3. Energy-cut correlation ──
    correlation = _energy_cut_correlation(energy_curve, boundaries, duration)

    return {
        "available": True,
        "bpm": bpm,
        "beat_interval": round(beat_interval, 3),
        "sync_density": round(sync_ratio, 3),
        "sync_pattern": sync_pattern,
        "avg_offset_from_beat": round(avg_offset, 3),
        "music_structure": music_structure,
        "energy_cut_correlation": correlation,
    }


# ── Beat alignment ─────────────────────────────────────────────────────

def _beat_alignment(
    boundaries: List[float],
    bpm: float,
    beat_interval: float,
) -> Tuple[float, float]:
    """Compute fraction of cuts that land near a beat grid position."""
    if not boundaries:
        return 0.0, 0.0

    sync_count = 0
    offsets: List[float] = []

    for cut_t in boundaries:
        # Find nearest beat position
        beat_idx = round(cut_t / beat_interval)
        nearest_beat = beat_idx * beat_interval
        offset = abs(cut_t - nearest_beat)
        offsets.append(offset)
        if offset < 0.08:  # ±80ms
            sync_count += 1

    sync_ratio = sync_count / len(boundaries)
    avg_offset = sum(offsets) / len(offsets)
    return sync_ratio, avg_offset


# ── Music structure ─────────────────────────────────────────────────────

def _music_structure(
    energy_curve: List[float],
    duration: float,
) -> Dict[str, Any]:
    """Detect energy rise/fall sections via moving-average slope.

    Returns list of {start, end, label} sections (intro, buildup, drop, outro).
    """
    if not energy_curve or duration <= 0:
        return {"sections": []}

    arr = np.asarray(energy_curve, dtype=float)
    n = len(arr)

    # Moving average smooth (window = ~2s worth of frames)
    window = max(3, n // 20) if n >= 6 else 3
    smoothed = np.convolve(arr, np.ones(window) / window, mode="same")

    # Compute first derivative (slope)
    if n < 6:
        return {"sections": []}

    slope = np.diff(smoothed)

    # Segment by slope sign
    sections: List[dict] = []
    i = 1
    while i < len(slope):
        t0 = float(i) / n * duration

        # Rising segment
        if slope[i] > 0.001:
            j = i
            while j < len(slope) and slope[j] > 0.001:
                j += 1
            t1 = float(j) / n * duration
            sections.append({"start": round(t0, 1), "end": round(t1, 1), "label": "能量上升"})
            i = j
        # Falling segment
        elif slope[i] < -0.001:
            j = i
            while j < len(slope) and slope[j] < -0.001:
                j += 1
            t1 = float(j) / n * duration
            sections.append({"start": round(t0, 1), "end": round(t1, 1), "label": "能量下降"})
            i = j
        else:
            i += 1

    return {"sections": sections[:10]}


# ── Energy-cut correlation ─────────────────────────────────────────────

def _energy_cut_correlation(
    energy_curve: List[float],
    boundaries: List[float],
    duration: float,
) -> Dict[str, Any]:
    """Compute Pearson correlation between energy level and cut count per bin."""
    if not energy_curve or not boundaries or duration <= 0:
        return {"pearson_r": 0.0, "bins": []}

    n_bins = 10
    bin_width = duration / n_bins
    energy_bins: List[float] = []
    cut_bins: List[float] = []

    arr = np.asarray(energy_curve, dtype=float)
    n_energy = len(arr)

    for b in range(n_bins):
        t0 = b * bin_width
        t1 = (b + 1) * bin_width

        # Average energy in bin
        i0 = int(t0 / duration * n_energy)
        i1 = int(t1 / duration * n_energy)
        i0 = max(0, min(i0, n_energy - 1))
        i1 = max(i0 + 1, min(i1, n_energy))
        avg_energy = float(np.mean(arr[i0:i1])) if i1 > i0 else 0.0

        # Cuts in bin
        cuts = sum(1 for bd in boundaries if t0 <= bd < t1)

        energy_bins.append(round(avg_energy, 4))
        cut_bins.append(cuts)

    # Pearson r
    r = _pearson(energy_bins, cut_bins)

    return {
        "pearson_r": round(r, 3),
        "bins": [
            {"energy": e, "cuts": c}
            for e, c in zip(energy_bins, cut_bins)
        ],
    }


def _pearson(x: List[float], y: List[float]) -> float:
    if len(x) < 3:
        return 0.0
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    mx, my = xa.mean(), ya.mean()
    num = ((xa - mx) * (ya - my)).sum()
    den = np.sqrt(((xa - mx) ** 2).sum() * ((ya - my) ** 2).sum())
    return float(num / den) if den > 1e-10 else 0.0
