"""Pipeline orchestrator: chains signal → filter → understand → script layers.

The Pipeline class is the central orchestrator that coordinates the
end-to-end video analysis workflow.

Heavy ML dependencies (OpenCV, Whisper, Librosa, Tesseract, SceneDetect)
are lazily imported only when the analysis pipeline is actually executed,
so the backend server can start without them installed.
"""

import math

import os
import uuid
import concurrent.futures
from typing import Any, Dict, List, Optional

# Lightweight imports (always available — no heavy ML deps)
from understanding.filter.adaptive_sampler import AdaptiveSampler

from understanding.understand.structure import StructureInferrer


def _lazy_import(module_path: str, attr: str):
    """Import a module attribute on demand (for heavy ML dependencies)."""
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


class Pipeline:
    """End-to-end video analysis pipeline.

    Flow:
    1. Signal layer: frame_diff + scene_detect + audio_transcribe +
       audio_analysis + ocr
    2. Filter layer: adaptive_sampler → keyframe list
    3. Understand layer: vision (LLM) + structure_inferrer
    4. Script layer: build MigratableScript JSON

    Attributes:
        work_dir: Working directory for intermediate artifacts.
        vision_api_url: Endpoint for multimodal LLM API.
        vision_api_key: Authentication key for LLM API.
    """

    def __init__(
        self,
        work_dir: str = "",
        vision_api_url: str = "",
        vision_api_key: str = "",
        vision_model: str = "qwen-vl-max",
        vision_provider: str = "local",
        on_progress=None,
    ) -> None:
        self.work_dir = work_dir or os.getcwd()
        self.vision_api_url = vision_api_url
        self.vision_api_key = vision_api_key
        self.vision_model = vision_model
        self.vision_provider = vision_provider
        self.on_progress = on_progress  # callable(tag, msg) or None

        # Lazy-initialized components
        self._frame_diff: Optional[Any] = None  # FrameDiffAnalyzer
        self._scene_detector: Optional[Any] = None  # SceneDetector
        self._transcriber: Optional[Any] = None  # AudioTranscriber
        self._audio_analyzer: Optional[Any] = None  # AudioAnalyzer
        self._ocr: Optional[Any] = None  # OCRExtractor
        self._frame_extractor: Optional[Any] = None  # FrameExtractor
        self._sampler: Optional[AdaptiveSampler] = None
        self._structure: Optional[StructureInferrer] = None

    def analyze_video(self, video_path: str) -> Dict[str, Any]:
        """Run the full analysis pipeline on a video.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            Dict containing:
                - signal_data: Raw signal outputs
                - keyframes: Sampled keyframe indices
                - structure: Narrative structure segments
                - module_tree: Structured module tree ready for script building

        Raises:
            FileNotFoundError: If video_path does not exist.
            RuntimeError: If any pipeline stage fails.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        # --- Stage 1: Signal Layer ---
        if self.on_progress: self.on_progress("信号采集", "开始提取视频元数据、场景检测、音频分析…")
        signal_data = self._run_signal_layer(video_path)
        if self.on_progress: self.on_progress("信号采集", f"完成 — 时长: {signal_data.get('total_duration', 0):.1f}s, 场景: {len(signal_data.get('scene_boundaries', []))}个, 语音段: {len(signal_data.get('transcript_segments', []))}个")

        # --- Stage 2: Filter Layer ---
        if self.on_progress: self.on_progress("帧筛选", "自适应采样中…")
        keyframes = self._run_filter_layer(
            signal_data["diff_curve"],
            signal_data["scene_boundaries"],
            signal_data.get("fps", 30.0),
        )
        if self.on_progress: self.on_progress("帧筛选", f"完成 — {len(keyframes)} 个关键帧")

        # --- Stage 2.5: OCR on Keyframes ---
        if self.on_progress: self.on_progress("文字识别", "OCR 关键帧文字提取…")
        ocr_results = self._run_ocr_on_keyframes(video_path, keyframes)
        if self.on_progress: self.on_progress("文字识别", f"完成 — {len(ocr_results)} 帧")

        # --- Stage 3: Understand Layer ---
        if self.on_progress: self.on_progress("规则引擎", "结构推断 + 视觉特征分析…")
        structure_segments = self._run_understand_layer(
            keyframes, signal_data, ocr_results, video_path
        )
        if self.on_progress: self.on_progress("规则引擎", f"完成 — {len(structure_segments)} 个叙事段")

        # --- Stage 4: Build Module Tree ---
        module_tree = self._build_module_tree(
            structure_segments, signal_data, video_path, ocr_results,
            signal_data.get("visual_features")
        )
        if self.on_progress: self.on_progress("Pipeline", f"模块树生成完成 — {len(module_tree)} 个模块")

        return {
            "signal_data": signal_data,
            "keyframes": keyframes,
            "structure": structure_segments,
            "module_tree": module_tree,
        }

    def _run_signal_layer(self, video_path: str) -> Dict[str, Any]:
        """Execute all signal layer analysis in parallel.

        Frame diff, scene detection, audio transcription, and audio analysis
        all run concurrently via ThreadPoolExecutor. Each component is
        independently error-tolerant.
        """
        import logging
        _log = logging.getLogger(__name__)

        results: Dict[str, Any] = {
            "diff_curve": [], "diff_timestamps": [],
            "scene_boundaries": [], "transcript_segments": [],
            "audio_data": {}, "ocr_results": [],
            "fps": 30.0, "total_duration": 0.0,
        }

        def _frame_diff():
            try:
                if self._frame_diff is None:
                    FrameDiffAnalyzer = _lazy_import("understanding.signal.frame_diff", "FrameDiffAnalyzer")
                    self._frame_diff = FrameDiffAnalyzer()
                d, t = self._frame_diff.calc_diff_curve_with_timestamps(video_path)
                return ("diff", d, t)
            except Exception as e:
                _log.warning("Frame diff failed: %s", e)
                return None

        def _scene_detect():
            try:
                if self._scene_detector is None:
                    SceneDetector = _lazy_import("understanding.signal.scene_detect", "SceneDetector")
                    self._scene_detector = SceneDetector()
                return ("scene", self._scene_detector.detect(video_path))
            except Exception as e:
                _log.warning("Scene detection failed: %s", e)
                return None

        def _transcribe():
            try:
                if self._transcriber is None:
                    AudioTranscriber = _lazy_import("understanding.signal.audio_transcribe", "AudioTranscriber")
                    self._transcriber = AudioTranscriber()
                return ("transcript", self._transcriber.transcribe(video_path))
            except Exception as e:
                _log.warning("Audio transcription failed: %s", e)
                return None

        def _audio_analysis():
            try:
                if self._audio_analyzer is None:
                    AudioAnalyzer = _lazy_import("understanding.signal.audio_analysis", "AudioAnalyzer")
                    self._audio_analyzer = AudioAnalyzer()
                return ("audio", self._audio_analyzer.analyze(video_path))
            except Exception as e:
                _log.warning("Audio analysis failed: %s", e)
                return None

        # Run all 4 signal collectors in parallel (Whisper is the bottleneck)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(_frame_diff),
                pool.submit(_scene_detect),
                pool.submit(_transcribe),
                pool.submit(_audio_analysis),
            ]
            for f in concurrent.futures.as_completed(futures):
                r = f.result()
                if r is None:
                    continue
                kind = r[0]
                if kind == "diff":
                    diff_curve, timestamps = r[1], r[2]
                    results["diff_curve"] = diff_curve
                    results["diff_timestamps"] = timestamps
                    if timestamps:
                        results["total_duration"] = timestamps[-1] if timestamps else 0.0
                        if results["total_duration"] > 0 and diff_curve:
                            results["fps"] = len(diff_curve) / results["total_duration"]
                elif kind == "scene":
                    results["scene_boundaries"] = r[1]
                elif kind == "transcript":
                    results["transcript_segments"] = r[1]
                elif kind == "audio":
                    results["audio_data"] = r[1]

        return results

    def _run_filter_layer(
        self,
        diff_curve: List[float],
        scene_boundaries: List[float],
        fps: float,
    ) -> List[dict]:
        """Run adaptive sampler to get keyframe list.

        Returns:
            List of dicts with frame_index, timestamp, diff_value, is_boundary.
        """
        if self._sampler is None:
            self._sampler = AdaptiveSampler()
        return self._sampler.sample_with_context(
            diff_curve, scene_boundaries, fps
        )

    def _run_ocr_on_keyframes(
        self,
        video_path: str,
        keyframes: List[dict],
    ) -> List[dict]:
        """Run OCR on keyframe images extracted from the video.

        Extracts frame images at each keyframe index using FrameExtractor,
        then runs Tesseract OCR on each image to detect on-screen text regions.

        Args:
            video_path: Absolute path to the input video file.
            keyframes: List of keyframe dicts from AdaptiveSampler, each
                containing ``frame_index``, ``timestamp``, etc.

        Returns:
            List of OCR result dicts, each containing ``frame_path`` and
            ``text_regions`` (see OCRExtractor.extract for schema).
        """
        try:
            # Initialize OCR engine (lazy-import: pytesseract)
            if self._ocr is None:
                OCRExtractor = _lazy_import("understanding.signal.ocr_extract", "OCRExtractor")
                self._ocr = OCRExtractor()

            # Initialize frame extractor (lazy-import: OpenCV)
            if self._frame_extractor is None:
                FrameExtractor = _lazy_import("understanding.signal.frame_extractor", "FrameExtractor")
                self._frame_extractor = FrameExtractor(work_dir=self.work_dir)

            frame_indices = [kf["frame_index"] for kf in keyframes]
            if not frame_indices:
                return []

            # Extract frame images at keyframe indices
            frame_paths = self._frame_extractor.extract(
                video_path, frame_indices, video_id="ocr"
            )

            if not frame_paths:
                return []

            # Run OCR in parallel batches of 8 frames
            ocr_results: List[dict] = []
            batch_size = 8
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                batches = [frame_paths[i:i+batch_size] for i in range(0, len(frame_paths), batch_size)]
                futures = [pool.submit(self._ocr.extract, b) for b in batches]
                for f in concurrent.futures.as_completed(futures):
                    try:
                        ocr_results.extend(f.result())
                    except Exception:
                        pass

            # Inject real timestamps from keyframe data.
            # OCRExtractor hardcodes timestamp=0.0; override with the
            # actual keyframe timestamp so downstream time-window filters
            # can match OCR results to the correct segment.
            ts_map = {kf["frame_index"]: kf.get("timestamp", 0.0) for kf in keyframes}
            for item in ocr_results:
                fp = item.get("frame_path", "")
                # Match frame index from filename pattern: frame_00042.png
                m = __import__("re").search(r"frame_(\d+)", fp)
                if m:
                    fidx = int(m.group(1))
                    item["timestamp"] = ts_map.get(fidx, 0.0)

            return ocr_results
        except Exception as e:
            import logging
            _log = logging.getLogger(__name__)
            _log.warning("OCR on keyframes failed (skipping): %s", e)
            return []

    def _run_understand_layer(
        self,
        keyframes: List[dict],
        signal_data: Dict[str, Any],
        ocr_results: List[dict],
        video_path: str = "",
    ) -> List[dict]:
        """Run vision analysis, visual features, and structure inference.

        Degradation chain:
          1. External vision API (if provider="api" and api_url set)
          2. Local YOLO + OpenCV
          3. OpenCV-only (zero-model)
        """
        import logging
        _log = logging.getLogger(__name__)

        frame_descriptions: List[dict] = []
        visual_features: List[dict] = []

        if not keyframes:
            return self._run_structure_inference(
                frame_descriptions, signal_data, ocr_results, visual_features
            )

        # Extract frames first
        try:
            if self._frame_extractor is None:
                FrameExtractor = _lazy_import(
                    "understanding.signal.frame_extractor", "FrameExtractor"
                )
                self._frame_extractor = FrameExtractor(work_dir=self.work_dir, downscale=True)
            frame_indices = [kf["frame_index"] for kf in keyframes]
            extracted_paths = self._frame_extractor.extract(
                video_path, frame_indices, video_id=os.path.basename(video_path)
            )
        except Exception as e:
            _log.warning("Frame extraction failed: %s", e)
            extracted_paths = []

        if not extracted_paths:
            return self._run_structure_inference(
                frame_descriptions, signal_data, ocr_results, visual_features
            )

        # ── Degradation chain via VisualFeatureExtractor ──
        try:
            VisualFeatureExtractor = _lazy_import(
                "understanding.signal.visual_features", "VisualFeatureExtractor"
            )
            vfe = VisualFeatureExtractor()
            vfe.set_provider(
                provider=self.vision_provider or "local",
                api_url=self.vision_api_url,
                api_key=self.vision_api_key,
                model=self.vision_model,
            )
            result = vfe.analyze_frames(extracted_paths)
            visual_features = result.get("features", [])
            frame_descriptions = result.get("descriptions", [])
            source = result.get("source", "opencv")
            _log.info(
                "Visual features from %s: %d frames, %d descriptions (api_time=%.2fs)",
                source, len(visual_features), len(frame_descriptions), result.get("api_time", 0),
            )
        except Exception as e:
            _log.warning("Full visual feature pipeline failed: %s", e)

        return self._run_structure_inference(
            frame_descriptions, signal_data, ocr_results, visual_features
        )

    def _run_structure_inference(
        self,
        frame_descriptions: List[dict],
        signal_data: Dict[str, Any],
        ocr_results: List[dict],
        visual_features: List[dict],
    ) -> List[dict]:
        """Structure inference from all available signals."""
        import logging
        _log = logging.getLogger(__name__)

        # Inject into signal_data so downstream _build_module_tree can use them
        signal_data["visual_features"] = visual_features

        # Structure inference
        if self._structure is None:
            self._structure = StructureInferrer()

        # Merge data from signal layer into audio_data so that
        # structure inferrer has a rich set of signals even if some
        # components (Whisper, Librosa) failed.
        audio_for_infer = dict(signal_data.get("audio_data", {}))
        if not audio_for_infer.get("duration"):
            audio_for_infer["duration"] = signal_data.get("total_duration", 0.0)
        if not audio_for_infer.get("total_duration"):
            audio_for_infer["total_duration"] = signal_data.get("total_duration", 0.0)
        # Inject scene boundaries — critical for segment partitioning
        if not audio_for_infer.get("scene_boundaries"):
            audio_for_infer["scene_boundaries"] = signal_data.get("scene_boundaries", [])
        # Inject transcript segments if available
        if not audio_for_infer.get("transcript_segments"):
            audio_for_infer["transcript_segments"] = signal_data.get("transcript_segments", [])
        if not audio_for_infer.get("speech_segments"):
            audio_for_infer["speech_segments"] = signal_data.get("transcript_segments", [])
        # Use real audio RMS energy curve; diff_curve is frame pixel difference,
        # not audio energy — only use as last resort when audio analysis failed entirely.
        if not audio_for_infer.get("energy_curve"):
            audio_data_raw = signal_data.get("audio_data", {})
            if audio_data_raw.get("energy_curve"):
                audio_for_infer["energy_curve"] = audio_data_raw["energy_curve"]
            else:
                _log.info("audio_data missing energy_curve, falling back to diff_curve")
                audio_for_infer["energy_curve"] = signal_data.get("diff_curve", [])
        # Estimate BPM from frame activity if not available
        if not audio_for_infer.get("bpm"):
            diff = signal_data.get("diff_curve", [])
            if diff:
                high = len([d for d in diff if d > 0.1]) / max(len(diff), 1)
                audio_for_infer["bpm"] = 80 + high * 100

        structure_segments = self._structure.infer(
            frame_descriptions,
            audio_for_infer,
            ocr_results,
            visual_features=visual_features if visual_features else None,
        )

        return structure_segments

    # ── ETA estimation ────────────────────────────────────────────

    @staticmethod
    def estimate_eta(
        duration_s: float,
        fps: float = 30.0,
        has_whisper: bool = True,
        has_yolo: bool = False,
        has_api: bool = False,
        keyframe_count: int = 60,
    ) -> float:
        """Estimate analysis time in seconds from video parameters.

        Formula (CPU baseline, not GPU):
          base       = duration * 0.3     (OpenCV frame diff + scene detect)
          whisper    = duration * 0.8     (Whisper small, single-thread)
          ocr        = keyframes * 0.15   (Tesseract per frame)
          yolo       = keyframes * 0.08   (YOLOv8n inference)
          api        = keyframes * 0.3    (external API network latency)
          audio      = duration * 0.1     (librosa BPM + energy)

        Returns total estimated seconds.
        """
        base = duration_s * 0.3
        whisper = duration_s * 0.8 if has_whisper else 0
        ocr = keyframe_count * 0.15
        yolo = keyframe_count * 0.08 if has_yolo else 0
        api = keyframe_count * 0.3 if has_api else 0
        audio = duration_s * 0.1

        return base + whisper + ocr + yolo + api + audio

    # ── Module tree building ──────────────────────────────────────

    def _build_module_tree(
        self,
        structure_segments: List[dict],
        signal_data: Dict[str, Any],
        video_path: str = "",
        ocr_results: Optional[List[dict]] = None,
        visual_features: Optional[List[dict]] = None,
    ) -> List[Dict[str, Any]]:
        """Convert structure segments into a 5-type module tree with detail.

        Each module includes a `detail` dict with per-segment analysis
        extracted from real signal data (transcript, energy, OCR, BPM).
        """
        modules: List[Dict[str, Any]] = []
        transcripts = signal_data.get("transcript_segments", [])
        # Prefer real audio RMS energy_curve over diff_curve (pixel diff)
        energy = signal_data.get("audio_data", {}).get("energy_curve") or signal_data.get("diff_curve", [])
        dur_total = signal_data.get("total_duration", 0.0)
        bpm = signal_data.get("audio_data", {}).get("bpm", 0)
        ocr_data = ocr_results or signal_data.get("ocr_results", [])

        # ── Global watermark scan: texts appearing across multiple segments ──
        from collections import defaultdict
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
        watermark_set = {t for t, segs in ocr_seg_map.items()
                         if len(segs) >= max(2, int(num_segs * 0.4))}

        for i, seg in enumerate(structure_segments):
            seg_type = seg.get("structure_type", "unclassified")
            seg_label = seg.get("label", f"segment_{i}")
            start_time = seg.get("start_time", 0.0)
            end_time = seg.get("end_time", start_time)
            duration = max(end_time - start_time, 0.0)
            evidence = seg.get("evidence", [])
            reason = ", ".join(evidence[:2]) if evidence else ""

            # ── Build per-module detail from signals ──
            sub_type = seg.get("sub_type", "")
            detail = self._build_detail(
                seg_type, sub_type, start_time, end_time, duration,
                evidence, transcripts, energy, dur_total, bpm, ocr_data,
                visual_features, watermark_set
            )

            base = {
                "id": uuid.uuid4().hex[:12],
                "start_time": start_time, "duration": duration,
                "label": seg_label, "children": [],
                "detail": detail,
            }

            if seg_type == "opening":
                modules.append({**base, "track_index": 1, "type": "title",
                    "params": {"text_content": seg_label, "animation": "fade_in"}})

            elif seg_type == "highlight":
                modules.append({**base, "track_index": 0, "type": "video_segment",
                    "source": {"type": "video", "path": video_path}})

            elif seg_type == "transition":
                modules.append({**base, "track_index": 0, "type": "transition",
                    "params": {"transition_type": "dissolve"}})

            elif seg_type == "effect":
                modules.append({**base, "track_index": 3, "type": "effect",
                    "params": {"transition_type": "fade"}})

            elif seg_type == "closing":
                modules.append({**base, "track_index": 0, "type": "video_segment"})
                modules.append({**base, "track_index": 3, "type": "effect",
                    "label": f"{seg_label}_outro",
                    "params": {"transition_type": "fade_out"}})

            else:
                modules.append({**base, "track_index": 0, "type": "video_segment"})

        return modules

    @staticmethod
    def _build_detail(
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
        watermark_set: Optional[set] = None,
    ) -> Dict[str, Any]:
        """Build per-module analysis detail from real signal data."""
        # ── Scene tags: prefer sub_type (from evidence) over generic type map ──
        fallback_map = {
            "opening": ["引入", "铺垫", "建置"],
            "highlight": ["战斗爆发", "对决", "名场面"],
            "transition": ["场景切换", "时间跳转"],
            "effect": ["慢动作", "粒子", "变速"],
            "closing": ["情感回落", "告别", "谢幕"],
        }
        if sub_type and sub_type != "未分类":
            scene_tags = [sub_type]
        else:
            scene_tags = fallback_map.get(seg_type, ["未知"])

        # ── Visual elements: visual_features primary, OCR supplement ──
        vf_desc = _derive_visual_from_features(visual_features, start, end, total_dur)

        # OCR: collect all text, then filter noise
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

        ocr_clean = _filter_ocr_noise(ocr_raw)

        if ocr_clean:
            # Supplement: meaningful OCR text enriches visual description
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
                if var > 0.01:
                    color_tone = "高对比度"
                elif avg > 0.05:
                    color_tone = "暖色调"
                else:
                    color_tone = "冷色调"

        # ── BGM type from BPM ──
        if bpm > 120:
            bgm_type = "激昂 / 紧张"
        elif bpm > 80:
            bgm_type = "明快 / 活泼"
        elif bpm > 50:
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
        # energy_peak_value: normalized RMS energy peak (0~1), higher = more intense
        # energy_peak_offset: relative time offset within segment when peak occurs (seconds)
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
        # Build human-readable label
        if energy_peak_value <= 0:
            emotion_peak = "无"
        elif energy_peak_value > 0.8:
            emotion_peak = f"高 ({energy_peak_value:.2f}, +{energy_peak_offset:.1f}s)"
        elif energy_peak_value > 0.5:
            emotion_peak = f"中 ({energy_peak_value:.2f}, +{energy_peak_offset:.1f}s)"
        else:
            emotion_peak = f"低 ({energy_peak_value:.2f}, +{energy_peak_offset:.1f}s)"

        # ── High-freq words: ASR voice lines first, OCR supplement ──
        # Voice content carries real semantics; OCR is often noisy watermarks
        voice_text = " ".join(voice_lines).strip()
        if voice_text:
            # Tokenize Chinese/English words from speech
            import re as _re_hf
            speech_tokens = _re_hf.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{4,}", voice_text)
            high_freq = speech_tokens[:5] if speech_tokens else voice_lines[:3]
        else:
            # No speech: use filtered OCR as fallback
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
            ocr_freq_clean = _filter_ocr_noise(ocr_freq_raw)
            if ocr_freq_clean:
                high_freq = ocr_freq_clean[:5]
            else:
                _fallback_freq = {
                    "opening": ["#片头"],
                    "highlight": ["#高光"],
                    "transition": ["#转场"],
                    "effect": ["#特效"],
                    "closing": ["#片尾"],
                }
                high_freq = _fallback_freq.get(seg_type, ["#未分类"])

        # ── Sentiment from keyword matching ──
        positive_kw = ["燃", "炸", "绝了", "高能", "神", "帅", "厉害", "精彩", "期待"]
        negative_kw = ["完结", "再见", "结束"]
        all_text = " ".join(ocr_clean + voice_lines)
        pos = sum(1 for kw in positive_kw if kw in all_text)
        neg = sum(1 for kw in negative_kw if kw in all_text)
        if pos > neg:
            sentiment = "正面/激昂"
        elif neg > pos:
            sentiment = "负面/低落"
        else:
            sentiment = "中性"

        return {
            "scene_tags": scene_tags,
            "visual_elements": visual_elements[:5],
            "color_tone": color_tone,
            "bgm_type": bgm_type,
            "voice_content": voice_content,
            "emotion_peak": emotion_peak,
            "energy_peak_value": round(energy_peak_value, 3),
            "energy_peak_offset": round(energy_peak_offset, 2),
            "high_freq_words": high_freq,
            "sentiment": sentiment,
        }


def _derive_visual_from_features(
    visual_features: Optional[List[dict]], start: float, end: float, total_dur: float
) -> List[str]:
    """Derive human-readable visual descriptions — 框架 → 内容 → 动效.

    Three-layer hierarchy (content-agnostic to concrete):

      框架层 (transferable across scenes):
        - 构图: composition_type from _analyze_composition, fallback heuristic
        - 光照: brightness-based (暗调 / 正常 / 明亮)
        - 色彩: saturation-based (高饱和暖色 / 低饱和冷色)

      内容层 (scene-specific):
        - 物体: YOLO per-class count + spatial position

      动效层 (temporal continuity):
        - 动效: optical-flow + histogram-distance based motion label
    """
    from collections import Counter, defaultdict

    if not visual_features or total_dur <= 0:
        return ["无"]

    n = len(visual_features)
    i_s = max(0, int(start / total_dur * n))
    i_e = min(n, int(end / total_dur * n) + 1)
    i_s = max(0, min(i_s, n - 1))
    i_e = max(i_s + 1, min(i_e, n))
    frames = visual_features[i_s:i_e]
    if not frames:
        return ["无"]

    # ── Aggregate OpenCV signals ──
    fc = sum(f.get("face_count", 0) for f in frames)
    far = sum(f.get("face_area_ratio", 0) for f in frames) / max(len(frames), 1)
    fl = sum(f.get("optical_flow_magnitude", 0) for f in frames) / len(frames)
    sat = sum(f.get("saturation_mean", 0) for f in frames) / len(frames)
    bm = sum(f.get("brightness_mean", 0) for f in frames) / len(frames)
    hd = sum(f.get("histogram_distance", 0) for f in frames) / len(frames)

    # ── Aggregate YOLO objects ──
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

    _VEHICLE_NAMES = {"car", "truck", "bus", "motorcycle", "bicycle", "train", "boat", "aeroplane", "airplane"}
    _ANIMAL_NAMES = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}
    yolo_person_cnt = class_counts.get("person", 0)
    yolo_vehicle_cnt = sum(class_counts[k] for k in class_counts if k in _VEHICLE_NAMES)
    yolo_animal_cnt = sum(class_counts[k] for k in class_counts if k in _ANIMAL_NAMES)

    # ── Spatial position helper ──
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
        if avg_cx < 0.33:
            parts_pos.append("画面左侧")
        elif avg_cx > 0.66:
            parts_pos.append("画面右侧")
        else:
            parts_pos.append("画面中央")
        if avg_cy < 0.33:
            parts_pos.append("上方")
        elif avg_cy > 0.66:
            parts_pos.append("下方")
        return "（" + "、".join(parts_pos) + "）" if parts_pos else ""

    result: List[str] = []

    # ════════════════════════════════════════
    #  框架层 — content-agnostic, transferable
    # ════════════════════════════════════════

    # ── 构图: use composition_type from _analyze_composition; fallback heuristic ──
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
        # Fallback heuristic
        _heuristic = ""
        if fc >= 1 and far > 0.08:
            _heuristic = "人物特写"
        elif fc >= 2 and far < 0.04:
            _heuristic = "群像/全景"
        elif len(all_objs) > 5:
            _heuristic = "复杂"
        elif len(all_objs) < 3:
            _heuristic = "简洁"
        if _heuristic:
            result.append(f"构图: {_heuristic}构图")

    # ── 光照: brightness-based ──
    if bm < 25:
        result.append("光照: 暗调/夜场景")
    elif bm > 180:
        result.append("光照: 明亮日间场景")
    else:
        result.append("光照: 正常光照")

    # ── 色彩: saturation-based ──
    if sat > 100:
        result.append("色彩: 暖色调（高饱和）")
    else:
        result.append("色彩: 冷色调（低饱和）")

    # ════════════════════════════
    #  内容层 — concrete objects
    # ════════════════════════════

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
        if name not in seen_top_classes and name not in _ANIMAL_NAMES | _VEHICLE_NAMES
    ]
    for name, cnt in other_classes[:3]:
        pos = _avg_position(class_bboxes.get(name, []))
        obj_parts.append(f"{name}×{cnt}{pos}" if cnt >= 3 else f"{name}{pos}")
        seen_top_classes.add(name)

    if yolo_vehicle_cnt > 0:
        pos = ""
        for name in _VEHICLE_NAMES:
            if name in class_counts:
                pos = _avg_position(class_bboxes.get(name, []))
                break
        if yolo_vehicle_cnt >= 3:
            obj_parts.append(f"车辆×{yolo_vehicle_cnt}{pos}")
        else:
            vehicle_names = [k for k in class_counts if k in _VEHICLE_NAMES]
            obj_parts.append(f"含{'、'.join(vehicle_names)}{pos}")

    if yolo_animal_cnt > 0:
        pos = ""
        animal_names = [k for k in class_counts if k in _ANIMAL_NAMES]
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

    # ═════════════════════════
    #  动效层 — motion effects
    # ═════════════════════════

    if fl < 3 and hd < 0.2:
        motion = "静止定镜"
    elif 3 <= fl <= 8:
        motion = "轻微晃动"
    elif 8 < fl <= 15:
        motion = "缓推镜头 / 平移跟随"
    elif 15 < fl <= 25 and hd < 0.3:
        motion = "快速摇镜"
    elif fl > 25 and hd > 0.5:
        motion = "剧烈切换"
    elif fl >= 15:
        motion = "画面运动"
    elif fl < 3:
        motion = "静止定镜"
    else:
        motion = "画面运动"

    result.append(f"动效: {motion}（光流均值 {fl:.1f}）")

    return result


def _filter_ocr_noise(raw: List[str]) -> List[str]:
    """Remove OCR noise: single chars, short gibberish, consecutive duplicates.

    Returns a deduplicated list of meaningful text snippets.
    """
    import re
    seen: set = set()
    clean: List[str] = []

    for t in raw:
        t = t.strip()
        if not t:
            continue

        # ── Length filter ──
        if len(t) < 2:
            continue

        # ── Pure punctuation / special chars ──
        if re.fullmatch(r"[^\w\u4e00-\u9fff]+", t):
            continue

        # ── Short ASCII-only garbage (like "AN", "rm", "up", "are") ──
        if len(t) <= 3 and re.fullmatch(r"[a-zA-Z]+", t):
            continue

        # ── Purely numeric short strings ──
        if len(t) <= 3 and t.isdigit():
            continue

        # ── Deduplicate ──
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)

        clean.append(t)

    return clean
