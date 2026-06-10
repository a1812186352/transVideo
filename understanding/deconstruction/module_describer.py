"""Module describer — synthesise human-readable segment labels + descriptions.

Pure rule-engine: reads per-module ``detail`` dicts and produces
``semantic_label``, ``time_range``, and ``description`` fields by
composing existing signal fields without any LLM call.

Three-tier fallback for semantic labels:
    1. ``sub_type`` → ``SUB_TYPE_*`` mapping table (Chinese label)
    2. ``scene_tags[0]`` (first content tag)
    3. Position heuristic (opening / closing / segment-N)
"""

from typing import Any, Dict, List, Optional

from understanding.pipeline_config import (
    CONTENT_LABEL_MAP, SCENE_TAG_MAP, MOTION_LABEL_RULES,
    SUB_TYPE_OPENING, SUB_TYPE_HIGHLIGHT,
    SUB_TYPE_TRANSITION, SUB_TYPE_CLOSING, SUB_TYPE_EFFECT,
)

# ── Unified sub-type → Chinese label map (English keys only) ──
_SUB_TYPE_MAP: Dict[str, str] = {}
_SUB_TYPE_MAP.update(SUB_TYPE_OPENING)
_SUB_TYPE_MAP.update(SUB_TYPE_HIGHLIGHT)
_SUB_TYPE_MAP.update(SUB_TYPE_TRANSITION)
_SUB_TYPE_MAP.update(SUB_TYPE_CLOSING)
_SUB_TYPE_MAP.update(SUB_TYPE_EFFECT)


def describe(module: dict, index: int = 0, total_count: int = 1) -> Dict[str, Any]:
    """Produce semantic label, time range, and description for one module.

    Args:
        module: Module dict with ``detail``, ``start_time``, ``duration``,
            ``type`` fields.
        index: Position in module list.
        total_count: Total number of modules (for last-segment detection).

    Returns:
        Dict with ``semantic_label``, ``time_range``, ``description``.
    """
    detail = module.get("detail") or {}
    seg_type = module.get("type", "")

    # ── 1. Semantic label ──
    semantic_label = _resolve_label(detail, seg_type, index, total_count)

    # ── 2. Time range ──
    t0 = module.get("start_time", 0.0)
    dur = module.get("duration", 0.0)
    time_range = f"{t0:.1f}s-{t0 + dur:.1f}s"

    # ── 3. Description ──
    description = _build_description(detail, seg_type, dur)

    return {
        "semantic_label": semantic_label,
        "time_range": time_range,
        "description": description,
    }


# ── Label resolution ───────────────────────────────────────────────────

# ── 6-label map: module type → display label ──

_MODULE_TYPE_LABEL = {
    "title":          "开头",
    "video_segment":  "高潮",
    "transition":     "转场",
    "effect":         "特效",
    "content":        "内容",
    "closing":        "结尾",
}


def _resolve_label(detail: dict, seg_type: str, index: int, total_count: int) -> str:
    """6-label system: 开头/高潮/转场/特效/内容/结尾."""
    if index == 0:
        return "开头"
    if index >= total_count - 1:
        return "结尾"
    return _MODULE_TYPE_LABEL.get(seg_type, "内容")

    return "内容"


# ── Description builder ─────────────────────────────────────────────────

def _build_description(detail: dict, seg_type: str, duration: float) -> str:
    """Compose a readable description from detail fields, per module type."""
    # Short modules get a fixed label
    if duration < 0.5:
        return "闪切过渡"

    if seg_type in ("title",):
        return _describe_opening(detail)
    elif seg_type in ("video_segment",):
        return _describe_highlight(detail)
    elif seg_type in ("transition",):
        return _describe_transition(detail)
    elif seg_type in ("effect",):
        return _describe_effect(detail)
    elif seg_type in ("closing",):
        return _describe_closing(detail)
    else:
        return _describe_content(detail)


def _describe_opening(detail: dict) -> str:
    parts: List[str] = []
    scene_tags = detail.get("scene_tags") or []
    if scene_tags:
        parts.append("，".join(scene_tags[:2]))
    ocr = (detail.get("ocr_texts") or [])
    if ocr:
        parts.append("文字: " + " ".join(ocr[:2]))
    return "，".join(parts) if parts else "片头画面"


def _describe_highlight(detail: dict) -> str:
    parts: List[str] = []
    vis = detail.get("visual_elements") or []
    if vis:
        # Keep only content-like items (skip light/color/tone)
        filtered = [v for v in vis if not v.startswith(("光照", "色彩", "构图"))]
        if filtered:
            parts.append("，".join(filtered[:2]))
    motion = detail.get("motion", "")
    if motion and motion != "无":
        # Truncate at first comma for brevity
        short = motion.split("，")[0].split("｜")[0].strip()
        if short:
            parts.append(short)
    ep = detail.get("emotion_peak", "")
    if ep and ep != "无":
        parts.append(f"情绪{ep}")
    return "，".join(parts) if parts else "精彩片段"


def _describe_transition(detail: dict) -> str:
    motion = detail.get("motion", "")
    if motion and motion != "无":
        short = motion.split("，")[0].split("｜")[0].strip()
        if short:
            return short
    return "转场过渡"


def _describe_effect(detail: dict) -> str:
    parts: List[str] = []
    motion = detail.get("motion", "")
    if motion and motion != "无":
        short = motion.split("，")[0].split("｜")[0].strip()
        if short:
            parts.append(short)
    vis = detail.get("visual_elements") or []
    if vis:
        filtered = [v for v in vis if not v.startswith(("光照", "色彩"))]
        parts.append("，".join(filtered[:1]))
    return "，".join(parts) if parts else "视觉特效"


def _describe_closing(detail: dict) -> str:
    parts: List[str] = []
    voice = detail.get("voice_content", "")
    if voice and voice != "无":
        parts.append(voice[:20] + ("..." if len(voice) > 20 else ""))
    ocr = (detail.get("ocr_texts") or [])
    if ocr:
        parts.append("文字: " + " ".join(ocr[:2]))
    scene_tags = detail.get("scene_tags") or []
    if scene_tags:
        parts.append("，".join(scene_tags[:2]))
    return "，".join(parts) if parts else "片尾画面"


def _describe_content(detail: dict) -> str:
    """Content module: brief from voice/OCR/visual, or neutral fallback."""
    brief = detail.get("brief_description", "")
    if brief:
        return brief
    voice = detail.get("voice_content", "")
    if voice and voice != "无":
        return voice[:30] + ("..." if len(voice) > 30 else "")
    ocr = (detail.get("ocr_texts") or [])
    if ocr:
        return "文字: " + " ".join(ocr[:2])
    return "常规画面"
