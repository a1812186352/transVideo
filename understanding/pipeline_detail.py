"""Per-module detail assembly — signal-level data → human-readable analysis dict.

Exported functions:
    build_detail(...)       — full per-segment detail dict
    derive_visual_from_features(...)  — 框架 → 内容 → 动效 list
    filter_ocr_noise(...)   — deduplicate and clean OCR texts
"""

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from understanding.pipeline_config import (
    BPM_HIGH, BPM_MEDIUM, BPM_LOW,
    BRIGHTNESS_DARK, BRIGHTNESS_BRIGHT, SATURATION_HIGH,
    FACE_CLOSEUP_RATIO, FACE_GROUP_RATIO,
    OBJECT_COMPLEX_COUNT, OBJECT_SIMPLE_COUNT,
    EDGE_COMPLEX, EDGE_SIMPLE,
    FL_STILL, FL_SLIGHT, FL_PUSH, FL_FAST,
    HD_STILL, HD_FAST, HD_VIOLENT,
    POS_LEFT, POS_RIGHT,
    ENERGY_VARIANCE_HIGH, ENERGY_AVG_WARM,
    EMOTION_PEAK_HIGH, EMOTION_PEAK_MEDIUM,
    ENERGY_CURVE_BINS,
    SCENE_TAG_MAP, FALLBACK_HIGH_FREQ,
    POSITIVE_KW, NEGATIVE_KW,
    PALETTE_WARM, PALETTE_COOL,
    PALETTE_HIGH_CONTRAST, PALETTE_NEUTRAL,
)


# ── Public API ────────────────────────────────────────────────────────

def build_detail(
    seg_type: str,
    sub_type: str,
    start: float, end: float, duration: float,
    evidence: List[str],
    transcripts: List[dict],
    energy: List[float],
    total_dur: float,
    bpm: float,
    ocr_data: List[dict],
    visual_features: Optional[List[dict]] = None,
    audio_data: Optional[Dict[str, Any]] = None,
    watermark_set: Optional[set] = None,
    prev_motion: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build per-module analysis detail from real signal data.

    Args:
        seg_type: Structure segment type (opening / highlight / …).
        sub_type: Sub-type label from evidence.
        start, end, duration: Segment time bounds.
        evidence: Evidence list from structure inference.
        transcripts: ASR segments.
        energy: Energy curve (RMS or diff).
        total_dur: Total video duration.
        bpm: BPM from audio analysis.
        ocr_data: OCR results with timestamps.
        visual_features: Visual feature dicts from _run_understand_layer.
        audio_data: Full audio analysis dict (mood, spectral, etc.).
        watermark_set: Optional set of watermark texts to exclude.

    Returns:
        Per-segment detail dict with signal-layer data propagated.
    """
    # ── Scene tags ──
    if sub_type and sub_type != "未分类":
        scene_tags = [sub_type]
    else:
        scene_tags = SCENE_TAG_MAP.get(seg_type, ["未知"])

    # ── Visual elements (new: returns structured dict alongside list) ──
    vf_desc, vf_structured = derive_visual_from_features(visual_features, start, end, total_dur)

    # OCR: collect + filter
    ocr_raw: List[str] = []
    for ocr in ocr_data:
        ts = ocr.get("timestamp", -1)
        if ts < 0 or ts < start or ts > end:
            continue
        for region in ocr.get("text_regions", []):
            t = ""
            if isinstance(region, dict):
                t = region.get("text", "")
            elif isinstance(region, str):
                t = region
            if t and (not watermark_set or t not in watermark_set):
                ocr_raw.append(t)

    ocr_clean = filter_ocr_noise(ocr_raw)

    if ocr_clean:
        visual_elements = vf_desc + ocr_clean[:2] if vf_desc else ocr_clean
    else:
        visual_elements = vf_desc if vf_desc else ["静态中景画面"]

    # ── Color tone from energy stats ──
    color_tone = "无"
    if energy and total_dur > 0:
        n = len(energy)
        i_s = int(start / total_dur * n)
        i_e = int(end / total_dur * n)
        i_s = max(0, min(i_s, n - 1))
        i_e = max(i_s + 1, min(i_e, n))
        w = energy[i_s:i_e]
        if w:
            avg = sum(w) / len(w)
            var = sum((x - avg) ** 2 for x in w) / len(w)
            if var > ENERGY_VARIANCE_HIGH:
                color_tone = "高对比度"
            elif avg > ENERGY_AVG_WARM:
                color_tone = "暖色调"
            else:
                color_tone = "冷色调"

    # ── BGM type from BPM ──
    if bpm > BPM_HIGH:
        bgm_type = "激昂 / 紧张"
    elif bpm > BPM_MEDIUM:
        bgm_type = "明快 / 活泼"
    elif bpm > BPM_LOW:
        bgm_type = "舒缓 / 沉静"
    elif bpm > 0:
        bgm_type = "低沉 / 空灵"
    else:
        bgm_type = "无"

    # ── Voice content from ASR ──
    voice_lines: List[str] = []
    for seg in transcripts:
        s = seg.get("start", seg.get("start_time", 0))
        e = seg.get("end", seg.get("end_time", 0))
        if max(s, start) < min(e, end):
            text = seg.get("text", "")
            if text:
                voice_lines.append(text)
    voice_content = " ".join(voice_lines[:3]) if voice_lines else "无"

    # ── Emotion peak from energy ──
    energy_peak_value = 0.0
    energy_peak_offset = 0.0
    if energy and total_dur > 0:
        n = len(energy)
        i_s = int(start / total_dur * n)
        i_e = int(end / total_dur * n)
        i_s = max(0, min(i_s, n - 1))
        i_e = max(i_s + 1, min(i_e, n))
        w = energy[i_s:i_e]
        if w:
            peak_val = max(w)
            peak_rel_idx = w.index(peak_val)
            energy_peak_offset = peak_rel_idx / len(w) * duration
            full_max = max(energy) if energy else 1.0
            if full_max > 0:
                energy_peak_value = peak_val / full_max

    if energy_peak_value <= 0:
        emotion_peak = "无"
    elif energy_peak_value > EMOTION_PEAK_HIGH:
        emotion_peak = f"高 ({energy_peak_value:.2f}, +{energy_peak_offset:.1f}s)"
    elif energy_peak_value > EMOTION_PEAK_MEDIUM:
        emotion_peak = f"中 ({energy_peak_value:.2f}, +{energy_peak_offset:.1f}s)"
    else:
        emotion_peak = f"低 ({energy_peak_value:.2f}, +{energy_peak_offset:.1f}s)"

    # ── High-freq words ──
    voice_text = " ".join(voice_lines).strip()
    if voice_text:
        speech_tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{4,}", voice_text)
        high_freq = speech_tokens[:5] if speech_tokens else voice_lines[:3]
    else:
        ocr_freq_raw: List[str] = []
        for ocr in ocr_data:
            ts = ocr.get("timestamp", -1)
            if ts < 0 or ts < start or ts > end:
                continue
            for region in ocr.get("text_regions", []):
                t = ""
                if isinstance(region, dict):
                    t = region.get("text", "")
                elif isinstance(region, str):
                    t = region
                if t and (not watermark_set or t not in watermark_set):
                    ocr_freq_raw.append(t)
        ocr_freq_clean = filter_ocr_noise(ocr_freq_raw)
        if ocr_freq_clean:
            high_freq = ocr_freq_clean[:5]
        else:
            high_freq = FALLBACK_HIGH_FREQ.get(seg_type, ["#未分类"])

    # ── Sentiment ──
    all_text = " ".join(ocr_clean + voice_lines)
    pos = sum(1 for kw in POSITIVE_KW if kw in all_text)
    neg = sum(1 for kw in NEGATIVE_KW if kw in all_text)
    if pos > neg:
        sentiment = "正面/激昂"
    elif neg > pos:
        sentiment = "负面/低落"
    else:
        sentiment = "中性"

    # ── Parse structured fields from vf_desc ──
    composition = ""
    content_parts: List[str] = []
    motion = ""
    for item in visual_elements:
        if item.startswith("构图:"):
            composition = item.replace("构图: ", "")
        elif item.startswith("动效:"):
            motion = item.replace("动效: ", "")
        elif item.startswith("物体:"):
            content_parts.append(item.replace("物体: ", ""))
        else:
            content_parts.append(item)

    # ── OCR texts in this segment ──
    ocr_texts_in_seg: List[str] = []
    ocr_texts_structured: List[dict] = []
    for ocr in ocr_data:
        ts = ocr.get("timestamp", -1)
        if ts < 0 or ts < start or ts > end:
            continue
        for region in ocr.get("text_regions", []):
            t = ""
            if isinstance(region, dict):
                t = region.get("text", "")
                # Collect structured dict for new field
                if t and (not watermark_set or t not in watermark_set):
                    ocr_texts_structured.append({
                        "text": t,
                        "text_size_rank": region.get("text_size_rank", "small"),
                        "low_confidence": region.get("low_confidence", False),
                    })
            elif isinstance(region, str):
                t = region
                if t and (not watermark_set or t not in watermark_set):
                    ocr_texts_structured.append({
                        "text": t, "text_size_rank": "small", "low_confidence": False,
                    })
            if t and (not watermark_set or t not in watermark_set):
                ocr_texts_in_seg.append(t)

    # ── Signal-layer fields: HSV color, mood, YOLO quality ──

    # color_zone_pcts — per-zone mean across segment frames (English keys)
    color_zone_pcts: Dict[str, float] = {
        "white": 0.0, "warm": 0.0, "cool": 0.0, "neutral": 0.0, "dark": 0.0,
    }
    ZONE_KEY_MAP = {
        "白色/浅灰": "white", "暖色": "warm", "冷色": "cool",
        "中性": "neutral", "暗色": "dark",
    }
    if visual_features and total_dur > 0:
        n_vf = len(visual_features)
        i_s_vf = max(0, int(start / total_dur * n_vf))
        i_e_vf = min(n_vf, int(end / total_dur * n_vf) + 1)
        i_s_vf = max(0, min(i_s_vf, n_vf - 1))
        i_e_vf = max(i_s_vf + 1, min(i_e_vf, n_vf))
        seg_vf = visual_features[i_s_vf:i_e_vf]
        if seg_vf:
            for cn_key, en_key in ZONE_KEY_MAP.items():
                vals = [f.get("color_zone_pcts", {}).get(cn_key, 0.0) for f in seg_vf]
                color_zone_pcts[en_key] = round(sum(vals) / len(vals), 1)

    # is_dominantly_neutral — white + neutral + dark > 50% total
    is_dominantly_neutral = (
        color_zone_pcts["white"] + color_zone_pcts["neutral"] + color_zone_pcts["dark"] > 50.0
    )

    # yolo_quality_flag — worst flag across segment frames
    yolo_quality_flag = "reliable"
    if visual_features and total_dur > 0:
        seg_vf = _slice_visual_features(visual_features, start, end, total_dur)
        flags = [f.get("yolo_quality_flag", "reliable") for f in seg_vf]
        if any(f == "rejected" for f in flags):
            yolo_quality_flag = "rejected"
        elif any(f == "suspicious" for f in flags):
            yolo_quality_flag = "suspicious"

    # mood / mood_confidence / mood_secondary — from audio_data
    mood = ""
    mood_confidence = 0.0
    mood_secondary = ""
    if audio_data:
        mood = audio_data.get("mood", "")
        mood_confidence = audio_data.get("mood_confidence", 0.0)
        mood_secondary = audio_data.get("mood_secondary", "")

    # VAD-aware: non-speech BGM narrative (replaces transcript-driven text)
    has_speech = audio_data.get("has_speech", True) if audio_data else True
    bgm_narrative = ""
    if not has_speech and audio_data:
        bgm_val = audio_data.get("bgm_type", "")
        bpm_val = audio_data.get("bpm", 0)
        energy_curve_local = audio_data.get("energy_curve", [])
        beat_times_local = audio_data.get("beat_times", [])
        dur = audio_data.get("duration", 0)

        # Energy peaks: count frames above 90th percentile
        peak_count = 0
        if energy_curve_local:
            threshold = sorted(energy_curve_local)[int(len(energy_curve_local) * 0.9)]
            peak_count = sum(1 for v in energy_curve_local if v >= threshold)

        # Beat density
        beat_dens = "稀疏"
        if dur > 0:
            bd = len(beat_times_local) / dur
            if bd > 2.0:
                beat_dens = "密集"
            elif bd >= 1.0:
                beat_dens = "适中"

        parts = []
        if bgm_val and bgm_val != "无":
            parts.append(f"BGM: {bgm_val}")
        if bpm_val > 0:
            parts.append(f"BPM {bpm_val:.0f}")
        if peak_count > 0:
            parts.append(f"能量峰 {peak_count}处")
        parts.append(f"节拍{beat_dens}")
        bgm_narrative = " · ".join(parts)

    # ── Inter-module motion trend ──

    bc = vf_structured.get("brightness_curve", [])
    comp_chg = vf_structured.get("composition_changes", 0.0)
    cur_flow = vf_structured.get("motion_description", {}).get("mean", 0.0)

    # brightness_trend: compare first vs last frames
    brightness_trend = "稳定"
    brightness_ratio = 1.0
    if len(bc) >= 3:
        first_val = sum(bc[:3]) / 3
        last_val = sum(bc[-3:]) / 3
        if first_val > 0.01:
            brightness_ratio = round(last_val / first_val, 3)
            if brightness_ratio > 1.1:
                brightness_trend = "变亮"
            elif brightness_ratio < 0.9:
                brightness_trend = "变暗"

    # scale_trend: composition_changes
    scale_trend = "稳定"
    if comp_chg > 0.1:
        scale_trend = "扩散"
    elif comp_chg < -0.1:
        scale_trend = "聚拢"

    # movement_trend: compare current vs previous segment flow
    movement_trend = "稳定"
    movement_ratio = 1.0
    if prev_motion and cur_flow > 0.01:
        prev_flow_val = prev_motion.get("mean", 0.0)
        if prev_flow_val > 0.01:
            movement_ratio = round(cur_flow / prev_flow_val, 3)
            if movement_ratio > 1.5:
                movement_trend = "动效增强"
            elif movement_ratio < 0.6:
                movement_trend = "动效减弱"
    elif prev_motion is None:
        movement_trend = "起始段"

    motion_trend = {
        "brightness_trend": brightness_trend,
        "brightness_ratio": brightness_ratio,
        "scale_trend": scale_trend,
        "scale_value": round(comp_chg, 3),
        "movement_trend": movement_trend,
        "movement_ratio": movement_ratio,
    }

    # object_transitions — from derive_visual_from_features structured output
    object_transitions = vf_structured.get("object_transitions", {
        "fade_in_count": 0, "fade_out_count": 0,
    })

    # ── Color palette ──
    if "暖" in color_tone or "高饱和" in color_tone:
        color_palette = PALETTE_WARM
    elif "冷" in color_tone:
        color_palette = PALETTE_COOL
    elif "高对比度" in color_tone:
        color_palette = PALETTE_HIGH_CONTRAST
    else:
        color_palette = PALETTE_NEUTRAL

    # ── Energy curve snippet (binned to 20 bars) ──
    energy_curve_binned: List[float] = []
    if energy and total_dur > 0:
        n = len(energy)
        i_s = int(start / total_dur * n)
        i_e = int(end / total_dur * n)
        i_s = max(0, min(i_s, n - 1))
        i_e = max(i_s + 1, min(i_e, n))
        segment_energy = energy[i_s:i_e]
        if segment_energy:
            bin_size = max(1, len(segment_energy) // ENERGY_CURVE_BINS)
            energy_curve_binned = [
                sum(segment_energy[j:j + bin_size]) / bin_size
                for j in range(0, len(segment_energy), bin_size)
            ][:ENERGY_CURVE_BINS]

    return {
        "scene_tags": scene_tags,
        "composition": composition or "无",
        "visual_elements": content_parts if content_parts else visual_elements[:3],
        "motion": motion or "无",
        "color_tone": color_tone,
        "color_palette": color_palette,
        "bpm": bpm,
        "bgm_type": bgm_type,
        "ocr_texts": ocr_texts_in_seg[:10] if ocr_texts_in_seg else [],
        "ocr_texts_structured": ocr_texts_structured[:10] if ocr_texts_structured else [],
        "voice_content": voice_content,
        "emotion_peak": emotion_peak,
        "energy_peak_value": round(energy_peak_value, 3),
        "energy_peak_offset": round(energy_peak_offset, 2),
        "energy_curve": energy_curve_binned if energy_curve_binned else [],
        "high_freq_words": high_freq,
        "sentiment": sentiment,
        # Signal-layer propagation (new)
        "color_zone_pcts": color_zone_pcts,
        "is_dominantly_neutral": is_dominantly_neutral,
        "yolo_quality_flag": yolo_quality_flag,
        "mood": mood,
        "mood_confidence": mood_confidence,
        "mood_secondary": mood_secondary,
        "has_speech": has_speech,
        "bgm_narrative": bgm_narrative,
        "brightness_curve": bc,
        "composition_changes": vf_structured.get("composition_changes", 0.0),
        "motion_description": vf_structured.get("motion_description", {}),
        "motion_trend": motion_trend,
        "object_transitions": object_transitions,
        # ═══ Enhanced module info ═══
        "original_start": round(start, 2),
        "original_end": round(end, 2),
        "content_tags": _build_content_tags(
            seg_type=seg_type, sub_type=sub_type,
            scene_tags=scene_tags, motion=motion,
            bgm_type=bgm_type, color_tone=color_tone,
        ),
    }


def _build_content_tags(
    seg_type: str,
    sub_type: str,
    scene_tags: List[str],
    motion: str,
    bgm_type: str,
    color_tone: str,
) -> List[str]:
    """Build content-level tags for dual-layer classification.

    Structure type (e.g. ``highlight``) describes the narrative role;
    content tags describe the actual scene content (voiceover, effect,
    transition, etc.).
    """
    tags: List[str] = []

    # Scene tags from evidence
    if scene_tags:
        tags.extend(t for t in scene_tags if t)

    # Motion label
    if motion and motion != "无":
        tags.append(motion)

    # BGM type
    if bgm_type and bgm_type != "无" and bgm_type != "未知":
        tags.append(bgm_type)

    # Color tone
    if color_tone and color_tone != "未知":
        tags.append(color_tone)

    # Sub-type as content hint (if not redundant)
    if sub_type and sub_type not in ("未分类", "无", ""):
        tags.append(sub_type)

    return list(dict.fromkeys(tags))  # dedupe preserving order


# ── Visual description helpers ────────────────────────────────────────

def derive_visual_from_features(
    visual_features: Optional[List[dict]], start: float, end: float, total_dur: float
) -> Tuple[List[str], Dict[str, Any]]:
    """Derive human-readable visual descriptions and structured data.

    Returns:
        (visual_list, structured_dict)

        visual_list: 框架 → 内容 → 动效 human-readable labels.
        structured_dict:
            - brightness_curve: List[float]  normalized brightness (0-1)
            - composition_changes: float  bbox area change rate
            - motion_description: dict  {mean, std, max, label}
    """
    from collections import Counter, defaultdict

    structured: Dict[str, Any] = {
        "brightness_curve": [],
        "composition_changes": 0.0,
        "motion_description": {},
    }

    if not visual_features or total_dur <= 0:
        return ["无"], structured

    n = len(visual_features)
    i_s = max(0, int(start / total_dur * n))
    i_e = min(n, int(end / total_dur * n) + 1)
    i_s = max(0, min(i_s, n - 1))
    i_e = max(i_s + 1, min(i_e, n))
    frames = visual_features[i_s:i_e]
    if not frames:
        return ["无"]

    # Aggregate OpenCV signals
    fc = sum(f.get("face_count", 0) for f in frames)
    far = sum(f.get("face_area_ratio", 0) for f in frames) / max(len(frames), 1)
    fl = sum(f.get("optical_flow_magnitude", 0) for f in frames) / len(frames)
    sat = sum(f.get("saturation_mean", 0) for f in frames) / len(frames)
    bm = sum(f.get("brightness_mean", 0) for f in frames) / len(frames)
    hd = sum(f.get("histogram_distance", 0) for f in frames) / len(frames)

    # Aggregate YOLO objects
    all_objs: List[dict] = []
    for f in frames:
        all_objs.extend(f.get("yolo_objects", []) or [])

    class_counts: Dict[str, int] = Counter()
    class_bboxes: Dict[str, List[list]] = defaultdict(list)
    for obj in all_objs:
        name = obj.get("class_name", "")
        if not name:
            continue
        class_counts[name] += 1
        class_bboxes[name].append(obj.get("bbox", [0, 0, 0, 0]))

    VEHICLE_NAMES = {"car", "truck", "bus", "motorcycle", "bicycle", "train", "boat", "aeroplane", "airplane"}
    ANIMAL_NAMES = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}
    yolo_person_cnt = class_counts.get("person", 0)
    yolo_vehicle_cnt = sum(class_counts[k] for k in class_counts if k in VEHICLE_NAMES)
    yolo_animal_cnt = sum(class_counts[k] for k in class_counts if k in ANIMAL_NAMES)

    def _avg_position(bboxes: List[list]) -> str:
        if not bboxes:
            return ""
        cx_list, cy_list = [], []
        for b in bboxes:
            if len(b) >= 4:
                cx_list.append((b[0] + b[2]) / 2.0)
                cy_list.append((b[1] + b[3]) / 2.0)
        if not cx_list:
            return ""
        avg_cx = sum(cx_list) / len(cx_list)
        avg_cy = sum(cy_list) / len(cy_list)
        parts_pos = []
        if avg_cx < POS_LEFT:
            parts_pos.append("画面左侧")
        elif avg_cx > POS_RIGHT:
            parts_pos.append("画面右侧")
        else:
            parts_pos.append("画面中央")
        if avg_cy < POS_LEFT:
            parts_pos.append("上方")
        elif avg_cy > POS_RIGHT:
            parts_pos.append("下方")
        return "（" + "、".join(parts_pos) + "）" if parts_pos else ""

    result: List[str] = []

    # ═══════════════ 框架层 ═══════════════

    comp_types = [
        f.get("composition_type", "")
        for f in frames
        if f.get("composition_type") and f["composition_type"] != "unknown"
    ]
    comp_confs = [f.get("composition_confidence", 0) for f in frames]
    if comp_types:
        best_comp = Counter(comp_types).most_common(1)[0][0]
        avg_conf = sum(comp_confs) / len(comp_confs) if comp_confs else 0
        result.append(f"构图: {best_comp}（置信度 {avg_conf:.2f}）")
    else:
        _heuristic = ""
        if fc >= 1 and far > FACE_CLOSEUP_RATIO:
            _heuristic = "人物特写"
        elif fc >= 2 and far < FACE_GROUP_RATIO:
            _heuristic = "群像/全景"
        elif len(all_objs) > OBJECT_COMPLEX_COUNT:
            _heuristic = "复杂"
        elif len(all_objs) < OBJECT_SIMPLE_COUNT:
            _heuristic = "简洁"
        if _heuristic:
            result.append(f"构图: {_heuristic}构图")

    if bm < BRIGHTNESS_DARK:
        result.append("光照: 暗调/夜场景")
    elif bm > BRIGHTNESS_BRIGHT:
        result.append("光照: 明亮日间场景")
    else:
        result.append("光照: 正常光照")

    if sat > SATURATION_HIGH:
        result.append("色彩: 暖色调（高饱和）")
    else:
        result.append("色彩: 冷色调（低饱和）")

    # ═══════════════ 内容层 ═══════════════

    obj_parts: List[str] = []
    seen_top_classes: set = set()

    if yolo_person_cnt > 0:
        pos = _avg_position(class_bboxes.get("person", []))
        if yolo_person_cnt >= 3:
            obj_parts.append(f"人物×{yolo_person_cnt}{pos}")
        elif yolo_person_cnt == 2:
            obj_parts.append(f"双人{pos}")
        else:
            obj_parts.append(f"单人{pos}")
        seen_top_classes.add("person")

    other_classes = [
        (name, cnt) for name, cnt in class_counts.most_common(10)
        if name not in seen_top_classes and name not in ANIMAL_NAMES | VEHICLE_NAMES
    ]
    for name, cnt in other_classes[:3]:
        pos = _avg_position(class_bboxes.get(name, []))
        obj_parts.append(f"{name}×{cnt}{pos}" if cnt >= 3 else f"{name}{pos}")
        seen_top_classes.add(name)

    if yolo_vehicle_cnt > 0:
        pos = ""
        for name in VEHICLE_NAMES:
            if name in class_counts:
                pos = _avg_position(class_bboxes.get(name, []))
                break
        if yolo_vehicle_cnt >= 3:
            obj_parts.append(f"车辆×{yolo_vehicle_cnt}{pos}")
        else:
            vehicle_names = [k for k in class_counts if k in VEHICLE_NAMES]
            obj_parts.append(f"含{'、'.join(vehicle_names)}{pos}")

    if yolo_animal_cnt > 0:
        pos = ""
        animal_names = [k for k in class_counts if k in ANIMAL_NAMES]
        for name in animal_names:
            pos = _avg_position(class_bboxes.get(name, []))
            break
        obj_parts.append(f"动物×{yolo_animal_cnt}{pos}" if yolo_animal_cnt >= 3
                         else f"含{'、'.join(animal_names)}{pos}")

    if obj_parts:
        obj_str = "、".join(obj_parts[:4])
        result.append(f"物体: {obj_str}")
    elif fc >= 1:
        result.append("物体: 人物")
    else:
        result.append("物体: 无显著物体")

    # ═══════════════ 动效层 ═══════════════
    # ── Compute enriched motion signals from frame data ──
    bbox_area_trend: float = 0.0  # + = expanding, - = contracting
    brightness_trend: float = 0.0
    bbox_x_drift: float = 0.0      # + = rightward, - = leftward

    bbox_centers_x: List[float] = []
    if frames:
        bright_vals = [f.get("brightness_mean", 0.0) for f in frames]
        if len(bright_vals) >= 3:
            half = len(bright_vals) // 2
            b_first = sum(bright_vals[:half]) / max(half, 1)
            b_last = sum(bright_vals[-half:]) / max(half, 1)
            brightness_trend = (b_last - b_first) / max(max(b_last, b_first), 0.001)

    bbox_areas = []
    for f in frames:
        centers: List[float] = []
        areas: List[float] = []
        for o in (f.get("yolo_objects", []) or []):
            b = o.get("bbox", [])
            if len(b) >= 4:
                cx = (b[0] + b[2]) / 2.0
                centers.append(cx)
                areas.append((b[2] - b[0]) * (b[3] - b[1]))
        bbox_centers_x.append(sum(centers) / max(len(centers), 1) if centers else 0.0)
        top3 = sorted(areas, reverse=True)[:3]
        bbox_areas.append(sum(top3) / max(len(top3), 1) if top3 else 0.0)

    if len(bbox_areas) >= 2:
        half = max(len(bbox_areas) // 2, 1)
        left_mean = sum(bbox_areas[:half]) / max(half, 1)
        right_mean = sum(bbox_areas[half:]) / max(len(bbox_areas) - half, 1)
        if left_mean > 0 and right_mean > 0:
            bbox_area_trend = right_mean / left_mean  # >1 = zoom in, <1 = zoom out

    if len(bbox_centers_x) >= 2:
        half = max(len(bbox_centers_x) // 2, 1)
        left_cx = sum(bbox_centers_x[:half]) / max(half, 1)
        right_cx = sum(bbox_centers_x[half:]) / max(len(bbox_centers_x) - half, 1)
        bbox_x_drift = right_cx - left_cx

    # ── Enhanced motion classification ──
    motion_label_code = ""  # machine-readable code (ZOOM_IN, PAN, etc.)
    scale_factor = round(bbox_area_trend, 3) if bbox_area_trend != 0 else None
    rotation_angle = None
    displacement = round(bbox_x_drift, 1) if abs(bbox_x_drift) > 2 else None

    # Fade detection: brightness trend (requires near-zero flow + strong brightness shift)
    if abs(brightness_trend) > 0.25 and fl < FL_STILL:
        if brightness_trend > 0:
            motion = "淡入过渡"
            motion_label_code = "FADE_IN"
        else:
            motion = "淡出过渡"
            motion_label_code = "FADE_OUT"

    # Zoom detection: bbox area consistently expanding/contracting
    elif bbox_area_trend > 1.25 and fl < FL_FAST:
        motion = f"镜头推近（放大 ×{bbox_area_trend:.2f}）"
        motion_label_code = "ZOOM_IN"
    elif 0.001 < bbox_area_trend < 0.75 and fl < FL_FAST:
        zoom_ratio = max(1.0 / bbox_area_trend, 1.0)
        motion = f"镜头拉远（缩小 ×{zoom_ratio:.2f}）"
        motion_label_code = "ZOOM_OUT"

    # Pan detection: consistent x-drift of tracked objects
    elif abs(bbox_x_drift) > 20 and fl < FL_FAST:
        direction = "右移" if bbox_x_drift > 0 else "左移"
        motion = f"画面{direction}"
        motion_label_code = "PAN"
        displacement = round(bbox_x_drift, 1)

    # Slide detection: moderate flow + weak bbox change
    elif FL_STILL < fl <= FL_SLIGHT and abs(bbox_area_trend - 1) < 0.15:
        motion = "滑动平移"
        motion_label_code = "SLIDE"

    # Rotate heuristic: moderate flow + high std in center dispersion
    elif FL_SLIGHT < fl <= FL_PUSH:
        # Estimate rotation from center variance (crude proxy)
        if len(bbox_centers_x) >= 2:
            spreads = [max(cs) - min(cs) for cs in bbox_centers_x if len(cs) > 1]
            if spreads and max(spreads) - min(spreads) > 50:
                motion = "镜头旋转"
                motion_label_code = "ROTATE"
                rotation_angle = round(max(spreads) - min(spreads), 1)
            else:
                motion = "缓推镜头 / 平移跟随"
                motion_label_code = "PUSH"
        else:
            motion = "缓推镜头 / 平移跟随"
            motion_label_code = "PUSH"

    # Fallback to existing 5-level system
    elif fl < FL_STILL and hd < HD_STILL:
        motion = "静止定镜"
        motion_label_code = "STILL"
    elif FL_STILL <= fl <= FL_SLIGHT:
        motion = "轻微晃动"
        motion_label_code = "SHAKE"
    elif FL_PUSH < fl <= FL_FAST and hd < HD_FAST:
        motion = "快速摇镜"
        motion_label_code = "PAN"
    elif fl > FL_FAST and hd > HD_VIOLENT:
        motion = "剧烈切换"
        motion_label_code = "CUT"
    elif fl >= FL_PUSH:
        motion = "画面运动"
        motion_label_code = "MOVE"
    else:
        motion = "静止定镜"
        motion_label_code = "STILL"

    # ── Build enriched text description ──
    motion_parts = [motion]
    if fl >= FL_STILL:
        motion_parts.append(f"光流 {fl:.1f}")
    if scale_factor:
        motion_parts.append(f"缩放 ×{scale_factor}")
    if rotation_angle:
        motion_parts.append(f"旋转 {rotation_angle}°")
    if displacement:
        motion_parts.append(f"位移 {displacement}px")

    result.append(f"动效: {'｜'.join(motion_parts)}")

    # ── Structured data ──

    # brightness_curve — normalized per-frame brightness (0-1)
    structured["brightness_curve"] = [
        round(f.get("brightness_mean", 0.0) / 255.0, 4) for f in frames
    ]

    # composition_changes — bbox area frame-to-frame change rate
    bbox_areas: List[float] = []
    for f in frames:
        objs = f.get("yolo_objects", []) or []
        areas = []
        for o in objs:
            b = o.get("bbox", [])
            if len(b) >= 4:
                areas.append((b[2] - b[0]) * (b[3] - b[1]))
        areas.sort(reverse=True)
        top3 = areas[:3]
        bbox_areas.append(sum(top3) / max(len(top3), 1) if top3 else 0.0)
    if len(bbox_areas) >= 2:
        diffs = [bbox_areas[i] - bbox_areas[i - 1] for i in range(1, len(bbox_areas))]
        nonzero = [d for d in diffs if abs(d) > 1e-6]
        structured["composition_changes"] = round(
            sum(nonzero) / max(len(nonzero), 1), 2,
        ) if nonzero else 0.0

    # motion_description
    flows = [f.get("optical_flow_magnitude", 0.0) for f in frames]
    if flows:
        flow_mean = sum(flows) / len(flows)
        flow_std = float((sum((x - flow_mean) ** 2 for x in flows) / len(flows)) ** 0.5)
        flow_max = max(flows)
        structured["motion_description"] = {
            "mean": round(flow_mean, 2),
            "std": round(flow_std, 2),
            "max": round(flow_max, 2),
            "label": motion,
            "label_code": motion_label_code,
            "scale_factor": scale_factor,
            "rotation_angle": rotation_angle,
            "displacement": displacement,
        }

    # object_transitions — YOLO bbox disappear/appear per frame pair
    fade_in_cnt, fade_out_cnt = 0, 0
    prev_classes: set = set()
    for f in frames:
        cur_classes: set = set()
        for o in (f.get("yolo_objects", []) or []):
            cls = o.get("class_name", "")
            if cls:
                cur_classes.add(cls)
        if prev_classes:
            new = cur_classes - prev_classes
            gone = prev_classes - cur_classes
            if new:
                fade_in_cnt += len(new)
            if gone:
                fade_out_cnt += len(gone)
        prev_classes = cur_classes
    structured["object_transitions"] = {
        "fade_in_count": fade_in_cnt,
        "fade_out_count": fade_out_cnt,
    }

    return result, structured


def _slice_visual_features(
    visual_features: List[dict], start: float, end: float, total_dur: float,
) -> List[dict]:
    """Slice visual_features to the frames falling within [start, end]."""
    n = len(visual_features)
    i_s = max(0, int(start / total_dur * n))
    i_e = min(n, int(end / total_dur * n) + 1)
    i_s = max(0, min(i_s, n - 1))
    i_e = max(i_s + 1, min(i_e, n))
    return visual_features[i_s:i_e]


def filter_ocr_noise(raw: List[str]) -> List[str]:
    """Remove OCR noise: single chars, short gibberish, consecutive duplicates.

    Returns a deduplicated list of meaningful text snippets.
    """
    seen: set = set()
    clean: List[str] = []

    for t in raw:
        t = t.strip()
        if not t:
            continue
        if len(t) < 2:
            continue
        if re.fullmatch(r"[^\w\u4e00-\u9fff]+", t):
            continue
        if len(t) <= 3 and re.fullmatch(r"[a-zA-Z]+", t):
            continue
        if len(t) <= 3 and t.isdigit():
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append(t)

    return clean
