"""Audio analysis using Librosa: BPM detection, beat timestamps, energy curve.

Provides rhythmic and energy signals for narrative structure inference.
"""

import shutil
import subprocess
import tempfile
import os
import librosa
import numpy as np
from typing import List, Tuple


class AudioAnalyzer:
    """Analyzes audio track for BPM, beat positions and energy envelope.

    Attributes:
        sr: Target sample rate for analysis (default 22050).
        hop_length: Hop length for onset detection (default 512).
    """

    def __init__(self, sr: int = 22050, hop_length: int = 512) -> None:
        self.sr = sr
        self.hop_length = hop_length

    def analyze(self, video_path: str) -> dict:
        """Extract BPM, beat timestamps and RMS energy curve from audio.

        Handles both audio files and video files (extracts audio via ffmpeg).

        Args:
            video_path: Absolute path to the input video file.

        Returns:
            Dict containing:
                - bpm: Estimated tempo (float)
                - beat_times: List of beat timestamps in seconds
                - energy_curve: RMS energy values per frame
                - energy_times: Time axis for energy_curve
                - silence_boundaries: List of (start, end) tuples for gaps > 3s
                - duration: Total audio duration in seconds
        """
        audio_path = video_path

        # If it's a video file (not .wav/.mp3/.flac), extract audio via ffmpeg
        ext = os.path.splitext(video_path)[1].lower()
        if ext in (".mov", ".mp4", ".avi", ".mkv", ".webm"):
            audio_path = self._extract_audio(video_path)
            if not audio_path:
                raise RuntimeError(f"Cannot extract audio from {video_path}")

        try:
            y, _sr = librosa.load(audio_path, sr=self.sr)

            duration = len(y) / self.sr

            # BPM and beats
            tempo, beat_frames = librosa.beat.beat_track(
                y=y, sr=self.sr, hop_length=self.hop_length
            )
            bpm = float(tempo)
            beat_times = librosa.frames_to_time(
                beat_frames, sr=self.sr, hop_length=self.hop_length
            ).tolist()

            # Energy curve (RMS)
            rms = librosa.feature.rms(y=y, hop_length=self.hop_length)[0]
            energy_curve = rms.tolist()
            energy_times = librosa.frames_to_time(
                np.arange(len(rms)), sr=self.sr, hop_length=self.hop_length
            ).tolist()

            # Silence detection (>3s gaps with RMS below 5% of max)
            silence_boundaries = self._detect_silence(y, self.sr)

            return {
                "bpm": bpm,
                "beat_times": beat_times,
                "energy_curve": energy_curve,
                "energy_times": energy_times,
                "silence_boundaries": silence_boundaries,
                "duration": duration,
            }
        finally:
            # Clean up temp audio file
            if audio_path != video_path and os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                except OSError:
                    pass

    @staticmethod
    def _extract_audio(video_path: str) -> str:
        """Extract audio track from video to a temporary WAV file via ffmpeg.

        Returns:
            Path to the temporary WAV file, or empty string on failure.
        """
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return ""
        fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="transvideo_audio_")
        os.close(fd)
        try:
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-i", video_path,
                    "-vn", "-acodec", "pcm_s16le",
                    "-ar", "22050", "-ac", "1",
                    "-loglevel", "error",
                    tmp,
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
        except (FileNotFoundError, subprocess.TimeoutExpired):
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return ""

    def _detect_silence(
        self, y: np.ndarray, sr: int, threshold_ratio: float = 0.05, min_gap: float = 3.0
    ) -> List[Tuple[float, float]]:
        """Detect silent segments longer than min_gap seconds.

        Args:
            y: Audio signal array.
            sr: Sample rate.
            threshold_ratio: Ratio of max RMS below which is considered silence.
            min_gap: Minimum silence duration in seconds.

        Returns:
            List of (start_time, end_time) tuples for silent segments.
        """
        rms = librosa.feature.rms(y=y, hop_length=self.hop_length)[0]
        max_rms = float(np.max(rms))
        if max_rms == 0:
            return []

        threshold = max_rms * threshold_ratio
        is_silent = rms < threshold

        boundaries: List[Tuple[float, float]] = []
        in_silence = False
        silence_start = 0.0

        for i, silent in enumerate(is_silent):
            time_val = librosa.frames_to_time(i, sr=sr, hop_length=self.hop_length)

            if silent and not in_silence:
                silence_start = time_val
                in_silence = True
            elif not silent and in_silence:
                duration = time_val - silence_start
                if duration > min_gap:
                    boundaries.append((silence_start, time_val))
                in_silence = False

        if in_silence:
            end_time = librosa.frames_to_time(
                len(is_silent), sr=sr, hop_length=self.hop_length
            )
            if end_time - silence_start > min_gap:
                boundaries.append((silence_start, end_time))

        return boundaries
