"""Pipeline orchestrator — coordinates signal → filter → understand → script.

The Pipeline class is the central coordinator that runs the full analysis
workflow.  Heavy ML deps (OpenCV, Whisper, Librosa, Tesseract) are lazily
imported only when the pipeline executes.

Child modules:
    pipeline_detail.py   — per-segment detail assembly
    pipeline_modules.py  — segment → module tree mapping
    pipeline_result.py   — result dict assembly
    pipeline_config.py   — centralised thresholds
"""

import os
import math
import concurrent.futures
from typing import Any, Dict, List, Optional

# Lightweight imports (always available)
from understanding.filter.adaptive_sampler import AdaptiveSampler
from understanding.understand.structure import StructureInferrer

from understanding.pipeline_config import (
    ETA_BASE_PER_SEC, ETA_WHISPER_PER_SEC,
    ETA_OCR_PER_FRAME, ETA_YOLO_PER_FRAME,
    ETA_API_PER_FRAME, ETA_AUDIO_PER_SEC,
    OCR_BATCH_SIZE, OCR_MAX_WORKERS,
    DIFF_ACTIVITY_THRESHOLD,
    BPM_FALLBACK_BASE, BPM_FALLBACK_SCALE,
    CONTENT_SAMPLE_INTERVAL_SEC,
    CONTENT_ENTROPY_THRESHOLD,
    CONTENT_EDGE_DENSITY_MAX,
)
from understanding.pipeline_modules import build_module_tree
from understanding.pipeline_result import assemble_result


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
    4. Module tree: build typed modules with per-segment detail

    Supports checkpoint-based resume: pass ``video_id`` to ``analyze_video``
    to persist intermediate artifacts.  On re-run, completed stages are
    loaded from disk.

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
        self._frame_diff: Optional[Any] = None
        self._scene_detector: Optional[Any] = None
        self._transcriber: Optional[Any] = None
        self._audio_analyzer: Optional[Any] = None
        self._ocr: Optional[Any] = None
        self._frame_extractor: Optional[Any] = None
        self._sampler: Optional[AdaptiveSampler] = None
        self._structure: Optional[StructureInferrer] = None

        # Checkpoint / resume state (lazy-initialised when video_id is set)
        self._job_store: Any = None
        self._video_id: str = ""

    # ── Checkpoint helpers ─────────────────────────────────────────

    def _init_checkpoint(self, video_id: str) -> None:
        """Lazy-init the JobStore for checkpointed runs."""
        if self._job_store is not None and self._video_id == video_id:
            return
        from backend.store import JobStore
        self._job_store = JobStore("analysis", base_dir=self.work_dir)
        self._video_id = video_id

    def _is_stage_done(self, stage: str) -> bool:
        """Check if a pipeline stage is already completed."""
        if self._job_store is None:
            return False
        cp = self._job_store.get_checkpoint(self._video_id)
        return stage in cp.get("completed_stages", [])

    def _save_artifact(self, name: str, data: Any) -> None:
        """Persist intermediate data and update checkpoint."""
        if self._job_store is None:
            return
        self._job_store.save_artifact(self._video_id, name, data)
        self._job_store.update_checkpoint(self._video_id, name)

    def _load_checkpointed(self, name: str) -> Any:
        """Load a previously-saved artifact, or None if missing."""
        if self._job_store is None:
            return None
        return self._job_store.load_artifact(self._video_id, name)

    # ── Main entry point ───────────────────────────────────────────

    def analyze_video(self, video_path: str, video_id: str = "", video_type: str = "vlog") -> Dict[str, Any]:
        """Run the full analysis pipeline on a video.

        Args:
            video_path: Absolute path to the input video file.
            video_id: Optional job identifier for checkpointed resume.
            video_type: Video type preset key (one of VIDEO_TYPE_PRESETS,
                        default "vlog" for general-purpose analysis).

        Returns:
            Dict with keys: signal_data, keyframes, structure, module_tree.

        Raises:
            FileNotFoundError: If video_path does not exist.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        if video_id:
            self._init_checkpoint(video_id)

        # ── Stage 1: Signal Layer (4 parallel sub-stages) ──
        signal_data = self._run_signal_layer(
            video_path, self._video_id, self._job_store,
        )
        if self.on_progress:
            dur = signal_data.get("total_duration", 0)
            scenes = len(signal_data.get("scene_boundaries", []))
            segs = len(signal_data.get("transcript_segments", []))
            self.on_progress("信号采集", f"完成 — 时长: {dur:.1f}s, 场景: {scenes}个, 语音段: {segs}个")

        # ── Stage 2: Filter Layer (keyframe sampling) ──
        if self._is_stage_done("filter_sampler"):
            keyframes = self._load_checkpointed("filter_sampler") or []
            if self.on_progress:
                self.on_progress("帧筛选", f"(恢复) {len(keyframes)} 个关键帧")
        else:
            if self.on_progress:
                self.on_progress("帧筛选", "自适应采样中…")
            keyframes = self._run_filter_layer(
                signal_data["diff_curve"],
                signal_data["scene_boundaries"],
                signal_data.get("fps", 30.0),
            )
            if self._job_store:
                self._save_artifact("filter_sampler", keyframes)
            if self.on_progress:
                self.on_progress("帧筛选", f"完成 — {len(keyframes)} 个关键帧")

        # ── Stage 2b: Content-based sampling (second channel) ──
        # Captures informative static frames missed by diff-based sampler.
        content_keyframes = self._run_content_sampler(
            video_path, signal_data.get("fps", 30.0),
            signal_data.get("total_duration", 0.0),
        )
        if content_keyframes:
            # Merge: diff-based first, content supplements; dedup by frame_index
            existing_indices = {kf["frame_index"] for kf in keyframes}
            added = 0
            for ckf in content_keyframes:
                if ckf["frame_index"] not in existing_indices:
                    keyframes.append(ckf)
                    existing_indices.add(ckf["frame_index"])
                    added += 1
            # Sort by frame_index to keep timeline order
            keyframes.sort(key=lambda kf: kf["frame_index"])
            if self.on_progress and added > 0:
                self.on_progress("帧筛选", f"内容采样 +{added} 静态帧 → 共 {len(keyframes)} 个关键帧")

        # ── Stage 2.5: OCR on keyframes ──
        if self._is_stage_done("ocr_keyframes"):
            ocr_results = self._load_checkpointed("ocr_keyframes") or []
            if self.on_progress:
                self.on_progress("文字识别", f"(恢复) {len(ocr_results)} 帧")
        else:
            if self.on_progress:
                self.on_progress("文字识别", "OCR 关键帧文字提取…")
            ocr_results = self._run_ocr_on_keyframes(video_path, keyframes)
            if self._job_store:
                self._save_artifact("ocr_keyframes", ocr_results)
            if self.on_progress:
                self.on_progress("文字识别", f"完成 — {len(ocr_results)} 帧")

        # ── Stage 3: Understand Layer ──
        if self._is_stage_done("structure"):
            structure_segments = self._load_checkpointed("structure") or []
            if self.on_progress:
                self.on_progress("规则引擎", f"(恢复) {len(structure_segments)} 个叙事段")
            # Also restore visual_features into signal_data for module tree building
            vf = self._load_checkpointed("visual_features")
            if vf:
                signal_data["visual_features"] = vf
        else:
            if self.on_progress:
                self.on_progress("规则引擎", "结构推断 + 视觉特征分析…")
            structure_segments = self._run_understand_layer(
                keyframes, signal_data, ocr_results, video_path, video_type=video_type,
            )
            if self._job_store:
                self._save_artifact("visual_features",
                                    signal_data.get("visual_features", []))
                self._save_artifact("structure", structure_segments)
            if self.on_progress:
                self.on_progress("规则引擎", f"完成 — {len(structure_segments)} 个叙事段")

        # ── Stage 4: Build Module Tree ──
        if self._is_stage_done("script_build"):
            module_tree = self._load_checkpointed("script_build") or []
            if self.on_progress:
                self.on_progress("Pipeline", f"(恢复) {len(module_tree)} 个模块")
        else:
            transcripts = signal_data.get("transcript_segments", [])
            energy = signal_data.get("audio_data", {}).get("energy_curve") or signal_data.get("diff_curve", [])
            dur_total = signal_data.get("total_duration", 0.0)
            bpm = signal_data.get("audio_data", {}).get("bpm", 0)
            ocr_data = ocr_results or signal_data.get("ocr_results", [])

            module_tree = build_module_tree(
                structure_segments=structure_segments,
                transcripts=transcripts,
                energy=energy,
                dur_total=dur_total,
                bpm=bpm,
                ocr_data=ocr_data,
                video_path=video_path,
                visual_features=signal_data.get("visual_features"),
                audio_data=signal_data.get("audio_data"),
            )
            if self._job_store:
                self._save_artifact("script_build", module_tree)
            if self.on_progress:
                self.on_progress("Pipeline", f"模块树生成完成 — {len(module_tree)} 个模块")

        return assemble_result(
            signal_data=signal_data,
            keyframes=keyframes,
            structure_segments=structure_segments,
            module_tree=module_tree,
        )

    # ── Signal Layer ────────────────────────────────────────────────

    def _run_signal_layer(
        self,
        video_path: str,
        video_id: str = "",
        job_store: Any = None,
    ) -> Dict[str, Any]:
        """Execute all signal layer analysis in parallel, with checkpoint
        support — each of the 4 sub-tasks is independently checkable.

        Already-completed sub-tasks are loaded from artifact storage;
        only the remaining ones run via ThreadPoolExecutor.
        """
        import logging
        _log = logging.getLogger(__name__)

        # ── Determine which sub-tasks need to run ──
        need_diff = not self._is_stage_done("frame_diff")
        need_scene = not self._is_stage_done("scene_detect")
        need_transcribe = not self._is_stage_done("audio_transcribe")
        need_audio = not self._is_stage_done("audio_analysis")

        # ── Bootstrap results from checkpointed data ──
        results: Dict[str, Any] = {
            "diff_curve": [], "diff_timestamps": [],
            "scene_boundaries": [], "transcript_segments": [],
            "audio_data": {}, "ocr_results": [],
            "fps": 30.0, "total_duration": 0.0,
        }

        if job_store:
            diff_art = job_store.load_artifact(video_id, "frame_diff")
            if diff_art:
                results["diff_curve"] = diff_art.get("diff_curve", [])
                results["diff_timestamps"] = diff_art.get("diff_timestamps", [])
                results["fps"] = diff_art.get("fps", 30.0)
                results["total_duration"] = diff_art.get("total_duration", 0.0)

            scene_art = job_store.load_artifact(video_id, "scene_detect")
            if scene_art:
                results["scene_boundaries"] = scene_art.get("scene_boundaries", [])

            trans_art = job_store.load_artifact(video_id, "audio_transcribe")
            if trans_art:
                results["transcript_segments"] = trans_art.get("transcript_segments", [])

            audio_art = job_store.load_artifact(video_id, "audio_analysis")
            if audio_art:
                results["audio_data"] = audio_art

        # ── Task wrappers ──

        def _frame_diff():
            try:
                if self._frame_diff is None:
                    FrameDiffAnalyzer = _lazy_import(
                        "understanding.signal.frame_diff", "FrameDiffAnalyzer"
                    )
                    self._frame_diff = FrameDiffAnalyzer()
                d, t = self._frame_diff.calc_diff_curve_with_timestamps(video_path)
                return ("diff", d, t)
            except Exception as e:
                _log.warning("Frame diff failed: %s", e)
                return None

        def _scene_detect():
            try:
                if self._scene_detector is None:
                    SceneDetector = _lazy_import(
                        "understanding.signal.scene_detect", "SceneDetector"
                    )
                    self._scene_detector = SceneDetector()
                return ("scene", self._scene_detector.detect(video_path))
            except Exception as e:
                _log.warning("Scene detection failed: %s", e)
                return None

        def _transcribe():
            try:
                if self._transcriber is None:
                    AudioTranscriber = _lazy_import(
                        "understanding.signal.audio_transcribe", "AudioTranscriber"
                    )
                    self._transcriber = AudioTranscriber()
                return ("transcript", self._transcriber.transcribe(video_path))
            except Exception as e:
                _log.warning("Audio transcription failed: %s", e)
                return None

        def _audio_analysis():
            try:
                if self._audio_analyzer is None:
                    AudioAnalyzer = _lazy_import(
                        "understanding.signal.audio_analysis", "AudioAnalyzer"
                    )
                    self._audio_analyzer = AudioAnalyzer()
                return ("audio", self._audio_analyzer.analyze(video_path))
            except Exception as e:
                _log.warning("Audio analysis failed: %s", e)
                return None

        # ── Build task list (only incomplete sub-tasks) ──
        tasks = []
        if need_diff:
            tasks.append(("diff", _frame_diff))
        if need_scene:
            tasks.append(("scene", _scene_detect))
        if need_transcribe:
            tasks.append(("transcript", _transcribe))
        if need_audio:
            tasks.append(("audio", _audio_analysis))

        if tasks:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                future_map = {pool.submit(fn): kind for kind, fn in tasks}
                for f in concurrent.futures.as_completed(future_map):
                    kind = future_map[f]
                    r = f.result()
                    if r is None:
                        continue
                    self._merge_signal_result(results, kind, r[1] if len(r) > 1 else None, r)

            # ── Persist artifacts for newly-completed sub-tasks ──
            if job_store:
                for kind, _ in tasks:
                    if kind == "diff" and results.get("diff_curve"):
                        job_store.save_artifact(video_id, "frame_diff", {
                            "diff_curve": results["diff_curve"],
                            "diff_timestamps": results["diff_timestamps"],
                            "fps": results["fps"],
                            "total_duration": results["total_duration"],
                        })
                        job_store.update_checkpoint(video_id, "frame_diff")
                    elif kind == "scene" and results.get("scene_boundaries"):
                        job_store.save_artifact(video_id, "scene_detect", {
                            "scene_boundaries": results["scene_boundaries"],
                        })
                        job_store.update_checkpoint(video_id, "scene_detect")
                    elif kind == "transcript" and results.get("transcript_segments"):
                        job_store.save_artifact(video_id, "audio_transcribe", {
                            "transcript_segments": results["transcript_segments"],
                        })
                        job_store.update_checkpoint(video_id, "audio_transcribe")
                    elif kind == "audio" and results.get("audio_data"):
                        job_store.save_artifact(video_id, "audio_analysis",
                                                results["audio_data"])
                        job_store.update_checkpoint(video_id, "audio_analysis")
        else:
            _log.info("Signal layer: all 4 sub-tasks loaded from checkpoint")

        return results

    @staticmethod
    def _merge_signal_result(
        results: Dict[str, Any], kind: str, payload: Any, raw: Any,
    ) -> None:
        """Merge one signal sub-task result into the results dict."""
        if kind == "diff":
            diff_curve, timestamps = raw[1], raw[2]
            results["diff_curve"] = diff_curve
            results["diff_timestamps"] = timestamps
            if timestamps:
                results["total_duration"] = timestamps[-1]
                if results["total_duration"] > 0 and diff_curve:
                    results["fps"] = len(diff_curve) / results["total_duration"]
        elif kind == "scene":
            results["scene_boundaries"] = payload
        elif kind == "transcript":
            results["transcript_segments"] = payload
        elif kind == "audio":
            results["audio_data"] = payload

    # ── Filter Layer ────────────────────────────────────────────────

    def _run_filter_layer(
        self,
        diff_curve: List[float],
        scene_boundaries: List[float],
        fps: float,
    ) -> List[dict]:
        """Run adaptive sampler to get keyframe list."""
        if self._sampler is None:
            self._sampler = AdaptiveSampler()
        return self._sampler.sample_with_context(diff_curve, scene_boundaries, fps)

    # ── OCR on Keyframes ────────────────────────────────────────────

    # ── Content-based Sampling (second channel) ─────────────────────

    def _run_content_sampler(
        self,
        video_path: str,
        fps: float,
        total_duration: float,
    ) -> List[dict]:
        """Run content-based sampler to capture informative static frames.

        Lazy-imports ContentSampler; errors are logged and return an empty list
        so the pipeline continues uninterrupted.
        """
        if total_duration <= 0:
            return []
        try:
            ContentSampler = _lazy_import(
                "understanding.filter.content_sampler", "ContentSampler"
            )
            sampler = ContentSampler(
                interval_sec=CONTENT_SAMPLE_INTERVAL_SEC,
                entropy_threshold=CONTENT_ENTROPY_THRESHOLD,
                edge_density_max=CONTENT_EDGE_DENSITY_MAX,
            )
            return sampler.sample(video_path, fps, total_duration)
        except Exception:
            import logging
            _log = logging.getLogger(__name__)
            _log.debug("Content sampler skipped (load error)", exc_info=True)
            return []

    def _run_ocr_on_keyframes(
        self,
        video_path: str,
        keyframes: List[dict],
    ) -> List[dict]:
        """Run OCR on keyframe images extracted from the video."""
        import logging
        _log = logging.getLogger(__name__)

        try:
            if self._ocr is None:
                OCRExtractor = _lazy_import("understanding.signal.ocr_extract", "OCRExtractor")
                self._ocr = OCRExtractor()

            if self._frame_extractor is None:
                FrameExtractor = _lazy_import(
                    "understanding.signal.frame_extractor", "FrameExtractor"
                )
                self._frame_extractor = FrameExtractor(work_dir=self.work_dir)

            frame_indices = [kf["frame_index"] for kf in keyframes]
            if not frame_indices:
                return []

            frame_paths = self._frame_extractor.extract(
                video_path, frame_indices, video_id="ocr"
            )
            if not frame_paths:
                return []

            ocr_results: List[dict] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=OCR_MAX_WORKERS) as pool:
                batches = [
                    frame_paths[i:i + OCR_BATCH_SIZE]
                    for i in range(0, len(frame_paths), OCR_BATCH_SIZE)
                ]
                futures = [pool.submit(self._ocr.extract, b) for b in batches]
                for f in concurrent.futures.as_completed(futures):
                    try:
                        ocr_results.extend(f.result())
                    except Exception:
                        pass

            # Inject real timestamps from keyframe data
            ts_map = {kf["frame_index"]: kf.get("timestamp", 0.0) for kf in keyframes}
            for item in ocr_results:
                fp = item.get("frame_path", "")
                m = __import__("re").search(r"frame_(\d+)", fp)
                if m:
                    fidx = int(m.group(1))
                    item["timestamp"] = ts_map.get(fidx, 0.0)

            return ocr_results
        except Exception as e:
            _log.warning("OCR on keyframes failed (skipping): %s", e)
            return []

    # ── Understand Layer ────────────────────────────────────────────

    def _run_understand_layer(
        self,
        keyframes: List[dict],
        signal_data: Dict[str, Any],
        ocr_results: List[dict],
        video_path: str = "",
        video_type: str = "vlog",
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
                source, len(visual_features), len(frame_descriptions),
                result.get("api_time", 0),
            )
        except Exception as e:
            _log.warning("Full visual feature pipeline failed: %s", e)

        return self._run_structure_inference(
            frame_descriptions, signal_data, ocr_results, visual_features,
            video_type=video_type,
        )

    def _run_structure_inference(
        self,
        frame_descriptions: List[dict],
        signal_data: Dict[str, Any],
        ocr_results: List[dict],
        visual_features: List[dict],
        video_type: str = "vlog",
    ) -> List[dict]:
        """Structure inference from all available signals.

        Args:
            video_type: Video-type preset key passed through to
                        StructureInferrer.infer(preset=...).
        """
        import logging
        _log = logging.getLogger(__name__)

        # Inject into signal_data so downstream build_module_tree can use them
        signal_data["visual_features"] = visual_features

        if self._structure is None:
            self._structure = StructureInferrer()

        # Load video-type preset
        from understanding.pipeline_config import VIDEO_TYPE_PRESETS
        preset = VIDEO_TYPE_PRESETS.get(video_type, VIDEO_TYPE_PRESETS["vlog"])

        # Merge data from signal layer into audio_data
        audio_for_infer = dict(signal_data.get("audio_data", {}))
        if not audio_for_infer.get("duration"):
            audio_for_infer["duration"] = signal_data.get("total_duration", 0.0)
        if not audio_for_infer.get("total_duration"):
            audio_for_infer["total_duration"] = signal_data.get("total_duration", 0.0)
        if not audio_for_infer.get("scene_boundaries"):
            audio_for_infer["scene_boundaries"] = signal_data.get("scene_boundaries", [])
        if not audio_for_infer.get("transcript_segments"):
            audio_for_infer["transcript_segments"] = signal_data.get("transcript_segments", [])
        if not audio_for_infer.get("speech_segments"):
            audio_for_infer["speech_segments"] = signal_data.get("transcript_segments", [])

        if not audio_for_infer.get("energy_curve"):
            audio_data_raw = signal_data.get("audio_data", {})
            if audio_data_raw.get("energy_curve"):
                audio_for_infer["energy_curve"] = audio_data_raw["energy_curve"]
            else:
                _log.info("audio_data missing energy_curve, falling back to diff_curve")
                audio_for_infer["energy_curve"] = signal_data.get("diff_curve", [])

        if not audio_for_infer.get("bpm"):
            diff = signal_data.get("diff_curve", [])
            if diff:
                high = len([d for d in diff if d > DIFF_ACTIVITY_THRESHOLD]) / max(len(diff), 1)
                audio_for_infer["bpm"] = BPM_FALLBACK_BASE + high * BPM_FALLBACK_SCALE

        structure_segments = self._structure.infer(
            frame_descriptions,
            audio_for_infer,
            ocr_results,
            visual_features=visual_features if visual_features else None,
            preset=preset,
        )

        return structure_segments

    # ── ETA estimation ─────────────────────────────────────────────

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
        base = duration_s * ETA_BASE_PER_SEC
        whisper = duration_s * ETA_WHISPER_PER_SEC if has_whisper else 0
        ocr = keyframe_count * ETA_OCR_PER_FRAME
        yolo = keyframe_count * ETA_YOLO_PER_FRAME if has_yolo else 0
        api = keyframe_count * ETA_API_PER_FRAME if has_api else 0
        audio = duration_s * ETA_AUDIO_PER_SEC

        return base + whisper + ocr + yolo + api + audio
