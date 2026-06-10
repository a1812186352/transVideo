"""Visual packaging extraction — color style, composition, objects, packaging.

Zero ML — pure arithmetic on per-frame visual features (saturation, brightness,
edge density, grayscale entropy, YOLO counts, optical flow).

Extracts:
    - color_style (saturation level, tone, contrast)
    - composition (preference, face_frame_ratio, avg_edge_density)
    - object_distribution (avg person / vehicle / animal per frame)
    - packaging_elements (title_card_ratio, pure_background_ratio, packaged_ratio)
    - brightness_stats (min, max, avg)
"""

from typing import Any, Dict, List, Optional


# ── Public API ─────────────────────────────────────────────────────────

def extract(
    signal_data: Dict[str, Any],
    structure_segments: Optional[List[Dict[str, Any]]] = None,
    keyframes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Extract visual packaging metrics from per-frame features.

    Uses ``visual_features`` from signal_data if available; falls back
    to ``keyframes``.

    Args:
        signal_data: Pipeline signal-layer output.
        structure_segments: Unused, reserved.
        keyframes: Sampled keyframe metadata (fallback source).

    Returns:
        Dict with: available, color_style, composition, object_distribution,
        packaging_elements, brightness_stats.
    """
    frames = _get_frames(signal_data, keyframes)
    if not frames:
        return {"available": False}

    # ── 1. Color style ──
    color_style = _color_style(frames)

    # ── 2. Composition ──
    composition = _composition(frames)

    # ── 3. Object distribution ──
    object_distribution = _object_distribution(frames)

    # ── 4. Packaging elements ──
    packaging_elements = _packaging_elements(frames)

    # ── 5. Brightness stats ──
    brightness_stats = _brightness_stats(frames)

    return {
        "available": True,
        "color_style": color_style,
        "composition": composition,
        "object_distribution": object_distribution,
        "packaging_elements": packaging_elements,
        "brightness_stats": brightness_stats,
    }


# ── Frame source ───────────────────────────────────────────────────────

def _get_frames(
    signal_data: Dict[str, Any],
    keyframes: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    vf = signal_data.get("visual_features")
    if vf and isinstance(vf, list) and len(vf) > 0:
        return [f for f in vf if isinstance(f, dict)]
    if keyframes:
        return [k for k in keyframes if isinstance(k, dict)]
    return []


# ── Color style ────────────────────────────────────────────────────────

def _color_style(frames: List[dict]) -> Dict[str, Any]:
    sats = [f.get("saturation_mean", 0.0) for f in frames]
    sat_mean = sum(sats) / max(len(sats), 1)

    if sat_mean > 120:
        saturation_level = "高饱和"
        tone = "暖色调"
    elif sat_mean > 60:
        saturation_level = "中饱和"
        tone = "暖色调" if sat_mean > 90 else "中性"
    elif sat_mean > 20:
        saturation_level = "低饱和"
        tone = "冷色调"
    else:
        saturation_level = "极低饱和/灰度"
        tone = "灰度/黑白"

    # Contrast from brightness std
    b_stds = [f.get("brightness_std", 0.0) for f in frames]
    contrast = "高对比度" if (sum(b_stds) / max(len(b_stds), 1)) > 60 else "标准"

    return {
        "saturation_level": saturation_level,
        "avg_saturation": round(sat_mean, 1),
        "tone": tone,
        "contrast": contrast,
    }


# ── Composition ────────────────────────────────────────────────────────

def _composition(frames: List[dict]) -> Dict[str, Any]:
    n = len(frames)
    face_frame_ratio = sum(1 for f in frames if f.get("face_count", 0) > 0) / max(n, 1)
    avg_face_area = sum(f.get("face_area_ratio", 0.0) for f in frames) / max(n, 1)
    avg_edge = sum(f.get("edge_density", 0.0) for f in frames) / max(n, 1)

    if face_frame_ratio > 0.4 and avg_face_area > 0.05:
        preference = "中心构图（人物主导）"
    elif avg_edge < 0.04 and face_frame_ratio < 0.2:
        preference = "简洁留白"
    elif avg_edge > 0.12:
        preference = "密集构图"
    else:
        preference = "均衡构图"

    return {
        "preference": preference,
        "face_frame_ratio": round(face_frame_ratio, 3),
        "avg_face_area": round(avg_face_area, 4),
        "avg_edge_density": round(avg_edge, 4),
    }


# ── Object distribution ────────────────────────────────────────────────

def _object_distribution(frames: List[dict]) -> Dict[str, float]:
    n = max(len(frames), 1)
    persons = sum(f.get("yolo_person_count", 0) for f in frames) / n
    vehicles = sum(f.get("yolo_vehicle_count", 0) for f in frames) / n
    animals = sum(f.get("yolo_animal_count", 0) for f in frames) / n

    return {
        "avg_person_per_frame": round(persons, 2),
        "avg_vehicle_per_frame": round(vehicles, 2),
        "avg_animal_per_frame": round(animals, 2),
    }


# ── Packaging elements ─────────────────────────────────────────────────

def _packaging_elements(frames: List[dict]) -> Dict[str, float]:
    """Infer packaging types from entropy, edge density, and optical flow.

    - High entropy + low motion → title card (text-rich static frame)
    - Low entropy + low edges → pure color background
    - Medium → packaged / composed frame
    """
    n = max(len(frames), 1)
    tc = bg = pkg = 0

    for f in frames:
        ent = f.get("gray_entropy", 0.0)
        ed = f.get("edge_density", 0.0)
        fl = f.get("optical_flow_magnitude", 0.0)

        if ent > 5.0 and fl < 3.0:
            tc += 1
        elif ent < 2.0 and ed < 0.03:
            bg += 1
        else:
            pkg += 1

    return {
        "title_card_ratio": round(tc / n, 3),
        "pure_background_ratio": round(bg / n, 3),
        "packaged_frame_ratio": round(pkg / n, 3),
    }


# ── Brightness ─────────────────────────────────────────────────────────

def _brightness_stats(frames: List[dict]) -> Dict[str, float]:
    b_vals = [f.get("brightness_mean", 0.0) for f in frames]
    if not b_vals:
        return {"min": 0.0, "max": 0.0, "avg": 0.0}
    return {
        "min": round(min(b_vals), 1),
        "max": round(max(b_vals), 1),
        "avg": round(sum(b_vals) / len(b_vals), 1),
    }
