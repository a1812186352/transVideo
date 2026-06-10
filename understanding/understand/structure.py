"""Narrative structure inference — 5-type sliding-window classifier.

Classifies video timeline into: opening / highlight / transition / effect / closing
with 19 fine-grained sub-types.  Supports 16 video-type presets that tune thresholds
per domain (commercial, gaming, lecture, …).

Uses position heuristics, scene boundaries, energy curve, speech, OCR, and visual signals.
"""

from typing import List, Dict, Any, Tuple, Optional


# ── 5-type system ──
TYPE_OPENING = "opening"
TYPE_HIGHLIGHT = "highlight"
TYPE_TRANSITION = "transition"
TYPE_EFFECT = "effect"
TYPE_CLOSING = "closing"
TYPE_UNCLASSIFIED = "unclassified"

# ── OCR keyword sets ──
_OPENING_KW = ["start", "opening", "intro", "begin", "title", "logo",
               "episode", "vol", "chapter", "第", "集", "片头", "开幕",
               "开始", "前方", "前排", "第一", "预告", "开篇", "序章",
               "登场", "出场", "序幕", "背景介绍", "前情提要", "播出"]
_HIGHLIGHT_KW = ["battle", "fight", "explosion", "climax", "燃", "爆",
                 "绝了", "高能", "神", "帅", "厉害", "卧槽", "牛", "炸",
                 "精彩", "超燃", "名场面", "高光", "对决", "激战", "反转",
                 "真相", "高峰", "飙升", "全场最佳", "高潮"]
_CLOSING_KW = ["end", "closing", "outro", "credits", "goodbye", "完结",
               "撒花", "再见", "结束", "辛苦", "下期", "期待", "谢幕",
               "片尾", "彩蛋", "to be continued", "see you", "告别",
               "落幕", "尾声", "终章", "感谢观看", "谢谢", "敬请期待",
               "下集"]

# Transition indicators (OCR text suggesting scene change)
_TRANSITION_KW = ["later", "meanwhile", "elsewhere", "之后", "同时",
                  "另一边", "时间跳转", "回想", "回忆", "切换", "转场",
                  "闪回", "倒叙", "插叙", "画面一转", "镜头切换"]


class StructureInferrer:
    """5-type sliding-window narrative classifier.

    Types: opening / highlight / transition / effect / closing.

    Opening  — first 10% of video, title/logo detected
    Highlight — highest priority; high activity + emotion keywords
    Transition — scene switch confidence > threshold
    Effect    — very short segments (< 3s) with distinctive signal
    Closing   — last 15% of video, fade-out / goodbye keywords
    """

    # ── Position thresholds ──
    OPENING_POSITION = 0.10       # first 10%
    CLOSING_POSITION = 0.85       # last 15%

    # ── Activity thresholds ──
    HIGH_CUT_RATE = 2             # cuts per window → transition candidate
    EFFECT_MAX_DURATION = 3.0     # seconds — effect cap
    ENERGY_PEAK_RATIO = 1.8       # RMS > baseline * 1.8 → highlight signal

    # ── Confidence base scores ──
    CONF_OPENING = 0.80
    CONF_HIGHLIGHT = 0.85
    CONF_TRANSITION = 0.75
    CONF_EFFECT = 0.65
    CONF_CLOSING = 0.80
    CONF_UNCLASSIFIED = 0.30

    # ── Sliding window params ──
    WINDOW_SIZE = 1.0             # seconds
    WINDOW_STEP = 0.5             # seconds

    # ── Visual feature thresholds ──
    FLOW_HIGH_THRESHOLD = 15.0
    FLOW_INTENSE_THRESHOLD = 25.0
    SATURATION_VIVID = 100
    SATURATION_HIGH = 150
    HIST_DIST_THRESHOLD = 0.5
    BRIGHTNESS_DARK = 20
    BRIGHTNESS_FADE = 25
    FACE_RATIO_TALKING = 0.08
    FACE_RATIO_HIGHLIGHT = 0.12
    EDGE_DENSITY_COMPLEX = 0.15

    def infer(
        self,
        frame_descriptions: List[dict],
        audio_data: dict,
        ocr_data: List[dict],
        visual_features: Optional[List[dict]] = None,
        confidence_threshold: float = 0.5,
        preset: Optional[Tuple] = None,
    ) -> List[dict]:
        """Run 5-type sliding-window classification.

        Args:
            frame_descriptions: Vision analyzer output (may be empty).
            audio_data: Audio analyzer output (bpm, energy, silence, speech).
            ocr_data: OCR results per frame.
            confidence_threshold: Minimum confidence to emit a segment.
            preset: Optional (opening_pct, closing_pct, energy_mult, cut_mult,
                    ocr_w, audio_w, yolo_w) tuple from VIDEO_TYPE_PRESETS.

        Returns:
            List of dicts with: start_time, end_time, structure_type,
            sub_type, confidence, evidence.
        """
        total_duration = self._resolve_duration(audio_data, ocr_data)
        if total_duration <= 0:
            return []

        if self.WINDOW_SIZE >= total_duration:
            return []

        # ── Apply preset (override default thresholds) ──
        if preset is not None:
            opening_pct, closing_pct, energy_mult, cut_mult, ocr_w, audio_w, yolo_w = preset[:7]
        else:
            opening_pct = self.OPENING_POSITION
            closing_pct = self.CLOSING_POSITION
            energy_mult = 1.0
            cut_mult = 1.0
            ocr_w = 1.0
            audio_w = 1.0
            yolo_w = 1.0

        # ── Pre-compute per-window signals ──
        windows = self._build_windows(total_duration)
        scene_bounds = self._extract_scene_boundaries(audio_data)
        energy = audio_data.get("energy_curve", [])
        speech_activity = self._speech_per_window(audio_data, windows)

        segments: List[dict] = []

        for w_start, w_end in windows:
            w_dur = w_end - w_start

            # ── Position check (preset-adjusted) ──
            is_opening_zone = w_start < total_duration * opening_pct
            is_closing_zone = w_start > total_duration * (1.0 - closing_pct)

            # ── Activity signals ──
            cuts = self._cuts_in_window(scene_bounds, w_start, w_end)
            cut_rate = cuts / w_dur if w_dur > 0 else 0

            energy_ratio = self._energy_peak_ratio(energy, total_duration, w_start, w_end)

            has_opening_ocr = self._has_ocr_keyword(ocr_data, w_start, w_end, _OPENING_KW)
            has_highlight_ocr = self._has_ocr_keyword(ocr_data, w_start, w_end, _HIGHLIGHT_KW)
            has_closing_ocr = self._has_ocr_keyword(ocr_data, w_start, w_end, _CLOSING_KW)
            has_transition_ocr = self._has_ocr_keyword(ocr_data, w_start, w_end, _TRANSITION_KW)

            speech_sec = speech_activity.get((w_start, w_end), 0.0)

            is_fading = self._is_fading(audio_data, w_start, total_duration)

            # ── Visual features (if available) ──
            vw: dict = {}
            if visual_features:
                vw = self._aggregate_visual_window(visual_features, w_start, w_end)

            # ── Score each type ──
            scores: List[Tuple[float, str, List[str]]] = []

            # Opening
            if is_opening_zone and w_start < 5.0:
                conf = self.CONF_OPENING
                ev = ["position_first_10pct"]
                if has_opening_ocr:
                    conf = min(conf + 0.08, 0.95)
                    ev.append("opening_ocr_match")
                if vw.get("face_presence") and vw.get("avg_face_ratio", 0) > self.FACE_RATIO_TALKING:
                    conf = min(conf + 0.06, 0.95)
                    ev.append("visual_talking_head")
                if vw.get("avg_edge_density", 0) > self.EDGE_DENSITY_COMPLEX and not vw.get("face_presence"):
                    conf = min(conf + 0.04, 0.95)
                    ev.append("visual_complex_scene")
                # YOLO: person in opening → talking-head or crowd intro
                if vw.get("yolo_person_count", 0) >= 2:
                    conf = min(conf + 0.04, 0.95)
                    if vw.get("face_presence"):
                        ev.append("yolo_talking_head")
                    else:
                        ev.append("yolo_crowd_intro")
                scores.append((conf, TYPE_OPENING, ev))

            # Highlight — any zone with high energy + emotion keywords
            hl_conf = 0.0
            hl_ev: List[str] = []
            if energy_ratio > self.ENERGY_PEAK_RATIO * energy_mult:
                hl_conf += 0.35
                hl_ev.append(f"energy_peak_{energy_ratio:.1f}x")
            if cut_rate > self.HIGH_CUT_RATE * cut_mult:
                hl_conf += 0.20
                hl_ev.append(f"cut_rate_{cut_rate:.1f}/s")
            if has_highlight_ocr:
                hl_conf += 0.20 * ocr_w
                hl_ev.append("highlight_ocr_match")
            if speech_sec / max(w_dur, 0.1) > 0.7:
                hl_conf += 0.10 * audio_w
                hl_ev.append("high_speech_density")

            if vw.get("avg_flow", 0) > self.FLOW_HIGH_THRESHOLD:
                hl_conf += 0.15
                hl_ev.append("visual_high_motion")
            if vw.get("avg_saturation", 0) > self.SATURATION_VIVID and vw.get("avg_flow", 0) > 8.0:
                hl_conf += 0.10
                hl_ev.append("visual_vivid_motion")
            if vw.get("face_presence") and vw.get("avg_face_ratio", 0) > self.FACE_RATIO_HIGHLIGHT:
                hl_conf += 0.05
                hl_ev.append("visual_face_highlight")
            # YOLO: crowd / vehicle / animal in highlight zone → activity
            if vw.get("yolo_person_count", 0) >= 3:
                hl_conf += 0.08 * yolo_w
                hl_ev.append("yolo_crowd_activity")
            if vw.get("yolo_vehicle_count", 0) >= 1:
                hl_conf += 0.05 * yolo_w
                hl_ev.append("yolo_vehicle_action")
            if vw.get("yolo_animal_count", 0) >= 1:
                hl_conf += 0.03 * yolo_w
                hl_ev.append("yolo_animal_presence")

            if hl_conf > 0.3:
                scores.append((min(hl_conf, 0.95), TYPE_HIGHLIGHT, hl_ev))

            # Transition
            tr_conf = 0.0
            tr_ev: List[str] = []
            if cut_rate > 0.5:
                tr_conf += 0.40
                tr_ev.append(f"scene_switch_{cut_rate:.1f}/s")
            if has_transition_ocr:
                tr_conf += 0.20
                tr_ev.append("transition_ocr")

            # Check silence gap
            if self._has_silence_gap(audio_data, w_start, w_end):
                tr_conf += 0.15
                tr_ev.append("silence_gap")

            if vw.get("max_hist_dist", 0) > self.HIST_DIST_THRESHOLD:
                tr_conf += 0.15
                tr_ev.append("visual_color_shift")
            if vw.get("min_brightness", 255) < self.BRIGHTNESS_DARK:
                tr_conf += 0.10
                tr_ev.append("visual_dark_transition")

            if tr_conf > 0.35:
                scores.append((min(tr_conf, 0.90), TYPE_TRANSITION, tr_ev))

            # Effect — very short with distinct signal
            if w_dur < self.EFFECT_MAX_DURATION and (energy_ratio > 2.0 or cut_rate > 3):
                ef_conf = self.CONF_EFFECT + min(energy_ratio * 0.05, 0.15)
                ef_ev = [f"short_segment_{w_dur:.1f}s"]
                if vw.get("avg_flow", 0) > self.FLOW_INTENSE_THRESHOLD:
                    ef_conf = min(ef_conf + 0.10, 0.90)
                    ef_ev.append("visual_intense_motion")
                if vw.get("avg_saturation", 0) > self.SATURATION_HIGH:
                    ef_conf = min(ef_conf + 0.08, 0.90)
                    ef_ev.append("visual_high_saturation")
                scores.append((min(ef_conf, 0.90), TYPE_EFFECT, ef_ev))

            # Closing
            if is_closing_zone:
                cl_conf = self.CONF_CLOSING
                cl_ev = ["position_last_15pct"]
                if has_closing_ocr:
                    cl_conf = min(cl_conf + 0.08, 0.95)
                    cl_ev.append("closing_ocr_match")
                if is_fading:
                    cl_conf = min(cl_conf + 0.05, 0.95)
                    cl_ev.append("energy_fading")
                if vw.get("min_brightness", 255) < self.BRIGHTNESS_FADE and vw.get("avg_flow", 99) < 3.0:
                    cl_conf = min(cl_conf + 0.05, 0.95)
                    cl_ev.append("visual_fade_out")
                scores.append((cl_conf, TYPE_CLOSING, cl_ev))

            # ── Pick best type ──
            if scores:
                scores.sort(key=lambda x: x[0], reverse=True)
                best_conf, best_type, best_ev = scores[0]
                if best_conf >= confidence_threshold:
                    sub_type = self._derive_sub_type(best_type, best_ev)
                    segments.append({
                        "start_time": w_start,
                        "end_time": w_end,
                        "structure_type": best_type,
                        "sub_type": sub_type,
                        "confidence": round(best_conf, 2),
                        "evidence": best_ev,
                    })

        # ── Non-maximum suppression: merge adjacent same-type ──
        merged = self._merge_adjacent(segments)

        return merged

    # ── Window helpers ──

    def _build_windows(self, total_duration: float) -> List[Tuple[float, float]]:
        windows: List[Tuple[float, float]] = []
        t = 0.0
        while t + self.WINDOW_SIZE <= total_duration:
            windows.append((round(t, 1), round(t + self.WINDOW_SIZE, 1)))
            t += self.WINDOW_STEP
        # Last partial window
        if t < total_duration:
            windows.append((round(t, 1), round(total_duration, 1)))
        return windows

    @staticmethod
    def _resolve_duration(audio_data: dict, ocr_data: List[dict]) -> float:
        dur = audio_data.get("duration", 0.0) or audio_data.get("total_duration", 0.0)
        if dur <= 0 and ocr_data:
            dur = max((d.get("timestamp", 0) for d in ocr_data), default=0.0)
        return dur

    @staticmethod
    def _extract_scene_boundaries(audio_data: dict) -> List[float]:
        sb = audio_data.get("scene_boundaries", [])
        out: List[float] = []
        for b in sb:
            if isinstance(b, (int, float)):
                out.append(float(b))
            elif isinstance(b, dict):
                out.append(float(b.get("timestamp", b.get("start", 0))))
        return sorted(out)

    @staticmethod
    def _cuts_in_window(boundaries: List[float], start: float, end: float) -> int:
        return sum(1 for b in boundaries if start <= b <= end)

    @staticmethod
    def _energy_peak_ratio(
        energy: List[float], total_duration: float, start: float, end: float
    ) -> float:
        if not energy or total_duration <= 0:
            return 1.0
        n = len(energy)
        i_s = int(start / total_duration * n)
        i_e = int(end / total_duration * n)
        i_s = max(0, min(i_s, n - 1))
        i_e = max(i_s + 1, min(i_e, n))
        window_vals = energy[i_s:i_e]
        if not window_vals:
            return 1.0
        peak = max(window_vals)
        baseline = sum(energy) / max(len(energy), 1)
        if baseline <= 0:
            return 1.0
        return peak / baseline

    @staticmethod
    def _has_ocr_keyword(
        ocr_data: List[dict], start: float, end: float, keywords: List[str]
    ) -> bool:
        for item in ocr_data:
            ts = item.get("timestamp", -1)
            if ts < 0 or ts < start or ts > end:
                continue
            for region in item.get("text_regions", []):
                text = ""
                if isinstance(region, dict):
                    text = region.get("text", "")
                elif isinstance(region, str):
                    text = region
                text_lower = text.lower()
                for kw in keywords:
                    if kw.lower() in text_lower:
                        return True
        return False

    @staticmethod
    def _is_fading(audio_data: dict, w_start: float, total_dur: float) -> bool:
        if total_dur <= 0:
            return False
        if w_start < total_dur * 0.8:
            return False
        energy = audio_data.get("energy_curve", [])
        n = len(energy)
        if n < 4:
            return w_start > total_dur * 0.9
        i_start = int(w_start / total_dur * n)
        i_end = min(i_start + int(n * 0.05), n)
        i_start = max(0, min(i_start, n - 2))
        i_end = max(i_start + 2, min(i_end, n))
        if i_end - i_start < 2:
            return w_start > total_dur * 0.9
        first = sum(energy[i_start:i_start + 2]) / 2
        last = sum(energy[i_end - 2:i_end]) / 2
        return last < first * 0.7 if first > 0 else True

    @staticmethod
    def _has_silence_gap(audio_data: dict, start: float, end: float) -> bool:
        for gap in audio_data.get("silence_boundaries", []):
            if isinstance(gap, (tuple, list)) and len(gap) == 2:
                if gap[0] <= start <= gap[1] or gap[0] <= end <= gap[1]:
                    return True
            elif isinstance(gap, dict):
                gs = gap.get("start", -1)
                ge = gap.get("end", -1)
                if (gs <= start <= ge) or (gs <= end <= ge):
                    return True
        return False

    @staticmethod
    def _speech_per_window(
        audio_data: dict, windows: List[Tuple[float, float]]
    ) -> Dict[Tuple[float, float], float]:
        result: Dict[Tuple[float, float], float] = {}
        segments = audio_data.get("transcript_segments") or audio_data.get("speech_segments") or []
        for seg in segments:
            s = seg.get("start", seg.get("start_time", 0))
            e = seg.get("end", seg.get("end_time", 0))
            for ws, we in windows:
                overlap = min(e, we) - max(s, ws)
                if overlap > 0:
                    result[(ws, we)] = result.get((ws, we), 0.0) + overlap
        return result

    @staticmethod
    def _aggregate_visual_window(
        visual_features: List[dict], start: float, end: float
    ) -> dict:
        """Aggregate visual features within a time window.

        Frames are matched to the window by their frame_index. Returns a dict
        of aggregated values keyed by: face_presence, avg_face_ratio, avg_flow,
        avg_saturation, avg_edge_density, avg_entropy, min_brightness,
        max_hist_dist. All values are 0 if no frames match the window.
        """
        n = len(visual_features)
        if n == 0:
            return {}

        # Estimate which frame indices fall in the window
        total = max(vf.get("frame_index", 0) for vf in visual_features) + 1
        if total <= 1:
            total = n
        i_s = max(0, int(start / max(end, 0.01) * total))
        i_e = min(n, int(end / max(end, 0.01) * total) + 1)
        i_s = max(0, min(i_s, n - 1))
        i_e = max(i_s + 1, min(i_e, n))

        frames = visual_features[i_s:i_e]
        if not frames:
            return {}

        face_count = sum(f.get("face_count", 0) for f in frames)
        face_ratios = [f.get("face_area_ratio", 0) for f in frames]
        flows = [f.get("optical_flow_magnitude", 0) for f in frames]
        sats = [f.get("saturation_mean", 0) for f in frames]
        edges = [f.get("edge_density", 0) for f in frames]
        entropies = [f.get("gray_entropy", 0) for f in frames]
        brightnesses = [f.get("brightness_mean", 0) for f in frames]
        hist_dists = [f.get("histogram_distance", 0) for f in frames]

        # ── YOLO aggregation ──
        yolo_person = sum(f.get("yolo_person_count", 0) for f in frames)
        yolo_vehicle = sum(f.get("yolo_vehicle_count", 0) for f in frames)
        yolo_animal = sum(f.get("yolo_animal_count", 0) for f in frames)
        yolo_total = sum(f.get("yolo_total_objects", 0) for f in frames)
        yolo_classes: List[str] = []
        for f in frames:
            dom = f.get("yolo_dominant_class", "")
            if dom:
                yolo_classes.append(dom)

        return {
            "face_presence": face_count > 0,
            "avg_face_ratio": sum(face_ratios) / len(face_ratios),
            "avg_flow": sum(flows) / len(flows),
            "avg_saturation": sum(sats) / len(sats),
            "avg_edge_density": sum(edges) / len(edges),
            "avg_entropy": sum(entropies) / len(entropies),
            "min_brightness": min(brightnesses) if brightnesses else 255,
            "max_hist_dist": max(hist_dists) if hist_dists else 0.0,
            # YOLO
            "yolo_person_count": yolo_person,
            "yolo_vehicle_count": yolo_vehicle,
            "yolo_animal_count": yolo_animal,
            "yolo_total_objects": yolo_total,
            "yolo_dominant_classes": yolo_classes,
        }

    @staticmethod
    @staticmethod
    def _merge_adjacent(segments: List[dict]) -> List[dict]:
        """Merge adjacent same-type segments.

        Highlight segments use a tighter gap (0.8s) to preserve
        multiple discrete climax points; other types use 1.5s.
        """
        if not segments:
            return []
        merged = [segments[0].copy()]
        for seg in segments[1:]:
            prev = merged[-1]
            same_type = prev["structure_type"] == seg["structure_type"]
            is_unclassified = prev["structure_type"] == TYPE_UNCLASSIFIED
            # Highlights: only merge if nearly adjacent (multiple climax points)
            gap = 0.8 if prev["structure_type"] == TYPE_HIGHLIGHT else 1.5
            if same_type and not is_unclassified and abs(prev["end_time"] - seg["start_time"]) < gap:
                prev["end_time"] = seg["end_time"]
                prev["confidence"] = max(prev["confidence"], seg["confidence"])
                for e in seg["evidence"]:
                    if e not in prev["evidence"]:
                        prev["evidence"].append(e)
            else:
                merged.append(seg.copy())
        return merged

    # ──────────────────────────────────────────────────────
    #  Sub-type derivation: evidence → Chinese label
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _derive_sub_type(structure_type: str, evidence: list) -> str:
        """Map evidence signals to a fine-grained Chinese sub-label (19 types)."""
        ev_set = set(evidence)
        has_ocr = any("ocr_match" in e for e in ev_set)
        has_motion = any("visual_high_motion" in e or e.startswith("cut_rate_") for e in ev_set)
        has_energy = any(e.startswith("energy_peak_") for e in ev_set)
        has_face = any(
            "face" in e or "talking_head" in e or "visual_face" in e
            for e in ev_set
        )
        has_yolo = any(e.startswith("yolo_") for e in ev_set)
        has_flow_low = any("avg_flow" in e for e in ev_set)  # proxied
        is_fading = "energy_fading" in ev_set
        is_dark = "visual_dark_transition" in ev_set
        has_fade_out = "visual_fade_out" in ev_set
        has_color_shift = "visual_color_shift" in ev_set
        has_silence = "silence_gap" in ev_set
        has_speech = "high_speech_density" in ev_set
        is_short = any(e.startswith("short_segment_") for e in ev_set)
        has_still = has_flow_low and not has_motion

        if structure_type == "opening":
            if has_ocr and not has_face and not has_motion:
                return "标题卡"
            if has_ocr and has_face:
                return "人物引入"
            if has_yolo and has_face:
                return "人物引入"
            if has_motion and has_energy:
                return "悬念开场"
            if has_face and has_speech:
                return "人物引入"
            if has_ocr:
                return "品牌开场"
            return "环境铺垫"

        if structure_type == "highlight":
            if has_motion and has_energy and has_yolo:
                return "动作高燃"
            if has_speech and not has_motion:
                return "台词金句"
            if has_energy and not has_motion:
                return "情绪峰值"
            if has_motion and has_energy:
                return "动作高燃"
            if has_ocr and has_energy:
                return "视觉爆发"
            if has_motion:
                return "动作高燃"
            return "视觉爆发"

        if structure_type == "transition":
            if has_silence and is_dark:
                return "硬切"
            if has_color_shift and not is_dark:
                return "匹配剪辑"
            if has_motion and has_color_shift:
                return "滑动转场"
            if has_color_shift and is_dark:
                return "淡入淡出"
            if is_dark:
                return "硬切"
            return "硬切"

        if structure_type == "effect":
            if has_motion and has_energy and is_short:
                return "视觉特效"
            if is_short:
                return "闪切插入"
            return "视觉特效"

        if structure_type == "closing":
            if has_ocr and has_still:
                return "品牌露出"
            if is_fading and has_fade_out:
                return "同步淡出"
            if is_fading and not has_fade_out:
                return "音乐淡出"
            if has_still and not has_ocr:
                return "画面定格"
            if has_fade_out and not is_fading:
                return "黑场淡出"
            if has_ocr:
                return "字幕滚动"
            if is_fading:
                return "音乐淡出"
            return "同步淡出"

        return "未分类"
