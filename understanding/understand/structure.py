"""Narrative structure inference from multi-modal signal data.

Combines visual descriptions, audio transcripts, beat density, silence
boundaries, and OCR results to infer narrative segment types:
Hook / Talking Head / Montage / Conversion / Outro.
"""

from typing import List, Optional


class StructureInferrer:
    """Infers narrative structure by combining all signal + understanding data.

    Classification rules:

    | Signal Combination                            | Inferred Structure |
    |------------------------------------------------|--------------------|
    | Title text (first 3-5s) + BGM fade-in         | Hook               |
    | Person close-up + speech > 30s                | Talking Head       |
    | Rapid multi-shot alternation + high BPM       | Montage            |
    | Text + price/CTA present                      | Conversion         |
    | Fade to dark at end + logo                    | Outro              |
    """

    # Duration threshold for Talking Head classification
    TALKING_HEAD_MIN_DURATION = 30.0

    # BPM threshold for Montage classification
    HIGH_BPM_THRESHOLD = 120

    def infer(
        self,
        frame_descriptions: List[dict],
        audio_data: dict,
        ocr_data: List[dict],
        confidence_threshold: float = 0.6,
    ) -> List[dict]:
        """Infer narrative structure segments from combined signals.

        Uses rule-based classification (no LLM needed) by partitioning the
        video timeline at scene boundaries and silence gaps, then applying
        classify_segment() rules to each window. Works fully offline when
        frame_descriptions is empty — falls back to audio + OCR signals.

        Args:
            frame_descriptions: Output from VisionAnalyzer.analyze().
                Each dict has: frame_path, description, detected_objects, scene_type.
                May be empty if no vision API is configured.
            audio_data: Output from AudioAnalyzer.analyze().
                Has: bpm, beat_times, energy_curve, silence_boundaries.
            ocr_data: Output from OCRExtractor.extract().
                Each dict has: frame_path, text_regions.
            confidence_threshold: Minimum confidence to assign a structure type.
                Segments below threshold are marked 'unclassified'.

        Returns:
            List of narrative segment dicts, each containing:
                - start_time: float
                - end_time: float
                - structure_type: str (hook / talking_head / montage /
                    conversion / outro / unclassified)
                - confidence: float (0.0-1.0)
                - evidence: List[str] human-readable reasons
        """
        segments: List[dict] = []

        # ── 1. Build timeline windows ──
        total_duration = audio_data.get("duration", 0.0)
        if total_duration <= 0:
            # Estimate from other sources
            total_duration = max(
                audio_data.get("total_duration", 0.0),
                self._max_ocr_timestamp(ocr_data),
            )

        if total_duration <= 0:
            return []  # Nothing to analyze

        # Collect boundary points: scene boundaries + silence gaps
        boundaries = set()

        # Scene boundaries (from PySceneDetect)
        for sb in audio_data.get("scene_boundaries", []):
            if isinstance(sb, (int, float)):
                boundaries.add(round(sb, 1))
            elif isinstance(sb, dict):
                boundaries.add(round(sb.get("timestamp", sb.get("start", 0)), 1))

        # Silence boundaries (audio-based segmentation)
        for sb in audio_data.get("silence_boundaries", []):
            if isinstance(sb, (int, float)):
                boundaries.add(round(sb, 1))
            elif isinstance(sb, dict):
                boundaries.add(round(sb.get("start", 0), 1))
                boundaries.add(round(sb.get("end", 0), 1))
            elif isinstance(sb, (tuple, list)) and len(sb) == 2:
                boundaries.add(round(sb[0], 1))
                boundaries.add(round(sb[1], 1))

        # Also sample regular intervals if boundaries are sparse
        window_size = 10.0
        t = 0.0
        while t < total_duration:
            boundaries.add(round(t, 1))
            t += window_size

        boundaries.add(0.0)
        boundaries.add(round(total_duration, 1))

        sorted_bounds = sorted(b for b in boundaries if b <= total_duration)

        if len(sorted_bounds) < 2:
            return []

        # ── 2. Detect whether OCR / vision data is available ──
        has_ocr = len(ocr_data) > 0
        has_vision = len(frame_descriptions) > 0

        # Count scene boundaries per window for montage detection
        scene_boundaries_list = sorted(
            b for b in audio_data.get("scene_boundaries", [])
            if isinstance(b, (int, float))
        )

        # ── 3. Classify each window ──
        for i in range(len(sorted_bounds) - 1):
            seg_start = sorted_bounds[i]
            seg_end = sorted_bounds[i + 1]
            if seg_end - seg_start < 1.0:
                continue  # Skip windows shorter than 1s

            # --- Extract signals ---
            has_title_text = self._has_ocr_keyword(
                ocr_data, seg_start, min(seg_start + 5, seg_end),
                ["title", "标题", "第", "episode", "vol"],
            )
            has_price_cta = self._has_ocr_keyword(
                ocr_data, seg_start, seg_end,
                ["¥", "$", "€", "元", "价格", "buy", "购买", "点击", "subscribe",
                 "订阅", "扫码", "咨询", "免费", "优惠", "限时"],
            )
            has_logo = self._has_ocr_keyword(
                ocr_data, max(seg_start, seg_end - 10), seg_end,
                ["logo", "关注", "follow", "subscribe", "订阅"],
            )
            speech_duration = self._speech_in_window(
                audio_data, seg_start, seg_end
            )

            has_person_closeup = self._guess_person_presence(
                frame_descriptions, seg_start, seg_end, speech_duration
            )

            bpm = audio_data.get("bpm", 0)
            window_bpm = bpm

            is_fade_out = self._is_fade_window(
                audio_data, seg_start, seg_end, total_duration
            )

            window_descriptions = self._descriptions_in_window(
                frame_descriptions, seg_start, seg_end
            )

            # Count cuts in this window — high = montage
            cuts_in_window = sum(
                1 for b in scene_boundaries_list
                if seg_start <= b <= seg_end
            )

            # --- Hierarchical classification ---
            # Priority: position > activity > OCR/vision rules
            if seg_start < 8.0 and i == 0:
                structure_type = "hook"
                confidence = 0.75
                evidence = ["position_opening"]
            elif seg_start > total_duration * 0.8:
                structure_type = "outro"
                confidence = 0.75
                evidence = ["position_closing"]
            elif cuts_in_window >= 2:
                structure_type = "montage"
                confidence = 0.65
                evidence = [f"rapid_cuts_{cuts_in_window}"]
            elif speech_duration > 45:
                structure_type = "talking_head"
                confidence = 0.68
                evidence = ["sustained_speech"]
            else:
                # Fall through to signal-based classify_segment
                structure_type, confidence, evidence = self.classify_segment(
                    descriptions=window_descriptions,
                    has_title_text=has_title_text,
                    has_person_closeup=has_person_closeup,
                    has_price_cta=has_price_cta,
                    has_logo=has_logo,
                    speech_duration=speech_duration,
                    bpm=window_bpm,
                    is_fade_out=is_fade_out,
                )

            if confidence >= confidence_threshold:
                segments.append({
                    "start_time": seg_start,
                    "end_time": seg_end,
                    "structure_type": structure_type,
                    "confidence": confidence,
                    "evidence": evidence,
                })

        # ── 3. Merge adjacent same-type segments ──
        merged = self._merge_adjacent(segments)

        return merged


    # ── Signal extraction helpers ──

    @staticmethod
    def _max_ocr_timestamp(ocr_data: List[dict]) -> float:
        """Get the latest timestamp from OCR data."""
        max_t = 0.0
        for item in ocr_data:
            ts = item.get("timestamp", 0)
            if ts > max_t:
                max_t = ts
        return max_t

    @staticmethod
    def _has_ocr_keyword(
        ocr_data: List[dict],
        t_start: float,
        t_end: float,
        keywords: List[str],
    ) -> bool:
        """Check if any OCR text in the time window contains a keyword."""
        for item in ocr_data:
            ts = item.get("timestamp", -1)
            if ts < 0 or ts < t_start or ts > t_end:
                continue
            regions = item.get("text_regions", [])
            if isinstance(regions, list):
                for region in regions:
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
    def _guess_person_presence(
        frame_descriptions: List[dict],
        t_start: float,
        t_end: float,
        speech_duration: float = 0.0,
    ) -> bool:
        """Check if vision API reported person close-ups in window.

        If no vision data available, falls back to a speech-duration
        heuristic: sustained speech > 45s strongly suggests a person
        speaking on camera (talking head format).
        """
        # First, check vision API data if available
        for fd in frame_descriptions:
            ts = fd.get("timestamp", -1)
            if ts < 0 or ts < t_start or ts > t_end:
                continue
            scene_type = fd.get("scene_type", "")
            objects = fd.get("detected_objects", [])
            if scene_type == "talking_head":
                return True
            if "person" in objects or "face" in objects or "人物" in objects:
                return True

        # Fallback: no vision API — use speech duration as proxy
        # Long continuous speech almost always means someone talking to camera
        if speech_duration > 45.0:
            return True

        return False

    @staticmethod
    def _speech_in_window(
        audio_data: dict,
        t_start: float,
        t_end: float,
    ) -> float:
        """Estimate total speech duration within the time window."""
        total = 0.0
        segments = audio_data.get("transcript_segments", [])
        if not segments:
            segments = audio_data.get("speech_segments", [])
        for seg in segments:
            s = seg.get("start", seg.get("start_time", 0))
            e = seg.get("end", seg.get("end_time", 0))
            # Overlap with window
            overlap_start = max(s, t_start)
            overlap_end = min(e, t_end)
            if overlap_end > overlap_start:
                total += overlap_end - overlap_start
        return total

    @staticmethod
    def _is_fade_window(
        audio_data: dict,
        t_start: float,
        t_end: float,
        total_duration: float,
    ) -> bool:
        """Check if this window is near the end and has fading audio."""
        # Must be in the last 20% of the video
        if total_duration <= 0:
            return False
        if t_start < total_duration * 0.8:
            return False
        # Check for decreasing energy
        energy = audio_data.get("energy_curve", [])
        if not energy:
            return True  # Near end with no energy data → likely outro
        # Simple check: split window energy, compare first half vs second
        n = len(energy)
        if n < 4:
            return True
        # Map window to energy indices (rough)
        duration = audio_data.get("duration", total_duration)
        if duration <= 0:
            return True
        i_start = int(t_start / duration * n)
        i_end = int(t_end / duration * n)
        i_start = max(0, min(i_start, n - 1))
        i_end = max(i_start + 1, min(i_end, n))
        window_energy = energy[i_start:i_end]
        if len(window_energy) < 2:
            return True
        mid = len(window_energy) // 2
        first_half = sum(window_energy[:mid]) / max(mid, 1)
        second_half = sum(window_energy[mid:]) / max(len(window_energy) - mid, 1)
        return second_half < first_half * 0.7

    @staticmethod
    def _descriptions_in_window(
        frame_descriptions: List[dict],
        t_start: float,
        t_end: float,
    ) -> List[str]:
        """Collect natural-language descriptions from vision API in window."""
        texts: List[str] = []
        for fd in frame_descriptions:
            ts = fd.get("timestamp", -1)
            if ts < 0 or ts < t_start or ts > t_end:
                continue
            desc = fd.get("description", "")
            if desc:
                texts.append(desc)
        return texts

    @staticmethod
    def _merge_adjacent(segments: List[dict]) -> List[dict]:
        """Merge adjacent segments that share the same structure_type.

        Unclassified segments are never merged — they represent
        distinct sections of the video that should remain separate.
        """
        if not segments:
            return []
        merged = [segments[0].copy()]
        for seg in segments[1:]:
            prev = merged[-1]
            if (
                prev["structure_type"] != "unclassified"
                and prev["structure_type"] == seg["structure_type"]
                and abs(prev["end_time"] - seg["start_time"]) < 2.0
            ):
                # Merge: extend previous segment
                prev["end_time"] = seg["end_time"]
                prev["confidence"] = max(prev["confidence"], seg["confidence"])
                prev["evidence"].extend(
                    e for e in seg["evidence"] if e not in prev["evidence"]
                )
            else:
                merged.append(seg.copy())
        return merged

    def classify_segment(
        self,
        descriptions: List[str],
        has_title_text: bool,
        has_person_closeup: bool,
        has_price_cta: bool,
        has_logo: bool,
        speech_duration: float,
        bpm: float,
        is_fade_out: bool,
    ) -> tuple:
        """Classify a single time segment based on signal evidence.

        Args:
            descriptions: Vision descriptions for frames in this segment.
            has_title_text: Whether title-style text is detected.
            has_person_closeup: Whether a person close-up is detected.
            has_price_cta: Whether price/CTA text is detected.
            has_logo: Whether a logo is detected.
            speech_duration: Total speech duration in this segment (seconds).
            bpm: Estimated BPM for this segment.
            is_fade_out: Whether segment ends with fade-out.

        Returns:
            Tuple of (structure_type, confidence, evidence_list).
        """
        evidence: List[str] = []

        # Rule 1: Hook — title at start with BGM
        if has_title_text:
            evidence.append("title_text_detected")
            return ("hook", 0.85, evidence)

        # Rule 2: Talking Head — person close-up with sustained speech
        if has_person_closeup and speech_duration > self.TALKING_HEAD_MIN_DURATION:
            evidence.append("person_closeup_with_speech")
            return ("talking_head", 0.80, evidence)

        # Rule 3: Montage — high BPM with rapid cuts
        if bpm >= self.HIGH_BPM_THRESHOLD:
            evidence.append("high_bpm")
            return ("montage", 0.70, evidence)

        # Rule 4: Conversion — price/CTA present
        if has_price_cta:
            evidence.append("price_cta_detected")
            return ("conversion", 0.90, evidence)

        # Rule 5: Outro — fade-out with logo
        if is_fade_out and has_logo:
            evidence.append("fade_out_with_logo")
            return ("outro", 0.85, evidence)

        # Unclassified
        evidence.append("insufficient_signal")
        return ("unclassified", 0.30, evidence)
