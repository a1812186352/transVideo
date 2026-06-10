"""Module normaliser — eliminate gaps and overlaps in the module timeline.

Three-step pipeline applied after module classification:
    1. Remove overlaps — truncate preceding module at next module's start.
    2. Fill gaps — insert ``content`` modules for uncovered intervals.
    3. Generate content descriptions — brief textual summary for content modules.
"""

from typing import Any, Dict, List, Optional

from understanding.pipeline_config import MODULE_TYPE_CONTENT

# ── Public API ─────────────────────────────────────────────────────────

def normalize(
    modules: List[Dict[str, Any]],
    total_duration: float = 0.0,
) -> List[Dict[str, Any]]:
    """Normalize a module list: remove overlaps, fill gaps, add descriptions.

    Args:
        modules: Sorted list of module dicts (by ``start_time``).
        total_duration: Total video duration (for head/tail gap detection).

    Returns:
        Normalized module list — contiguous, non-overlapping, fully covered.
    """
    if not modules:
        return []

    # Ensure sorted by start_time
    modules.sort(key=lambda m: m.get("start_time", 0.0))

    # ── Step 1: Remove overlaps ──
    modules = _remove_overlaps(modules)

    # ── Step 2: Fill gaps ──
    modules = _fill_gaps(modules, total_duration)

    # ── Step 3: Generate content descriptions ──
    modules = _describe_content_modules(modules)

    return modules


# ── Step 1: Overlap removal ────────────────────────────────────────────

def _remove_overlaps(
    modules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Truncate preceding modules that overlap into the next module's start."""
    result: List[Dict[str, Any]] = []

    for i, mod in enumerate(modules):
        mod = dict(mod)  # shallow copy to avoid mutating input
        start = mod.get("start_time", 0.0)
        duration = mod.get("duration", 0.0)
        end = start + duration

        # Truncate if next module starts earlier
        if i < len(modules) - 1:
            next_start = modules[i + 1].get("start_time", float("inf"))
            if end > next_start:
                end = next_start
                duration = end - start
                mod["duration"] = max(duration, 0.0)

        if mod["duration"] > 0.05:  # skip degenerate
            result.append(mod)

    return result


# ── Step 2: Gap filling ────────────────────────────────────────────────

def _fill_gaps(
    modules: List[Dict[str, Any]],
    total_duration: float,
) -> List[Dict[str, Any]]:
    """Insert content modules for uncovered time intervals."""
    if not modules:
        if total_duration > 0:
            return [_make_content_module(0.0, total_duration)]
        return []

    result: List[Dict[str, Any]] = []

    # Head gap (before first module)
    first_start = modules[0].get("start_time", 0.0)
    if first_start > 0.05:
        result.append(_make_content_module(0.0, first_start))

    # Inter-module gaps
    for i in range(len(modules)):
        result.append(modules[i])
        if i < len(modules) - 1:
            cur_end = modules[i].get("start_time", 0.0) + modules[i].get("duration", 0.0)
            next_start = modules[i + 1].get("start_time", 0.0)
            gap = next_start - cur_end
            if gap > 0.05:
                result.append(_make_content_module(cur_end, next_start))

    # Tail gap (after last module)
    last_end = (modules[-1].get("start_time", 0.0) +
                modules[-1].get("duration", 0.0))
    if total_duration > 0 and (total_duration - last_end) > 0.05:
        result.append(_make_content_module(last_end, total_duration))

    return result


def _make_content_module(start: float, end: float) -> Dict[str, Any]:
    import uuid
    duration = end - start
    return {
        "id": uuid.uuid4().hex[:12],
        "type": MODULE_TYPE_CONTENT,
        "label": f"content_{start:.1f}s",
        "start_time": start,
        "duration": duration,
        "track_index": 0,
        "children": [],
        "detail": {
            "sub_type": "内容",
            "scene_tags": ["内容"],
            "brief_description": "",
        },
    }


# ── Step 3: Content descriptions ───────────────────────────────────────

def _describe_content_modules(
    modules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate a brief text description for every content-type module."""
    for mod in modules:
        if mod.get("type") != MODULE_TYPE_CONTENT:
            continue
        detail = mod.get("detail") or {}
        if detail.get("brief_description"):
            continue  # already has one

        # Priority: voice → OCR → visual → fallback
        desc = ""
        voice = detail.get("voice_content", "")
        if voice and voice != "无":
            desc = voice[:20] + ("..." if len(voice) > 20 else "")
        else:
            ocr = (detail.get("ocr_texts") or [])
            if ocr:
                desc = "文字: " + " ".join(ocr)[:15]
            else:
                vis = detail.get("visual_elements") or []
                if vis:
                    filtered = [v for v in vis if not v.startswith(("光照", "色彩"))]
                    if filtered:
                        desc = filtered[0][:30]
        if not desc:
            desc = "环境空镜 / 常规画面"

        detail["brief_description"] = desc
        mod["detail"] = detail
    return modules
