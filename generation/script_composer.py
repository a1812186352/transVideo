"""Script composer — module list → structured script with per-type templates.

Produces a rich script object (not just modules) with human-readable
descriptions, timing blocks, and export-ready structure.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════
#  Template definitions — one per module type
# ═══════════════════════════════════════════════════════

@dataclass
class ScriptBlock:
    """A single rendered script block for one module."""
    module_id: str
    module_type: str          # title / video_segment / transition / ...
    structure_type: str       # opening / highlight / transition / ...
    order: int                # 0-based in composed sequence
    start_time: float         # seconds from timeline start
    end_time: float
    duration: float
    label: str
    content_tags: List[str] = field(default_factory=list)
    content_description: str = ""   # human-readable paragraph
    template_params: Dict[str, Any] = field(default_factory=dict)


# ── Template definitions ──

TYPE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "title": {
        "label": "片头标题",
        "description": "视频开场标题片段",
        "structure_type": "opening",
        "layout": "center_text",
        "animation": "fade_in",
        "default_duration": 5.0,
    },
    "video_segment": {
        "label": "视频片段",
        "description": "原始视频高光片段",
        "structure_type": "highlight",
        "layout": "full_screen",
        "animation": None,
        "default_duration": 8.0,
    },
    "subtitle": {
        "label": "字幕叠加",
        "description": "叠加字幕文字内容",
        "structure_type": "content",
        "layout": "bottom_text",
        "animation": "slide_up",
        "default_duration": 3.0,
    },
    "transition": {
        "label": "转场效果",
        "description": "模块间过渡转场",
        "structure_type": "transition",
        "layout": "overlay",
        "animation": "crossfade",
        "default_duration": 1.5,
    },
    "audio": {
        "label": "音频段落",
        "description": "背景音乐或音效段落",
        "structure_type": "content",
        "layout": "audio_only",
        "animation": None,
        "default_duration": 5.0,
    },
    "effect": {
        "label": "视觉特效",
        "description": "叠层特效或滤镜",
        "structure_type": "effect",
        "layout": "overlay",
        "animation": "scale_up",
        "default_duration": 1.0,
    },
}


# ═══════════════════════════════════════════════════════
#  Composer
# ═══════════════════════════════════════════════════════

def compose_script(
    modules: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    video_path: str = "",
) -> Dict[str, Any]:
    """Build a rich composed script from a list of modules.

    Each module is expanded into a ``ScriptBlock`` with template
    parameters, descriptive content, and timing info.  The output
    is a structured dict ready for export or rendering.

    Args:
        modules: List of module dicts (as from timeline store).
        metadata: Optional project metadata dict.
        video_path: Source video path for source references.

    Returns:
        Composed script dict with ``blocks`` and ``summary``.
    """
    meta = metadata or {}
    blocks: List[Dict[str, Any]] = []

    # ── Recalculate cumulative timeline ──
    # Modules already have start_time; compute end_time per block.
    cumulative = 0.0

    for i, mod in enumerate(modules):
        mod_type = mod.get("type", "video_segment")
        mod_start = mod.get("start_time", cumulative)
        mod_dur = mod.get("duration", 3.0)

        # Template lookup
        tpl = TYPE_TEMPLATES.get(mod_type, TYPE_TEMPLATES["video_segment"])
        detail = mod.get("detail", {})

        # Content description — assemble from detail signals
        content_desc_parts: List[str] = []
        if detail.get("voice_content"):
            voice = detail["voice_content"]
            if isinstance(voice, str) and voice.strip() and voice.strip() != "无":
                content_desc_parts.append(f"配音: {voice.strip()}")
        if detail.get("motion") and detail["motion"] != "无":
            content_desc_parts.append(f"运镜: {detail['motion']}")
        if detail.get("color_tone") and detail["color_tone"] != "未知":
            content_desc_parts.append(f"色调: {detail['color_tone']}")
        if detail.get("bgm_type") and detail.get("bgm_type") not in ("无", "未知", ""):
            content_desc_parts.append(f"背景乐: {detail['bgm_type']}")
        tags = detail.get("content_tags", [])
        if isinstance(tags, list) and tags:
            content_desc_parts.insert(0, " · ".join(tags[:3]))

        desc = "；".join(content_desc_parts) if content_desc_parts else tpl["description"]

        # Template params
        params: Dict[str, Any] = {
            "layout": tpl["layout"],
            "animation": tpl["animation"],
            "source": mod.get("source", {}),
        }
        if mod_type == "title":
            params["text"] = mod.get("label", meta.get("title", "未命名"))
        if mod_type == "video_segment":
            o_start = detail.get("original_start", mod_start)
            o_end = detail.get("original_end", mod_start + mod_dur)
            params["source_start"] = o_start
            params["source_end"] = o_end
            params["source_path"] = mod.get("source", {}).get("path", video_path)
        if mod.get("params", {}).get("transition_type"):
            params["transition_type"] = mod["params"]["transition_type"]

        blocks.append({
            "module_id": mod.get("id", ""),
            "order": i,
            "module_type": mod_type,
            "structure_type": tpl["structure_type"],
            "start_time": round(mod_start, 2),
            "end_time": round(mod_start + mod_dur, 2),
            "duration": round(mod_dur, 2),
            "label": mod.get("label", tpl["label"]),
            "content_tags": tags if isinstance(tags, list) else [],
            "content_description": desc,
            "template_params": params,
        })

        cumulative = mod_start + mod_dur

    total_dur = round(cumulative, 2)

    # ── Summary ──
    structure_counts: Dict[str, int] = {}
    for b in blocks:
        key = b["structure_type"]
        structure_counts[key] = structure_counts.get(key, 0) + 1

    return {
        "version": "1.0.0",
        "metadata": {
            "title": meta.get("title", "未命名项目"),
            "total_duration": total_dur,
            "block_count": len(blocks),
            "structure_summary": structure_counts,
        },
        "blocks": blocks,
        # ═══ Serialisation fields ═══
        "tracks": _build_tracks(blocks),
        "modules": _collect_modules(modules),
    }


# ── Transforms ──

def _build_tracks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group blocks into tracks by type."""
    track_map: Dict[str, List[Dict[str, Any]]] = {}
    for b in blocks:
        tp = b["module_type"]
        track_map.setdefault(tp, []).append(b)
    tracks = []
    idx = 0
    for tp in ("title", "video_segment", "subtitle", "transition", "audio", "effect"):
        if tp in track_map:
            tracks.append({"index": idx, "name": tp, "type": tp, "blocks": track_map[tp]})
            idx += 1
    return tracks


def _collect_modules(modules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip detail for lighter serialization."""
    result = []
    for mod in modules:
        entry = {k: v for k, v in mod.items() if k != "detail"}
        tags = mod.get("detail", {}).get("content_tags", [])
        if tags:
            entry["content_tags"] = tags
        result.append(entry)
    return result
