"""Audio transcription using faster-whisper (preferred) or openai-whisper.

faster-whisper uses CTranslate2 backend — ~4× faster on CPU than openai-whisper.
Falls back to openai-whisper if faster-whisper is not installed.

First-run auto-download:  if the Whisper model is not in the local cache,
``_load_model()`` triggers an automatic download via ``model_manager.py``
with progress callbacks.  Network errors are caught and re-raised with a
clear message.
"""

from typing import List, Optional, Any, Callable

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
    Missing models are auto-downloaded on first load with progress reporting.

    Attributes:
        model_name: Whisper model size (default 'small').
        device: Compute device ('cpu' or 'cuda').
        on_progress: Optional ``(tag, msg)`` callback for download progress.
    """

    def __init__(
        self,
        model_name: str = "small",
        device: str = "cpu",
        on_progress: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.on_progress = on_progress
        self._model: Any = None

    # ── Backend name ──

    @staticmethod
    def backend() -> str:
        return "faster" if _USE_FASTER else "openai"

    # ── Model loading with auto-download ──

    def _load_model(self) -> Any:
        """Lazy-load the Whisper model, auto-downloading if necessary."""
        if self._model is not None:
            return self._model

        backend = self.backend()

        # Ensure model exists in cache — triggers download if missing
        from understanding.utils.model_manager import ensure_model
        ok, err = ensure_model(
            model_name=self.model_name,
            backend=backend,
            device=self.device,
            on_progress=self.on_progress,
        )
        if not ok:
            raise RuntimeError(
                f"Whisper {self.model_name} model unavailable and download failed: {err}"
            )

        if _USE_FASTER:
            from faster_whisper import WhisperModel
            compute = "int8"
            dev = "cuda" if self.device == "cuda" else "cpu"
            self._model = WhisperModel(self.model_name, device=dev, compute_type=compute)
        else:
            import whisper
            self._model = whisper.load_model(self.model_name, device=self.device)

        return self._model

    def transcribe(self, video_path: str) -> List[dict]:
        """Transcribe audio from video and return time-stamped segments.

        Logs Whisper version, backend, model size, and input file size
        before starting — helps diagnose external-dependency failures.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            List of segment dicts: {start, end, text}
        """
        model = self._load_model()

        # ── Log external dependency version + input dimensions ──
        import logging
        _log = logging.getLogger(__name__)
        try:
            wh_version = getattr(__import__('whisper', fromlist=['__version__']), '__version__', '?')
        except Exception:
            wh_version = '?'
        _log.info(
            "Whisper transcription start — backend=%s model=%s whisper_version=%s "
            "device=%s file_path=%.100s",
            self.backend(), self.model_name, wh_version,
            self.device, video_path,
        )

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
