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

import logging
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
    VIDEO_TYPE_CONFIDENCE_THRESHOLD,
    VIDEO_TYPE_PRESETS,
    STAGE1_TASK_TIMEOUT,
    STAGE2_TRANSCRIBE_TIMEOUT,
    STAGE3_OCR_TIMEOUT,
    FRAME_DIFF_SOFT_TIMEOUT,
    SCENE_DETECT_SOFT_TIMEOUT,
    ANALYZE_VIDEO_GLOBAL_TIMEOUT,
)
from understanding.pipeline_modules import build_module_tree
from understanding.pipeline_result import assemble_result

# Structured logging — used inside Pipeline
from backend.log_config import StructuredLogger

_STRUCTURED_LOG = StructuredLogger("pipeline")


def _lazy_import(module_path: str, attr: str):
    """Import a module attribute on demand (for heavy ML dependencies)."""
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


def _pre_import_signal_deps(pipeline: Any, stage1: list) -> None:
    """Pre-import heavy ML dependencies on the **main thread** before
    spawning worker threads.

    This avoids a class of deadlock where two threads simultaneously
    hit ``_lazy_import`` for the same module — Python's import lock
    can serialize them, but if one thread is already blocked on I/O
    (e.g. cv2.VideoCapture), the other thread waiting on the import
    lock will never wake up.

    Only triggers the lazy-init on ``pipeline``; does not run any
    actual analysis.
    """
    import logging
    _log = logging.getLogger(__name__)

    kinds = {k for k, _ in stage1}

    if "diff" in kinds and pipeline._frame_diff is None:
        try:
            FrameDiffAnalyzer = _lazy_import(
                "understanding.signal.frame_diff", "FrameDiffAnalyzer"
            )
            pipeline._frame_diff = FrameDiffAnalyzer()
            _log.debug("Pre-imported FrameDiffAnalyzer on main thread")
        except Exception:
            _log.debug("FrameDiffAnalyzer pre-import skipped (will retry in thread)")

    if "scene" in kinds and pipeline._scene_detector is None:
        try:
            SceneDetector = _lazy_import(
                "understanding.signal.scene_detect", "SceneDetector"
            )
            pipeline._scene_detector = SceneDetector()
            _log.debug("Pre-imported SceneDetector on main thread")
        except Exception:
            _log.debug("SceneDetector pre-import skipped")

    if "audio" in kinds and pipeline._audio_analyzer is None:
        try:
            AudioAnalyzer = _lazy_import(
                "understanding.signal.audio_analysis", "AudioAnalyzer"
            )
            pipeline._audio_analyzer = AudioAnalyzer()
            _log.debug("Pre-imported AudioAnalyzer on main thread")
        except Exception:
            _log.debug("AudioAnalyzer pre-import skipped")

    if "vad" in kinds and getattr(pipeline, '_vad_detector', None) is None:
        try:
            VADDetector = _lazy_import(
                "understanding.signal.vad_detect", "VADDetector"
            )
            pipeline._vad_detector = VADDetector()
            _log.debug("Pre-imported VADDetector on main thread")
        except Exception:
            _log.debug("VADDetector pre-import skipped")


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

    """

    def __init__(
        self,
        work_dir: str = "",
        on_progress=None,
    ) -> None:
        self.work_dir = work_dir or os.getcwd()
        self.on_progress = on_progress  # callable(tag, msg) or None

        # Lazy-initialized components
        self._frame_diff: Optional[Any] = None
        self._scene_detector: Optional[Any] = None
        self._transcriber: Optional[Any] = None
        self._audio_analyzer: Optional[Any] = None
        self._vad_detector: Optional[Any] = None
        self._ocr: Optional[Any] = None
        self._frame_extractor: Optional[Any] = None
        self._sampler: Optional[AdaptiveSampler] = None
        self._structure: Optional[StructureInferrer] = None
        self._vad_detector: Optional[Any] = None
        self._video_classifier: Optional[Any] = None

        # Checkpoint / resume state (lazy-initialised when video_id is set)
        self._job_store: Any = None
        self._video_id: str = ""
        # Global timeout result (populated by _run_pipeline_body)
        self._last_result: Optional[Dict[str, Any]] = None

    # ── Resource cleanup (memory, CUDA caches) ─────────────────────

    def cleanup(self) -> None:
        """Release all lazy-loaded models and free GPU memory.

        Call this after ``analyze_video()`` returns (or fails) to
        ensure that Whisper (~1 GB), OpenCV capture states, and
        any Torch tensors are garbage-collected promptly.

        Safe to call multiple times — already-``None`` fields are
        skipped.
        """
        import logging
        _log = logging.getLogger(__name__)

        # ── Release model references (allow GC to collect them) ──
        released = False
        for attr in (
            "_frame_diff", "_scene_detector", "_transcriber",
            "_audio_analyzer", "_vad_detector", "_ocr",
            "_frame_extractor", "_sampler", "_structure",
            "_video_classifier",
        ):
            obj = getattr(self, attr, None)
            if obj is not None:
                setattr(self, attr, None)
                released = True

        if released:
            _log.debug("Pipeline.cleanup(): released model references")

        # ── Free Torch CUDA cache ──
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                _log.debug("Pipeline.cleanup(): torch.cuda.empty_cache()")
        except ImportError:
            pass  # torch not installed — no GPU memory to manage

        # ── Close JobStore connection ──
        if self._job_store is not None:
            try:
                self._job_store.close()
            except Exception:
                pass
            self._job_store = None
            self._video_id = ""

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

    def _heartbeat(self) -> None:
        """Touch the heartbeat timestamp for the current job.

        Called after each major stage completes so that a crash
        between stages can be detected quickly by ``list_stale()``.
        """
        if self._job_store is None or not self._video_id:
            return
        try:
            self._job_store.update_heartbeat(self._video_id)
        except Exception:
            pass

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

    def analyze_video(self, video_path: str, video_id: str, video_type: str = "vlog") -> Dict[str, Any]:
        """Run the full analysis pipeline on a video.

        Each major stage is wrapped in try/except — on failure the error
        is written to the job store and re-raised as ``AnalysisError``.

        **video_id is required** — the pipeline always uses checkpointed
        storage so that interrupted runs can be resumed.

        Args:
            video_path: Absolute path to the input video file.
            video_id: Job identifier for checkpointed resume (required).
            video_type: Video type preset key (one of VIDEO_TYPE_PRESETS,
                        default "vlog" for general-purpose analysis).

        Returns:
            Dict with keys: signal_data, keyframes, structure, module_tree.

        Raises:
            FileNotFoundError: If video_path does not exist.
            AnalysisError: If any pipeline stage fails.
        """
        _log = logging.getLogger(__name__)

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        if not video_id:
            import uuid
            video_id = uuid.uuid4().hex[:16]
            _log.warning("No video_id provided — auto-generated %s", video_id)

        self._init_checkpoint(video_id)
        if self._job_store:
            self._job_store.create_job(
                job_id=video_id,
                type="analysis",
                input_path=video_path,
                status="processing",
            )
            self._job_store.update_heartbeat(video_id)

        # ── Global timeout guard: run body in thread with timeout ──
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _timeout_exec:
            _future = _timeout_exec.submit(
                self._run_pipeline_body,
                video_path, video_id, video_type, _log,
            )
            try:
                _future.result(timeout=ANALYZE_VIDEO_GLOBAL_TIMEOUT)
            except concurrent.futures.TimeoutError:
                _log.error(
                    "Pipeline timed out after %ds — saving partial results",
                    ANALYZE_VIDEO_GLOBAL_TIMEOUT,
                )
                if self._job_store and video_id:
                    self._job_store.set_status(video_id, "partial")
                    self._job_store.set_error(video_id,
                        f"Pipeline timed out after {ANALYZE_VIDEO_GLOBAL_TIMEOUT}s")
                from backend.middleware.error_handler import AnalysisError
                raise AnalysisError(
                    message=f"Pipeline timed out after {ANALYZE_VIDEO_GLOBAL_TIMEOUT}s",
                    details={"video_id": video_id, "status": "partial"},
                    recoverable=True,
                )

        return self._last_result

    def _run_pipeline_body(
        self, video_path: str, video_id: str, video_type: str,
        _log: logging.Logger,
    ) -> None:
        """Inner body of analyze_video, wrapped by global timeout."""
        # (result stored on self._last_result for timeout path)
        self._last_result = None

        # ── Structured log with per-analysis context ──
        slog = _STRUCTURED_LOG.child(video_id=video_id, video_type=video_type)

        def _fail(stage: str, exc: Exception) -> None:
            """Record error in job store and re-raise as AnalysisError."""
            msg = f"[{stage}] {exc}"
            slog.error(
                "Pipeline stage failed",
                stage=stage, error=str(exc), **slog.elapsed(),
            )
            if self._job_store and video_id:
                self._job_store.set_error(video_id, msg)
            from backend.middleware.error_handler import AnalysisError
            raise AnalysisError(
                message=msg,
                details={"stage": stage, "video_id": video_id},
            ) from exc

        # ── Stage 1: Signal Layer (4 parallel sub-stages) ──
        slog.info("Pipeline started", **slog.elapsed())
        try:
            signal_data = self._run_signal_layer(
                video_path, self._video_id, self._job_store,
            )
        except Exception as e:
            _fail("signal_layer", e)

        if self.on_progress:
            dur = signal_data.get("total_duration", 0)
            scenes = len(signal_data.get("scene_boundaries", []))
            segs = len(signal_data.get("transcript_segments", []))
            self.on_progress("信号采集", f"完成 — 时长: {dur:.1f}s, 场景: {scenes}个, 语音段: {segs}个")
        slog.info("Stage 1 complete", stage="signal_layer",
                  duration=dur, scenes=scenes, segments=segs, **slog.elapsed())
        self._heartbeat()

        # ── Stage 2: Filter Layer (keyframe sampling) ──
        try:
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
        except Exception as e:
            _fail("filter_layer", e)
        self._heartbeat()

        # ── Stage 2b: Content-based sampling (second channel) ──
        try:
            content_keyframes = self._run_content_sampler(
                video_path, signal_data.get("fps", 30.0),
                signal_data.get("total_duration", 0.0),
            )
            if content_keyframes:
                existing_indices = {kf["frame_index"] for kf in keyframes}
                added = 0
                for ckf in content_keyframes:
                    if ckf["frame_index"] not in existing_indices:
                        keyframes.append(ckf)
                        existing_indices.add(ckf["frame_index"])
                        added += 1
                keyframes.sort(key=lambda kf: kf["frame_index"])
                if self.on_progress and added > 0:
                    self.on_progress("帧筛选", f"内容采样 +{added} 静态帧 → 共 {len(keyframes)} 个关键帧")
        except Exception as e:
            _fail("content_sampler", e)
        self._heartbeat()

        # ── Stage 2c: Video type classification (heuristic rule-engine) ──
        # Runs after keyframes available; may override user-specified default.
        user_specified_type = (video_type != "vlog")
        classifier_result = signal_data.get("video_type")
        try:
            if self._is_stage_done("video_type"):
                classifier_result = self._load_checkpointed("video_type")
                if classifier_result:
                    signal_data["video_type"] = classifier_result
                    if self.on_progress:
                        self.on_progress("类型识别", f"(恢复) {classifier_result.get('video_type', 'vlog')}")
            else:
                classifier_result = self._run_video_classifier(keyframes, signal_data=signal_data)
                if classifier_result:
                    signal_data["video_type"] = classifier_result
                    if self._job_store:
                        self._save_artifact("video_type", classifier_result)
                    if self.on_progress:
                        self.on_progress("类型识别",
                            f"{classifier_result.get('video_type', '?')} "
                            f"(置信度 {classifier_result.get('confidence', 0):.2f}, "
                            f"method={classifier_result.get('method', '?')})")
        except Exception:
            _log.warning("Video type classification failed — keeping default")

        # Override video_type if user didn't specify and classifier is confident
        if not user_specified_type and classifier_result:
            cls_type = classifier_result.get("video_type", "vlog")
            cls_conf = classifier_result.get("confidence", 0.0)
            if cls_conf > VIDEO_TYPE_CONFIDENCE_THRESHOLD and cls_type in VIDEO_TYPE_PRESETS:
                video_type = cls_type
                _log.info("Video type auto-classified as '%s' (confidence=%.2f)", video_type, cls_conf)

        # ── Stage 2.5: OCR on keyframes ──
        try:
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
            slog.info("Stage 2.5 complete", stage="ocr",
                      frames=len(ocr_results), **slog.elapsed())
        except Exception as e:
            _fail("ocr", e)
        self._heartbeat()

        # ── Stage 3: Understand Layer ──
        try:
            if self._is_stage_done("structure"):
                structure_segments = self._load_checkpointed("structure") or []
                if self.on_progress:
                    self.on_progress("规则引擎", f"(恢复) {len(structure_segments)} 个叙事段")
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
            slog.info("Stage 3 complete", stage="understand_layer",
                      segments=len(structure_segments), **slog.elapsed())
        except Exception as e:
            _fail("understand_layer", e)
        self._heartbeat()

        # ── Stage 4: Build Module Tree ──
        try:
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
            slog.info("Stage 4 complete", stage="module_tree",
                      modules=len(module_tree), **slog.elapsed())
            slog.info("Pipeline complete", **slog.elapsed())
        except Exception as e:
            _fail("module_tree", e)
        self._heartbeat()

        # ── Stage 5: Creative deconstruction (post-pipeline analysis) ──
        creative_pattern: Optional[Dict[str, Any]] = None
        try:
            Deconstructor = _lazy_import(
                "understanding.deconstruction.deconstructor", "Deconstructor",
            )
            decon = Deconstructor()
            creative_pattern = decon.deconstruct(
                signal_data=signal_data,
                structure_segments=structure_segments,
                keyframes=keyframes,
            )
            if self.on_progress:
                dims = [k for k, v in (creative_pattern or {}).items() if v]
                self.on_progress("创作特征", f"已完成 {len(dims)} 个维度分析")
        except Exception as exc:
            _log.debug("Creative deconstruction skipped: %s", exc)

        # ── Extract video metadata from source file ──
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                signal_data["video_width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                signal_data["video_height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                signal_data["video_fps"] = round(cap.get(cv2.CAP_PROP_FPS), 2)
                fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
                if fourcc:
                    codec_str = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4))
                    signal_data["video_codec"] = codec_str.strip()
                cap.release()
        except Exception:
            pass
        signal_data["video_file_size"] = os.path.getsize(video_path)

        # Mark completed in job store
        if self._job_store and video_id:
            self._job_store.set_status(video_id, "completed")

        self._last_result = assemble_result(
            signal_data=signal_data,
            keyframes=keyframes,
            structure_segments=structure_segments,
            module_tree=module_tree,
            creative_pattern=creative_pattern,
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
        need_vad = not self._is_stage_done("vad_detect")

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

            vad_art = job_store.load_artifact(video_id, "vad_detect")
            if vad_art:
                if "audio_data" not in results:
                    results["audio_data"] = {}
                results["audio_data"]["vad"] = vad_art
                results["audio_data"]["has_speech"] = vad_art.get("has_speech", True)

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
                    self._transcriber = AudioTranscriber(
                        on_progress=self.on_progress,
                    )
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

        def _vad_detect():
            try:
                if self._vad_detector is None:
                    VADDetector = _lazy_import(
                        "understanding.signal.vad_detect", "VADDetector"
                    )
                    self._vad_detector = VADDetector()
                return ("vad", self._vad_detector.detect(video_path))
            except Exception as e:
                _log.warning("VAD detection failed: %s", e)
                return ("vad", {"has_speech": True})

        # ── Stage 1: diff + scene + audio + vad (parallel) ──
        stage1 = []
        if need_diff:
            stage1.append(("diff", _frame_diff))
        if need_scene:
            stage1.append(("scene", _scene_detect))
        if need_audio:
            stage1.append(("audio", _audio_analysis))
        if need_vad:
            stage1.append(("vad", _vad_detect))

        if stage1:
            # ── Pre-import heavy deps on main thread to avoid Python
            #     import-lock deadlock when two threads hit _lazy_import
            #     simultaneously for the same module.
            _pre_import_signal_deps(self, stage1)

            # ── OpenCV-based tasks (frame_diff + scene_detect) must run
            #     sequentially — they both open the SAME video file via
            #     cv2.VideoCapture, and concurrent access can deadlock at
            #     the kernel / driver level.
            opencv_kinds = {"diff", "scene"}
            opencv_tasks = [(k, f) for k, f in stage1 if k in opencv_kinds]
            other_tasks  = [(k, f) for k, f in stage1 if k not in opencv_kinds]

            # ── Run OpenCV tasks sequentially with individual timeouts ──
            for kind, fn in opencv_tasks:
                timeout = FRAME_DIFF_SOFT_TIMEOUT if kind == "diff" else SCENE_DETECT_SOFT_TIMEOUT
                task_label = "frame_diff" if kind == "diff" else "scene_detect"
                pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    f = pool.submit(fn)
                    r = f.result(timeout=timeout)
                    if r is not None:
                        self._merge_signal_result(results, kind, r[1] if len(r) > 1 else None, r)
                except concurrent.futures.TimeoutError:
                    _log.error("%s timed out after %ds — skipping", task_label, timeout)
                except Exception:
                    _log.exception("%s crashed — skipping", task_label)
                finally:
                    # CRITICAL: shutdown(wait=False) prevents deadlock.
                    # If the task timed out, the thread is still running but
                    # we must NOT block the with-statement shutdown.
                    pool.shutdown(wait=False)

            # ── Run non-OpenCV tasks in parallel with per-task timeout ──
            if other_tasks:
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    future_map: dict = {}
                    for kind, fn in other_tasks:
                        future_map[pool.submit(fn)] = kind

                    for f in concurrent.futures.as_completed(future_map):
                        kind = future_map[f]
                        task_label = {"audio": "audio_analysis", "vad": "vad_detect"}.get(kind, kind)
                        try:
                            r = f.result(timeout=STAGE1_TASK_TIMEOUT)
                            if r is None:
                                continue
                            self._merge_signal_result(results, kind, r[1] if len(r) > 1 else None, r)
                        except concurrent.futures.TimeoutError:
                            _log.error("%s timed out after %ds — skipping", task_label, STAGE1_TASK_TIMEOUT)
                        except Exception:
                            _log.exception("%s crashed — skipping", task_label)

                # Heartbeat after each completed parallel sub-task
                self._heartbeat()

            # Persist stage-1 artifacts
            if job_store:
                for kind, _ in stage1:
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
                    elif kind == "audio" and results.get("audio_data"):
                        job_store.save_artifact(video_id, "audio_analysis",
                                                results["audio_data"])
                        job_store.update_checkpoint(video_id, "audio_analysis")
                    elif kind == "vad" and results.get("audio_data", {}).get("vad"):
                        job_store.save_artifact(video_id, "vad_detect",
                                                results["audio_data"]["vad"])
                        job_store.update_checkpoint(video_id, "vad_detect")

        # ── Stage 2: transcription (gated by VAD) ──
        vad_has_speech = results.get("audio_data", {}).get("has_speech", True)
        if need_transcribe and vad_has_speech:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                f = pool.submit(_transcribe)
                try:
                    r = f.result(timeout=STAGE2_TRANSCRIBE_TIMEOUT)
                    if r is not None:
                        self._merge_signal_result(results, "transcript", r[1] if len(r) > 1 else None, r)
                except concurrent.futures.TimeoutError:
                    _log.error(
                        "Whisper transcription timed out after %ds — skipping",
                        STAGE2_TRANSCRIBE_TIMEOUT,
                    )
                # Persist transcription
                if job_store and results.get("transcript_segments"):
                    job_store.save_artifact(video_id, "audio_transcribe", {
                        "transcript_segments": results["transcript_segments"],
                    })
                    job_store.update_checkpoint(video_id, "audio_transcribe")
        elif need_transcribe and not vad_has_speech:
            _log.info("VAD: no speech detected — skipping Whisper transcription")
        elif not need_transcribe:
            pass  # already checkpointed

        if not stage1 and not (need_transcribe and vad_has_speech):
            _log.info("Signal layer: all sub-tasks loaded from checkpoint")

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
        elif kind == "vad":
            vad_result = raw[1]
            if isinstance(vad_result, dict):
                if "audio_data" not in results:
                    results["audio_data"] = {}
                results["audio_data"]["vad"] = vad_result
                results["audio_data"]["has_speech"] = vad_result.get("has_speech", True)

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

    # ── Video Type Classification ──────────────────────────────────

    def _run_video_classifier(
        self,
        keyframes: List[dict],
        signal_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Run heuristic video-type classifier (pure rules, zero ML deps).

        Builds a signal summary from keyframe data and signal_data, then
        passes it to the heuristic rule-engine.
        """
        if not keyframes:
            return None

        try:
            if self._video_classifier is None:
                create_classifier = _lazy_import(
                    "understanding.signal.video_classifier", "create_classifier",
                )
                self._video_classifier = create_classifier()

            # ── Build signal summary from keyframe + signal_data ──
            n = len(keyframes)
            fc = sum(k.get("face_count", 0) for k in keyframes) / max(n, 1)
            flows = [k.get("optical_flow_magnitude", 0) for k in keyframes if isinstance(k, dict)]
            flows_val = sum(flows) / max(len(flows), 1)
            edges = [k.get("edge_density", 0) for k in keyframes if isinstance(k, dict)]
            edges_val = sum(edges) / max(len(edges), 1)

            # Enrich with audio / visual data from signal_data
            audio = signal_data.get("audio_data", {})
            bgm_type = audio.get("bgm_type", "") or audio.get("mood", "") or ""
            bpm = audio.get("bpm", 0) or 0

            # is_dominantly_neutral from visual_features if available
            vf_all = signal_data.get("visual_features", [])
            neutral_count = 0
            for vf in vf_all:
                if isinstance(vf, dict):
                    if vf.get("is_dominantly_neutral", False):
                        neutral_count += 1
            is_neutral = (neutral_count / max(len(vf_all), 1)) > 0.5 if vf_all else False

            sig: Dict[str, Any] = {
                "face_count_avg": round(fc, 3),
                "optical_flow_avg": round(flows_val, 2),
                "edge_density_avg": round(edges_val, 4),
                "bgm_type": bgm_type,
                "bpm": bpm,
                "is_dominantly_neutral": is_neutral,
            }

            return self._video_classifier.classify(signal_summary=sig)
        except Exception:
            logging.getLogger(__name__).debug(
                "Video classifier skipped", exc_info=True,
            )
            return None

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

            # ── OCR batches with per-batch checkpoint ──
            ocr_results: List[dict] = []
            n_batches = (len(frame_paths) + OCR_BATCH_SIZE - 1) // OCR_BATCH_SIZE
            with concurrent.futures.ThreadPoolExecutor(max_workers=OCR_MAX_WORKERS) as pool:
                batches = [
                    frame_paths[i:i + OCR_BATCH_SIZE]
                    for i in range(0, len(frame_paths), OCR_BATCH_SIZE)
                ]
                futures = {pool.submit(self._ocr.extract, b) for b in batches}
                completed_batches = 0
                for f in concurrent.futures.as_completed(futures):
                    try:
                        ocr_results.extend(f.result(timeout=STAGE3_OCR_TIMEOUT))
                    except concurrent.futures.TimeoutError:
                        _log.warning("OCR batch timed out after %ds — skipping", STAGE3_OCR_TIMEOUT)
                    except Exception:
                        pass
                    # ── Sub-stage checkpoint: save progress after each batch ──
                    completed_batches += 1
                    if self._job_store and self._video_id:
                        self._job_store.update_heartbeat(self._video_id)
                        self._job_store.save_artifact(
                            self._video_id,
                            "ocr_progress",
                            {
                                "completed_batches": completed_batches,
                                "total_batches": n_batches,
                                "result_count": len(ocr_results),
                            },
                        )

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
          1. Local YOLO + OpenCV
          2. OpenCV-only (zero-model)
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
            result = {"features": vfe.extract_batch(extracted_paths)}
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

    # ── Job recovery (process restart) ─────────────────────────────

    @staticmethod
    def recover_job(*args, **kwargs) -> Dict[str, Any]:
        """Resume a job after process restart.

        Delegated to :func:`understanding.task_recovery.recover_job`.
        """
        from understanding.task_recovery import recover_job as _rj
        return _rj(*args, **kwargs)

    @staticmethod
    def recover_stale(*args, **kwargs) -> List[Dict[str, Any]]:
        """List stale jobs from the analysis store.

        Delegated to :func:`understanding.task_recovery.recover_stale`.
        """
        from understanding.task_recovery import recover_stale as _rs
        return _rs(*args, **kwargs)

    # ── ETA estimation ─────────────────────────────────────────────

    @staticmethod
    def estimate_eta(*args, **kwargs) -> float:
        """Estimate analysis time in seconds from video parameters.

        Delegated to :func:`understanding.pipeline_eta.estimate_eta`.
        """
        from understanding.pipeline_eta import estimate_eta as _ee
        return _ee(*args, **kwargs)
