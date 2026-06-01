"""Audio transcription using faster-whisper (preferred) or openai-whisper.

faster-whisper uses CTranslate2 backend — ~4× faster on CPU than openai-whisper.
Falls back to openai-whisper if faster-whisper is not installed.
"""

from typing import List, Optional, Any

# Detect available backend at import time
_USE_FASTER = False
try:
    from faster_whisper import WhisperModel  # noqa: F401
    _USE_FASTER = True
except ImportError:
    import whisper  # noqa: F401


class AudioTranscriber:
    """Transcribes speech from video audio track using Whisper.

    Prefers faster-whisper (CTranslate2, ~4× CPU speedup) when available.
    Falls back to openai-whisper otherwise.

    Attributes:
        model_name: Whisper model size (default 'small').
        device: Compute device ('cpu' or 'cuda').
    """

    def __init__(self, model_name: str = "small", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model: Any = None

    def _load_model(self) -> Any:
        """Lazy-load the Whisper model (faster-whisper or openai-whisper)."""
        if self._model is not None:
            return self._model

        if _USE_FASTER:
            from faster_whisper import WhisperModel
            # Map device string: "cuda" → "cuda", else "cpu"
            compute = "int8"  # int8 quantization for CPU speed
            dev = "cuda" if self.device == "cuda" else "cpu"
            self._model = WhisperModel(self.model_name, device=dev, compute_type=compute)
        else:
            import whisper
            self._model = whisper.load_model(self.model_name, device=self.device)

        return self._model

    def transcribe(self, video_path: str) -> List[dict]:
        """Transcribe audio from video and return time-stamped segments.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            List of segment dicts: {start, end, text}
        """
        model = self._load_model()

        if _USE_FASTER:
            segments_out, _info = model.transcribe(video_path, word_timestamps=False)
            return [
                {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
                for s in segments_out
            ]
        else:
            result = model.transcribe(video_path, word_timestamps=False)
            return [
                {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip()}
                for s in result.get("segments", [])
            ]

    def get_full_text(self, video_path: str) -> str:
        """Transcribe and return concatenated full text without timestamps."""
        segments = self.transcribe(video_path)
        return "".join(seg["text"] for seg in segments)
