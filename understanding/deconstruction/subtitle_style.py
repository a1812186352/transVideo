"""Subtitle style extraction — position, timing, duration, density.

Zero ML dependencies — pure arithmetic on OCR regions and transcript timestamps.

Extracts:
    - position distribution (top / center / bottom)
    - appearance timing (avg delay, sync ratio, lead ratio)
    - avg text duration (visible period estimate)
    - text density by structure segment type
    - sample texts (one per segment)
"""

from typing import Any, Dict, List, Optional


# ── Public API ─────────────────────────────────────────────────────────

def extract(
    signal_data: Dict[str, Any],
    structure_segments: Optional[List[Dict[str, Any]]] = None,
    keyframes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Extract subtitle style metrics from OCR data and transcripts.

    Args:
        signal_data: Pipeline signal-layer output with ``ocr_results``
            and ``transcript_segments``.
        structure_segments: Structure inferrer output (for per-type density).
        keyframes: Unused, reserved.

    Returns:
        Dict with: available, position_distribution, appearance_timing,
        avg_text_duration, density_by_segment, sample_texts.
    """
    ocr_results = signal_data.get("ocr_results", [])
    transcript_segments = signal_data.get("transcript_segments", [])

    if not ocr_results:
        return {"available": False}

    # Flatten: collect timed text regions
    timed_texts: List[dict] = []
    for ocr_item in ocr_results:
        ts = float(ocr_item.get("timestamp", -1))
        if ts < 0:
            continue
        for region in ocr_item.get("text_regions", []):
            text = ""
            bbox = None
            if isinstance(region, dict):
                text = region.get("text", "").strip()
                bbox_raw = region.get("bbox", None)
                if bbox_raw and isinstance(bbox_raw, list) and len(bbox_raw) >= 4:
                    # bbox format: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] or [x,y,w,h]
                    flat = _flatten_bbox(bbox_raw)
                    if flat:
                        bbox = flat
            if text:
                timed_texts.append({
                    "text": text,
                    "timestamp": ts,
                    "bbox": bbox,
                })

    if not timed_texts:
        return {"available": False}

    # ── 1. Position distribution ──
    position_distribution = _position_distribution(timed_texts)

    # ── 2. Appearance timing ──
    appearance_timing = _appearance_timing(timed_texts, transcript_segments)

    # ── 3. Avg text duration ──
    avg_duration = _avg_text_duration(timed_texts)

    # ── 4. Density by segment ──
    density_by_segment = _density_by_segment(timed_texts, structure_segments)

    # ── 5. Sample texts ──
    sample_texts = _collect_samples(timed_texts, structure_segments)

    return {
        "available": True,
        "position_distribution": position_distribution,
        "appearance_timing": appearance_timing,
        "avg_text_duration": round(avg_duration, 2),
        "density_by_segment": density_by_segment,
        "sample_texts": sample_texts,
    }


# ── Helpers ────────────────────────────────────────────────────────────

def _flatten_bbox(raw: list) -> Optional[tuple]:
    """Convert bbox list to (x, y, w, h) normalised 0-1.

    Handles two formats:
      4-point: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
      4-value: [x, y, w, h]
    """
    if not raw:
        return None
    if isinstance(raw[0], (list, tuple)):
        # 4-point polygon → bounding rect
        xs = [p[0] for p in raw]
        ys = [p[1] for p in raw]
        return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    if len(raw) >= 4:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return None


def _position_distribution(timed_texts: List[dict]) -> Dict[str, float]:
    """Fraction of texts in top / center / bottom thirds by centre y."""
    counts = {"top": 0, "center": 0, "bottom": 0}
    for t in timed_texts:
        bbox = t.get("bbox")
        if not bbox:
            continue
        _, y, _, h = bbox
        cy = y + h / 2
        if cy < 0.33:
            counts["top"] += 1
        elif cy > 0.67:
            counts["bottom"] += 1
        else:
            counts["center"] += 1
    total = max(sum(counts.values()), 1)
    return {k: round(v / total, 3) for k, v in counts.items()}


def _appearance_timing(
    timed_texts: List[dict],
    transcript_segments: List[dict],
) -> Dict[str, Any]:
    """Compute text-speech sync metrics."""
    delays: List[float] = []
    sync_in = 0
    lead_in = 0
    total = 0

    for t in timed_texts:
        ts = t["timestamp"]
        total += 1
        # Find nearest speech window
        best_delay = float("inf")
        in_window = False
        leads = False

        for seg in transcript_segments:
            s = float(seg.get("start", seg.get("start_time", 0)))
            e = float(seg.get("end", seg.get("end_time", 0)))
            if s <= ts <= e:
                in_window = True
                best_delay = ts - s
                break
            if ts < s:
                d = s - ts  # text appears before speech
                if d < best_delay:
                    best_delay = -d  # negative = lead
                    leads = True
            else:
                d = ts - e  # text appears after speech
                if d < abs(best_delay):
                    best_delay = d
                    leads = False

        if in_window:
            sync_in += 1
            delays.append(max(best_delay, 0))
        elif leads and best_delay != float("inf"):
            lead_in += 1
        elif best_delay != float("inf"):
            delays.append(best_delay)

    avg_delay = round(sum(delays) / max(len(delays), 1), 2)
    sync_ratio = round(sync_in / max(total, 1), 3)
    lead_ratio = round(lead_in / max(total, 1), 3)

    return {
        "avg_delay_after_speech": avg_delay,
        "sync_ratio": sync_ratio,
        "lead_ratio": lead_ratio,
    }


def _avg_text_duration(timed_texts: List[dict]) -> float:
    """Estimate avg text visible duration from timestamp deltas."""
    if len(timed_texts) < 2:
        return 0.0
    sorted_ts = sorted(t["timestamp"] for t in timed_texts)
    gaps = [sorted_ts[i + 1] - sorted_ts[i] for i in range(len(sorted_ts) - 1)]
    # Filter unrealistic gaps (> 10s = scene change, not text duration)
    gaps = [g for g in gaps if g < 10.0]
    return float(sum(gaps) / max(len(gaps), 1)) if gaps else 0.0


def _density_by_segment(
    timed_texts: List[dict],
    structure_segments: Optional[List[dict]],
) -> Dict[str, float]:
    """OCR texts per second by structure segment type."""
    result: Dict[str, float] = {}
    if not structure_segments:
        return result

    for seg in structure_segments:
        seg_type = seg.get("structure_type", "unclassified")
        t0 = seg.get("start_time", 0.0)
        t1 = seg.get("end_time", t0)
        dur = max(t1 - t0, 0.01)
        count = sum(1 for t in timed_texts if t0 <= t["timestamp"] <= t1)
        rate = round(count / dur, 3)
        result[seg_type] = max(result.get(seg_type, 0), rate)

    return result


def _collect_samples(
    timed_texts: List[dict],
    structure_segments: Optional[List[dict]],
) -> List[str]:
    """Collect one sample text per structure segment type."""
    if not structure_segments:
        texts = [t["text"] for t in timed_texts if len(t["text"]) >= 2]
        return texts[:5]

    seen: set = set()
    samples: List[str] = []
    for seg in structure_segments:
        seg_type = seg.get("structure_type", "")
        if seg_type in seen:
            continue
        t0 = seg.get("start_time", 0.0)
        t1 = seg.get("end_time", t0)
        for t in timed_texts:
            if t0 <= t["timestamp"] <= t1 and len(t["text"]) >= 2:
                samples.append(t["text"])
                seen.add(seg_type)
                break
    return samples[:10]
