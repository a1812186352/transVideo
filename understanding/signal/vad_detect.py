"""Voice activity detection using silero-vad ONNX model (~1.9 MB).

Placed before Whisper transcription to gate whether speech is present.
On first call the model is downloaded from torch hub and cached under
``~/.cache/torch/hub/``.  Subsequent runs have zero network overhead.

Fallback:  if torch or silero-vad is unavailable the detector returns
``has_speech=True`` so the pipeline proceeds to Whisper normally.
"""

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict

import numpy as np

_log = logging.getLogger(__name__)


class VADDetector:
    """Lightweight silero-vad wrapper — model loaded once on first call.

    Extracts 16 kHz mono WAV via ffmpeg, then passes float32 audio
    through silero-vad's ``get_speech_timestamps()``.

    Attributes:
        SPEECH_RATIO_THRESHOLD: Fraction of total duration that must
            contain speech for ``has_speech=True`` (default 0.03).
    """

    SPEECH_RATIO_THRESHOLD = 0.03

    def __init__(self) -> None:
        self._model: Any = None
        self._utils: Any = None

    # ── Model loading ──────────────────────────────────────────────

    def _load_model(self) -> Any:
        """Lazy-load silero-vad from torch hub (cached on disk after first run)."""
        if self._model is not None:
            return self._model

        try:
            import torch  # noqa: F401
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
            )
            self._model = model
            self._utils = utils
            _log.info("silero-vad model loaded (torch hub cache)")
        except Exception as exc:
            _log.warning("silero-vad load failed (%s) — gate disabled", exc)
            self._model = False  # sentinel: load failed, don't retry
        return self._model

    # ── Audio extraction ───────────────────────────────────────────

    @staticmethod
    def _extract_audio(video_path: str) -> str:
        """Extract 16 kHz mono WAV via ffmpeg.

        Returns:
            Path to temporary WAV file, or empty string on failure.
        """
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return ""

        fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="transvideo_vad_")
        os.close(fd)

        try:
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-i", video_path,
                    "-vn", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1",
                    "-loglevel", "error", tmp,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                return ""
            return tmp
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return ""

    # ── Public API ─────────────────────────────────────────────────

    def detect(self, video_path: str) -> Dict[str, Any]:
        """Run VAD on video audio and return speech presence + timestamps.

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            Dict with:
                - has_speech (bool): True if speech_ratio >= 0.03.
                - speech_timestamps (List[dict]): [{start, end}, …].
                - speech_ratio (float): 0.0 – 1.0.
        """
        # ── 1. Load model ──
        model = self._load_model()

        # Sentinel: model load previously failed → fallback
        if model is False:
            return self._fallback()

        # ── 2. Extract audio ──
        tmp_path = self._extract_audio(video_path)
        if not tmp_path:
            return self._fallback()

        try:
            # ── 3. Run VAD ──
            get_speech_timestamps = getattr(self._utils, "get_speech_timestamps", None)
            read_audio = getattr(self._utils, "read_audio", None)

            if get_speech_timestamps is None or read_audio is None:
                _log.warning("silero-vad utils missing expected functions")
                return self._fallback()

            wav = read_audio(tmp_path, sampling_rate=16000)
            speech_ts = get_speech_timestamps(wav, model, sampling_rate=16000)

            # ── 4. Compute metrics ──
            total_duration = float(len(wav)) / 16000.0
            speech_total = sum(
                float(ts["end"]) - float(ts["start"])
                for ts in (speech_ts or [])
            )
            speech_ratio = round(speech_total / max(total_duration, 0.01), 4)
            has_speech = speech_ratio >= self.SPEECH_RATIO_THRESHOLD

            return {
                "has_speech": has_speech,
                "speech_timestamps": speech_ts if speech_ts else [],
                "speech_ratio": speech_ratio,
            }
        except Exception as exc:
            _log.warning("VAD inference failed (%s) — falling back", exc)
            return self._fallback()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _fallback() -> Dict[str, Any]:
        """Return safe fallback: has_speech=True (don't block Whisper)."""
        return {
            "has_speech": True,
            "speech_timestamps": [],
            "speech_ratio": 1.0,
        }
