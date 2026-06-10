"""ETA estimation for video analysis pipeline.

Extracted from ``pipeline_orchestrator.py`` to reduce file size.
"""

from __future__ import annotations

from understanding.pipeline_config import (
    ETA_BASE_PER_SEC, ETA_WHISPER_PER_SEC,
    ETA_OCR_PER_FRAME, ETA_YOLO_PER_FRAME,
    ETA_API_PER_FRAME, ETA_AUDIO_PER_SEC,
)


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
