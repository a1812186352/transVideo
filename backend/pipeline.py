"""Pipeline orchestrator: chains signal → filter → understand → script layers.

The Pipeline class is the central orchestrator that coordinates the
end-to-end video analysis workflow.

Heavy ML dependencies (OpenCV, Whisper, Librosa, PaddleOCR, SceneDetect)
are lazily imported only when the analysis pipeline is actually executed,
so the backend server can start without them installed.
"""

import os
import uuid
from typing import Any, Dict, List, Optional

# Lightweight imports (always available — no heavy ML deps)
from understanding.filter.adaptive_sampler import AdaptiveSampler
from understanding.understand.vision import VisionAnalyzer
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
    ) -> None:
        self.work_dir = work_dir or os.getcwd()
        self.vision_api_url = vision_api_url
        self.vision_api_key = vision_api_key

        # Lazy-initialized components
        self._frame_diff: Optional[Any] = None  # FrameDiffAnalyzer
        self._scene_detector: Optional[Any] = None  # SceneDetector
        self._transcriber: Optional[Any] = None  # AudioTranscriber
        self._audio_analyzer: Optional[Any] = None  # AudioAnalyzer
        self._ocr: Optional[Any] = None  # OCRExtractor
        self._frame_extractor: Optional[Any] = None  # FrameExtractor
        self._sampler: Optional[AdaptiveSampler] = None
        self._vision: Optional[VisionAnalyzer] = None
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
        signal_data = self._run_signal_layer(video_path)

        # --- Stage 2: Filter Layer ---
        keyframes = self._run_filter_layer(
            signal_data["diff_curve"],
            signal_data["scene_boundaries"],
            signal_data.get("fps", 30.0),
        )

        # --- Stage 2.5: OCR on Keyframes ---
        ocr_results = self._run_ocr_on_keyframes(video_path, keyframes)

        # --- Stage 3: Understand Layer ---
        structure_segments = self._run_understand_layer(
            keyframes, signal_data, ocr_results
        )

        # --- Stage 4: Build Module Tree ---
        module_tree = self._build_module_tree(
            structure_segments, signal_data, video_path
        )

        return {
            "signal_data": signal_data,
            "keyframes": keyframes,
            "structure": structure_segments,
            "module_tree": module_tree,
        }

    def _run_signal_layer(self, video_path: str) -> Dict[str, Any]:
        """Execute all signal layer analysis.

        Each component is independently wrapped so that a missing
        dependency (e.g. Whisper not installed) won't block the
        rest of the pipeline.

        Returns:
            Dict with: diff_curve, scene_boundaries, transcript_segments,
            audio_data, ocr_results, fps, total_duration.
        """
        import logging
        _log = logging.getLogger(__name__)

        diff_curve: List[float] = []
        timestamps: List[float] = []
        scene_boundaries: List[float] = []
        transcript_segments: List[dict] = []
        audio_data: dict = {}
        ocr_results: List[dict] = []
        fps = 30.0
        total_duration = 0.0

        # ── Frame diff (OpenCV) ──
        try:
            if self._frame_diff is None:
                FrameDiffAnalyzer = _lazy_import("understanding.signal.frame_diff", "FrameDiffAnalyzer")
                self._frame_diff = FrameDiffAnalyzer()
            diff_curve, timestamps = self._frame_diff.calc_diff_curve_with_timestamps(video_path)
        except Exception as e:
            _log.warning("Frame diff failed (skipping): %s", e)

        # ── Scene detection (PySceneDetect) ──
        try:
            if self._scene_detector is None:
                SceneDetector = _lazy_import("understanding.signal.scene_detect", "SceneDetector")
                self._scene_detector = SceneDetector()
            scene_boundaries = self._scene_detector.detect(video_path)
        except Exception as e:
            _log.warning("Scene detection failed (skipping): %s", e)

        # ── Audio transcription (Whisper) ──
        try:
            if self._transcriber is None:
                AudioTranscriber = _lazy_import("understanding.signal.audio_transcribe", "AudioTranscriber")
                self._transcriber = AudioTranscriber()
            transcript_segments = self._transcriber.transcribe(video_path)
        except Exception as e:
            _log.warning("Audio transcription failed (skipping): %s", e)

        # ── Audio analysis (Librosa) ──
        try:
            if self._audio_analyzer is None:
                AudioAnalyzer = _lazy_import("understanding.signal.audio_analysis", "AudioAnalyzer")
                self._audio_analyzer = AudioAnalyzer()
            audio_data = self._audio_analyzer.analyze(video_path)
        except Exception as e:
            _log.warning("Audio analysis failed (skipping): %s", e)

        # ── Estimate FPS / duration ──
        if timestamps:
            total_duration = timestamps[-1] if timestamps else 0.0
            if total_duration > 0 and diff_curve:
                fps = len(diff_curve) / total_duration

        return {
            "diff_curve": diff_curve,
            "diff_timestamps": timestamps,
            "scene_boundaries": scene_boundaries,
            "transcript_segments": transcript_segments,
            "audio_data": audio_data,
            "ocr_results": ocr_results,
            "fps": fps,
            "total_duration": total_duration,
        }

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
        then runs PaddleOCR on each image to detect on-screen text regions.

        Args:
            video_path: Absolute path to the input video file.
            keyframes: List of keyframe dicts from AdaptiveSampler, each
                containing ``frame_index``, ``timestamp``, etc.

        Returns:
            List of OCR result dicts, each containing ``frame_path`` and
            ``text_regions`` (see OCRExtractor.extract for schema).
        """
        try:
            # Initialize OCR engine (lazy-import: PaddleOCR)
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

            # Run OCR on extracted frame images
            ocr_results = self._ocr.extract(frame_paths)
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
    ) -> List[dict]:
        """Run vision analysis and structure inference.

        Note: Vision analysis requires actual frame images extracted
        from the video. In production, keyframe indices are used to
        extract frames via OpenCV before sending to LLM.

        Note: frame_descriptions requires:
          1. FrameExtractor to convert keyframe indices to PNG files
          2. VisionAnalyzer to send PNGs to LLM API
        Both are placeholders until the user configures their API keys
        in the frontend settings panel.

        Returns:
            List of narrative structure segments.
        """
        # Vision analysis (placeholder — needs frame extraction first)
        # TODO: Extract frames at keyframe indices, then call vision API
        frame_descriptions: List[dict] = []

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
        # Inject diff curve for energy-based segmentation
        if not audio_for_infer.get("energy_curve"):
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
        )

        return structure_segments

    def _build_module_tree(
        self,
        structure_segments: List[dict],
        signal_data: Dict[str, Any],
        video_path: str = "",
    ) -> List[Dict[str, Any]]:
        """Convert structure segments into a module tree.

        Each structure segment becomes one or more modules in the tree.

        Returns:
            List of Module dicts ready for script builder.
        """
        import math

        modules: List[Dict[str, Any]] = []

        for i, seg in enumerate(structure_segments):
            seg_type = seg.get("structure_type", "unclassified")
            seg_label = seg.get("label", f"segment_{i}")
            start_time = seg.get("start_time", 0.0)
            end_time = seg.get("end_time", start_time)
            duration = max(end_time - start_time, 0.0)

            if seg_type == "hook":
                modules.append({
                    "id": uuid.uuid4().hex[:12],
                    "start_time": start_time,
                    "duration": duration,
                    "track_index": 1,
                    "label": seg_label,
                    "type": "title",
                    "children": [],
                    "params": {
                        "text_content": seg_label,
                        "animation": "fade_in",
                    },
                })

            elif seg_type == "talking_head":
                modules.append({
                    "id": uuid.uuid4().hex[:12],
                    "start_time": start_time,
                    "duration": duration,
                    "track_index": 0,
                    "label": seg_label,
                    "type": "video_segment",
                    "children": [],
                    "source": {
                        "type": "video",
                        "path": video_path,
                    },
                })

            elif seg_type == "montage":
                # Split montage duration into sub-segments of ~3s each
                sub_duration = 3.0
                num_segments = max(1, round(duration / sub_duration))
                segment_duration = duration / num_segments

                for sub_idx in range(num_segments):
                    sub_start = start_time + sub_idx * segment_duration
                    modules.append({
                        "id": uuid.uuid4().hex[:12],
                        "start_time": sub_start,
                        "duration": segment_duration,
                        "track_index": 0,
                        "label": f"{seg_label}_{sub_idx}",
                        "type": "video_segment",
                        "children": [],
                    })

            elif seg_type == "conversion":
                modules.append({
                    "id": uuid.uuid4().hex[:12],
                    "start_time": start_time,
                    "duration": duration,
                    "track_index": 1,
                    "label": seg_label,
                    "type": "subtitle",
                    "children": [],
                    "params": {
                        "text_content": "CTA text",
                        "animation": "fade_in",
                    },
                })

            elif seg_type == "outro":
                modules.append({
                    "id": uuid.uuid4().hex[:12],
                    "start_time": start_time,
                    "duration": duration,
                    "track_index": 0,
                    "label": seg_label,
                    "type": "video_segment",
                    "children": [],
                })
                modules.append({
                    "id": uuid.uuid4().hex[:12],
                    "start_time": start_time,
                    "duration": duration,
                    "track_index": 3,
                    "label": f"{seg_label}_effect",
                    "type": "effect",
                    "children": [],
                    "params": {
                        "transition_type": "fade_out",
                    },
                })

            else:  # unclassified — pass-through
                modules.append({
                    "id": uuid.uuid4().hex[:12],
                    "start_time": start_time,
                    "duration": duration,
                    "track_index": 0,
                    "label": seg_label,
                    "type": "video_segment",
                    "children": [],
                })

        return modules
