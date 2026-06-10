"""Module tree builder — structure segments → typed module list with detail.

Exported functions:
    build_module_tree(...)  — convert structure segments into track-aware modules
    detect_watermarks(...)  — global watermark scan across segments
    deduplicate_modules(...) — merge redundant sibling modules
"""

import json
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
    video_type: str = "vlog",
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

    # Track previous segment's motion for inter-module trend
    prev_motion: Optional[Dict[str, Any]] = None

    for i, seg in enumerate(structure_segments):
        seg_type = seg.get("structure_type", "unclassified")
        seg_label = seg.get("label", f"片段{i + 1}")
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
            video_type=video_type,
            prev_motion=prev_motion,
        )

        # ── Allocate transcripts and OCR to this module's time window ──
        contained_transcript: List[str] = []
        for seg in transcripts:
            s = seg.get("start", seg.get("start_time", 0))
            e = seg.get("end", seg.get("end_time", 0))
            if max(s, start_time) < min(e, end_time):
                text = seg.get("text", "").strip()
                if text:
                    contained_transcript.append(text)

        contained_ocr: List[str] = []
        for ocr in ocr_data:
            ts = ocr.get("timestamp", -1)
            if ts < 0 or ts < start_time or ts > end_time:
                continue
            for region in ocr.get("text_regions", []):
                t = ""
                if isinstance(region, dict):
                    t = region.get("text", "")
                elif isinstance(region, str):
                    t = region
                if t and (not watermark_set or t not in watermark_set):
                    contained_ocr.append(t)

        # Save current motion for next iteration
        prev_motion = detail.get("motion_description")

        base = {
            "id": uuid.uuid4().hex[:12],
            "start_time": start_time,
            "duration": duration,
            "label": seg_label,
            "children": [],
            "detail": detail,
            "contained_transcript": contained_transcript,
            "contained_ocr": contained_ocr,
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
                "params": {"transition_type": "fade_out"},
            })
        else:
            modules.append({
                **base, "track_index": 0, "type": "video_segment",
            })

    # ── Dedup: merge redundant video_segment + effect pairs ──
    modules = deduplicate_modules(modules)

    # ── ModuleNormalizer: remove overlaps + fill gaps (runs first) ──
    try:
        from understanding.deconstruction.module_normalizer import normalize
        modules = normalize(modules, total_duration=dur_total)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Module normalizer failed: %s", exc)

    # ── ModuleDescriber: runs AFTER normalize so all modules get labels ──
    try:
        from understanding.deconstruction.module_describer import describe
        for i, mod in enumerate(modules):
            desc = describe(mod, index=i, total_count=len(modules))
            detail = mod.get("detail") or {}
            detail["semantic_label"] = desc["semantic_label"]
            detail["description"] = desc["description"]
            detail["time_range"] = desc["time_range"]
            mod["detail"] = detail
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Module describer failed: %s", exc)

    return modules


# ═══════════════════════════════════════════════════════════════════
#  Module deduplication — merge same-segment video_segment + effect
# ═══════════════════════════════════════════════════════════════════

def _detail_key(detail: Optional[Dict[str, Any]]) -> str:
    """Deterministic JSON representation of detail for equality checks."""
    if detail is None:
        return "null"
    return json.dumps(detail, sort_keys=True, ensure_ascii=False, default=str)


def deduplicate_modules(
    modules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge redundant sibling modules that share the same segment.

    When a single structure segment produces **both** a ``video_segment``
    and an ``effect`` module at the same ``(start_time, duration)`` with
    identical ``detail``, the effect is considered a rendering embellishment
    of the video segment rather than a standalone module.

    Merging rules
    -------------
    - The ``video_segment`` is kept as the primary module.
    - The ``effect``'s ``params`` are moved into a new
      ``extra_params`` field on the primary module.
    - The ``effect`` module is dropped from the list.
    - Independent effects (different time, different detail) are
      preserved as-is.

    Returns:
        A new module list with redundant pairs merged.
    """
    if len(modules) < 2:
        return modules

    # ── Group modules by (start_time, duration) bucket ──
    bucket: Dict[tuple, List[Dict[str, Any]]] = {}
    bucket_order: List[tuple] = []  # preserve insertion order

    for m in modules:
        key = (m.get("start_time", 0.0), m.get("duration", 0.0))
        if key not in bucket:
            bucket[key] = []
            bucket_order.append(key)
        bucket[key].append(m)

    # ── Process each bucket ──
    result: List[Dict[str, Any]] = []

    for key in bucket_order:
        group = bucket[key]

        if len(group) == 1:
            result.append(group[0])
            continue

        # Collect modules by type within this time bucket
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for m in group:
            t = m.get("type", "unknown")
            by_type.setdefault(t, []).append(m)

        # ── Merge: exactly one video_segment + one effect, same detail ──
        videos = by_type.get("video_segment", [])
        effects = by_type.get("effect", [])

        merged_effect_indices: Set[int] = set()

        for vi, video in enumerate(videos):
            video_dk = _detail_key(video.get("detail"))
            for ei, effect in enumerate(effects):
                if ei in merged_effect_indices:
                    continue
                effect_dk = _detail_key(effect.get("detail"))
                if video_dk == effect_dk:
                    # Merge: effect params → video.extra_params
                    eff_params = effect.get("params") or {}
                    if eff_params:
                        existing_extra = video.get("extra_params") or {}
                        video["extra_params"] = {**existing_extra, **eff_params}
                    merged_effect_indices.add(ei)
                    break  # one effect per video_segment

        # ── Emit: all video_segments, non-merged effects, other types ──
        for m in group:
            t = m.get("type", "unknown")
            if t == "effect":
                # Only emit effects that weren't merged
                ei = effects.index(m) if m in effects else -1
                if ei in merged_effect_indices:
                    continue
            result.append(m)

    return result
