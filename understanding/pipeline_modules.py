"""Module tree builder — structure segments → typed module list with detail.

Exported functions:
    build_module_tree(...)  — convert structure segments into track-aware modules
    detect_watermarks(...)  — global watermark scan across segments
"""

import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from understanding.pipeline_config import WATERMARK_SEG_RATIO, WATERMARK_MIN_SEGS
from understanding.pipeline_detail import build_detail


def detect_watermarks(
    structure_segments: List[dict],
    ocr_data: List[dict],
) -> Set[str]:
    """Detect watermark text by checking cross-segment frequency.

    A text is considered a watermark if it appears in >= max(2, 40%) of
    all structure segments.

    Returns:
        Set of watermark strings to exclude from per-segment analysis.
    """
    ocr_seg_map: Dict[str, set] = defaultdict(set)
    for si, seg in enumerate(structure_segments):
        s0 = seg.get("start_time", 0.0)
        s1 = seg.get("end_time", s0)
        for ocr in ocr_data:
            ts = ocr.get("timestamp", -1)
            if ts < 0 or ts < s0 or ts > s1:
                continue
            for region in ocr.get("text_regions", []):
                t = region.get("text", "") if isinstance(region, dict) else str(region)
                t = t.strip()
                if t:
                    ocr_seg_map[t].add(si)

    num_segs = max(len(structure_segments), 1)
    threshold = max(WATERMARK_MIN_SEGS, int(num_segs * WATERMARK_SEG_RATIO))
    return {t for t, segs in ocr_seg_map.items() if len(segs) >= threshold}


def build_module_tree(
    structure_segments: List[dict],
    transcripts: List[dict],
    energy: List[float],
    dur_total: float,
    bpm: float,
    ocr_data: List[dict],
    video_path: str = "",
    visual_features: Optional[List[dict]] = None,
    audio_data: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Convert structure segments into a 5-type module tree with detail.

    Each module includes a ``detail`` dict with per-segment analysis
    extracted from real signal data (transcript, energy, OCR, BPM).

    Args:
        structure_segments: Output of StructureInferrer.infer().
        transcripts: ASR transcript segments.
        energy: Energy curve (RMS or pixel diff).
        dur_total: Total video duration in seconds.
        bpm: BPM from audio analysis.
        ocr_data: OCR results with timestamps.
        video_path: Source video path (for source refs).
        visual_features: Visual feature dicts from analysis.
        audio_data: Full audio analysis dict (mood, etc.).

    Returns:
        List of module dicts with ``type``, ``track_index``, ``detail``.
    """
    modules: List[Dict[str, Any]] = []

    # ── Global watermark scan ──
    watermark_set = detect_watermarks(structure_segments, ocr_data)

    for i, seg in enumerate(structure_segments):
        seg_type = seg.get("structure_type", "unclassified")
        seg_label = seg.get("label", f"segment_{i}")
        start_time = seg.get("start_time", 0.0)
        end_time = seg.get("end_time", start_time)
        duration = max(end_time - start_time, 0.0)
        evidence = seg.get("evidence", [])
        sub_type = seg.get("sub_type", "")

        # Build per-module detail from signals
        detail = build_detail(
            seg_type=seg_type,
            sub_type=sub_type,
            start=start_time,
            end=end_time,
            duration=duration,
            evidence=evidence,
            transcripts=transcripts,
            energy=energy,
            total_dur=dur_total,
            bpm=bpm,
            ocr_data=ocr_data,
            visual_features=visual_features,
            audio_data=audio_data,
            watermark_set=watermark_set,
        )

        base = {
            "id": uuid.uuid4().hex[:12],
            "start_time": start_time,
            "duration": duration,
            "label": seg_label,
            "children": [],
            "detail": detail,
        }

        # ── Segment type → module type mapping ──
        if seg_type == "opening":
            modules.append({
                **base, "track_index": 1, "type": "title",
                "params": {"text_content": seg_label, "animation": "fade_in"},
            })
        elif seg_type == "highlight":
            modules.append({
                **base, "track_index": 0, "type": "video_segment",
                "source": {"type": "video", "path": video_path},
            })
        elif seg_type == "transition":
            modules.append({
                **base, "track_index": 0, "type": "transition",
                "params": {"transition_type": "dissolve"},
            })
        elif seg_type == "effect":
            modules.append({
                **base, "track_index": 3, "type": "effect",
                "params": {"transition_type": "fade"},
            })
        elif seg_type == "closing":
            modules.append({
                **base, "track_index": 0, "type": "video_segment",
            })
            modules.append({
                **base, "track_index": 3, "type": "effect",
                "label": f"{seg_label}_outro",
                "params": {"transition_type": "fade_out"},
            })
        else:
            modules.append({
                **base, "track_index": 0, "type": "video_segment",
            })

    return modules
