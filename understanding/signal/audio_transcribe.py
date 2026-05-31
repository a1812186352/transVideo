"""Audio transcription using Whisper (small) for speech-to-text with timestamps.

Produces time-aligned text segments for downstream narrative structure inference.
"""

import whisper
from typing import List, Optional


class AudioTranscriber:
    """Transcribes speech from video audio track using Whisper.

    Attributes:
        model_name: Whisper model size (default 'small').
        device: Compute device ('cpu' or 'cuda').
    """

    def __init__(self, model_name: str = "small", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model: Optional[whisper.Whisper] = None

    def _load_model(self) -> whisper.Whisper:
        """Lazy-load the Whisper model."""
        if self._model is None:
            self._model = whisper.load_model(self.model_name, device=self.device)
        return self._model

    def transcribe(self, video_path: str) -> List[dict]:
        """Transcribe audio from video and return time-stamped segments.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            List of segment dicts, each containing:
                - start: float (seconds)
                - end: float (seconds)
                - text: str
        """
        model = self._load_model()
        result = model.transcribe(video_path, word_timestamps=False)

        segments: List[dict] = []
        for seg in result.get("segments", []):
            segments.append({
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": seg["text"].strip(),
            })

        return segments

    def get_full_text(self, video_path: str) -> str:
        """Transcribe and return concatenated full text without timestamps.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            Full transcript as a single string.
        """
        segments = self.transcribe(video_path)
        return "".join(seg["text"] for seg in segments)
