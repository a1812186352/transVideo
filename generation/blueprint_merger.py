"""Blueprint merger — template preset × module_tree → generation blueprint.

Strategy: template dominates, deconstruction fills gaps.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from generation.blueprint_templates import (
    TEMPLATE_PRESETS, TEMPLATE_KEY_TO_ENDS,
)

_log = logging.getLogger(__name__)


def merge(
    template_type: str,
    module_tree: List[Dict[str, Any]],
    total_duration: float = 0.0,
) -> Dict[str, Any]:
    """Merge template preset with deconstructed module tree.

    Args:
        template_type: One of ``product_review``, ``shopping_live``,
            ``talking_head``, ``mashup``, ``none``.
        module_tree: Pipeline output modules (normalized, with detail).
        total_duration: Total video duration in seconds (for ratio calc).

    Returns:
        BlueprintResult dict with ``template``, ``blocks``, ``summary``.
    """
    preset = TEMPLATE_PRESETS.get(template_type)
    if not preset:
        return {"template": template_type, "blocks": [], "summary": {"block_count": 0}}

    # ── Pass-through mode: no template, use module tree as-is ──
    if preset.get("pass_through"):
        return _build_pass_through(module_tree, total_duration)

    template_modules = preset.get("modules", [])
    total_dur = _resolve_total_dur(module_tree, total_duration)

    # ── Step 1: Match template slots to module_tree modules ──
    matched_mod_indices: set = set()
    blocks: List[Dict[str, Any]] = []

    for tpl_mod in template_modules:
        match_idx, match_mod = _find_best_match(tpl_mod, module_tree, matched_mod_indices)
        if match_idx is not None:
            matched_mod_indices.add(match_idx)
            blocks.append({
                "name": tpl_mod["name"],
                "template_key": tpl_mod["key"],
                "start_time": match_mod.get("start_time", 0.0),
                "duration": match_mod.get("duration", tpl_mod["default_dur"]),
                "status": "matched",
                "source_module": match_mod.get("id"),
                "detail": match_mod.get("detail"),
                "required": tpl_mod.get("required", False),
            })
        else:
            blocks.append({
                "name": tpl_mod["name"],
                "template_key": tpl_mod["key"],
                "start_time": 0.0,       # will be recalculated
                "duration": tpl_mod["default_dur"],
                "status": "missing",
                "required": tpl_mod.get("required", False),
            })

    # ── Step 2: Append unmatched modules as "passthrough" content ──
    for i, mod in enumerate(module_tree):
        if i in matched_mod_indices:
            continue
        dur = mod.get("duration", 0.0)
        if dur > 0:  # skip zero-duration modules
            blocks.append({
                "name": mod.get("label") or mod.get("detail", {}).get("semantic_label", "片段"),
                "template_key": "",
                "start_time": mod.get("start_time", 0.0),
                "duration": dur,
                "status": "passthrough",
                "source_module": mod.get("id"),
                "detail": mod.get("detail"),
                "required": False,
            })

    # ── Step 3: Sort blocks into template order (matched first, then passthrough) ──
    blocks.sort(key=lambda b: (
        _template_key_order(b.get("template_key"), template_modules),
        b.get("start_time", 0.0),
    ))

    # ── Step 4: Recalculate start_times sequentially ──
    cursor = 0.0
    for b in blocks:
        b["start_time"] = round(cursor, 2)
        cursor += b.get("duration", 0.0)

    # ── Step 5: Build summary ──
    match_count = sum(1 for b in blocks if b["status"] == "matched")
    missing_count = sum(1 for b in blocks if b["status"] == "missing")
    required_missing = [b["name"] for b in blocks if b["status"] == "missing" and b.get("required")]

    return {
        "template": {
            "type": template_type,
            "label": preset.get("label", template_type),
        },
        "blocks": blocks,
        "summary": {
            "block_count": len(blocks),
            "total_duration": round(cursor, 2),
            "matched": match_count,
            "missing": missing_count,
            "passthrough": len(blocks) - match_count - missing_count,
            "required_missing": required_missing,
        },
    }


# ═══════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════

def _resolve_total_dur(modules: List[Dict], fallback: float) -> float:
    if fallback > 0:
        return fallback
    if not modules:
        return 60.0
    return max(m.get("start_time", 0) + m.get("duration", 0) for m in modules)


def _find_best_match(
    tpl_mod: Dict[str, Any],
    modules: List[Dict[str, Any]],
    used_indices: set,
) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """Find the best module matching a template slot."""
    keywords = TEMPLATE_KEY_TO_ENDS.get(tpl_mod["key"], [])
    best_idx: Optional[int] = None
    best_score = 0.0

    for i, mod in enumerate(modules):
        if i in used_indices:
            continue
        score = _match_score(mod, keywords)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_idx is not None and best_score >= 1.0:
        return best_idx, modules[best_idx]
    return None, None


def _match_score(mod: Dict[str, Any], keywords: List[str]) -> float:
    """Score how well a module matches a set of keywords."""
    detail = mod.get("detail") or {}
    sub_type = detail.get("sub_type", "")
    scene_tags = detail.get("scene_tags") or []
    label = mod.get("label", "")
    semantic_label = detail.get("semantic_label", "")

    texts = [sub_type, label, semantic_label] + list(scene_tags)
    score = 0.0
    for kw in keywords:
        kw_lower = kw.lower()
        for t in texts:
            if not isinstance(t, str):
                continue
            if kw_lower in t.lower():
                score += 1.0
                break
    return score


def _template_key_order(key: str, template_modules: List[Dict]) -> int:
    """Return the position of a template key in the preset order."""
    for i, m in enumerate(template_modules):
        if m.get("key") == key:
            return i
    return 999


def _build_pass_through(
    module_tree: List[Dict[str, Any]], total_dur: float,
) -> Dict[str, Any]:
    """Build a pass-through blueprint (no template applied)."""
    blocks = []
    for mod in module_tree:
        dur = mod.get("duration", 0.0)
        if dur > 0:
            blocks.append({
                "name": mod.get("label") or mod.get("detail", {}).get("semantic_label", "片段"),
                "template_key": "",
                "start_time": mod.get("start_time", 0.0),
                "duration": dur,
                "status": "passthrough",
                "source_module": mod.get("id"),
                "detail": mod.get("detail"),
                "required": False,
            })
    return {
        "template": {"type": "none", "label": "无预设"},
        "blocks": blocks,
        "summary": {
            "block_count": len(blocks),
            "total_duration": total_dur or _resolve_total_dur(module_tree, 0.0),
            "matched": 0,
            "missing": 0,
            "passthrough": len(blocks),
            "required_missing": [],
        },
    }
