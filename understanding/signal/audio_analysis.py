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

    def __init__(self, sr: int = 16000, hop_length: int = 512) -> None:
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
            # librosa >= 0.10 returns tempo as 1-d array [bpm], not a scalar
            if hasattr(tempo, "item"):
                bpm = float(tempo.item())
            elif isinstance(tempo, (list, np.ndarray)) and len(tempo) > 0:
                bpm = float(tempo[0])
            else:
                bpm = float(tempo)
            # Convert beat_frames if it's a 0-d or 1-d array
            if hasattr(beat_frames, "ndim") and beat_frames.ndim == 0:
                beat_frames = np.array([beat_frames.item()])
            beat_frames = np.atleast_1d(np.asarray(beat_frames, dtype=float))
            beat_times = librosa.frames_to_time(
                beat_frames, sr=self.sr, hop_length=self.hop_length
            ).tolist()

            # Energy curve (RMS)
            rms = librosa.feature.rms(y=y, hop_length=self.hop_length)[0]
            rms_np = np.asarray(rms)
            energy_curve = rms_np.tolist()
            energy_times = librosa.frames_to_time(
                np.arange(len(rms_np)), sr=self.sr, hop_length=self.hop_length
            ).tolist()

            # Silence detection
            silence_boundaries = self._detect_silence(y, self.sr)

            # ── New multidimensional analysis ──

            # Volume (RMS in dB)
            rms_mean = float(np.mean(rms_np))
            volume_rms = float(20.0 * np.log10(rms_mean + 1e-10))
            volume_variance = float(np.std(rms_np))

            # Spectral features
            spectral_centroid, spectral_bandwidth = self._compute_spectral_features(y)

            # Frequency band energy ratio
            low_mid_high_ratio = self._compute_band_energy_ratio(y, self.sr)

            # Energy variation (mean adjacent-frame difference)
            energy_variation = float(np.mean(np.abs(np.diff(rms_np))))

            # BGM type classification
            bgm_type, bgm_confidence = self._classify_bgm(
                bpm=bpm,
                spectral_centroid=spectral_centroid,
                spectral_bandwidth=spectral_bandwidth,
                energy_curve=rms_np,
                low_ratio=low_mid_high_ratio[0],
                mid_ratio=low_mid_high_ratio[1],
                high_ratio=low_mid_high_ratio[2],
                beat_times=beat_times,
            )

            return {
                "_status": "success",
                "bpm": bpm,
                "beat_times": beat_times,
                "energy_curve": energy_curve,
                "energy_times": energy_times,
                "silence_boundaries": silence_boundaries,
                "duration": duration,
                "volume_rms": volume_rms,
                "volume_variance": volume_variance,
                "spectral_centroid": spectral_centroid,
                "spectral_bandwidth": spectral_bandwidth,
                "low_mid_high_ratio": low_mid_high_ratio,
                "energy_variation": energy_variation,
                "bgm_type": bgm_type,
                "bgm_confidence": bgm_confidence,
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
                    "-ar", "16000", "-ac", "1",
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
        rms = librosa.feature.rms(y=y, hop_length=self.hop_length)
        # rms shape is (n_channels, n_frames); take first channel and flatten
        rms_1d = np.asarray(rms[0]).flatten()
        max_rms = float(np.max(rms_1d))
        if max_rms == 0 or len(rms_1d) == 0:
            return []

        threshold = max_rms * threshold_ratio
        is_silent = rms_1d < threshold

        boundaries: List[Tuple[float, float]] = []
        in_silence = False
        silence_start = 0.0

        n_frames = len(is_silent)
        for i in range(n_frames):
            time_val = librosa.frames_to_time(i, sr=sr, hop_length=self.hop_length)

            if is_silent[i] and not in_silence:
                silence_start = time_val
                in_silence = True
            elif not is_silent[i] and in_silence:
                duration = time_val - silence_start
                if duration > min_gap:
                    boundaries.append((silence_start, time_val))
                in_silence = False

        if in_silence:
            end_time = librosa.frames_to_time(
                n_frames, sr=sr, hop_length=self.hop_length
            )
            if end_time - silence_start > min_gap:
                boundaries.append((silence_start, end_time))

        return boundaries

    # ── Spectral features ──

    def _compute_spectral_features(self, y: np.ndarray) -> Tuple[float, float]:
        """Compute mean spectral centroid (brightness) and spectral bandwidth.

        Returns:
            (spectral_centroid_mean, spectral_bandwidth_mean)
        """
        centroids = librosa.feature.spectral_centroid(
            y=y, sr=self.sr, hop_length=self.hop_length
        )[0]
        bandwidths = librosa.feature.spectral_bandwidth(
            y=y, sr=self.sr, hop_length=self.hop_length
        )[0]
        return float(np.mean(centroids)), float(np.mean(bandwidths))

    # ── Frequency band energy ratio ──

    def _compute_band_energy_ratio(self, y: np.ndarray, sr: int) -> List[float]:
        """Compute energy distribution across three frequency bands.

        Bands:
            low:    0 – 250 Hz
            mid:  250 – 2000 Hz
            high: 2000 Hz+

        Returns:
            [low_ratio, mid_ratio, high_ratio] summing to 1.0.
        """
        S = np.abs(librosa.stft(y, hop_length=self.hop_length))
        freqs = librosa.fft_frequencies(sr=sr)

        low_mask = freqs <= 250
        mid_mask = (freqs > 250) & (freqs <= 2000)
        high_mask = freqs > 2000

        low_energy = float(np.sum(S[low_mask, :]))
        mid_energy = float(np.sum(S[mid_mask, :]))
        high_energy = float(np.sum(S[high_mask, :]))
        total = low_energy + mid_energy + high_energy

        if total == 0.0:
            return [0.0, 0.0, 0.0]

        return [
            round(low_energy / total, 4),
            round(mid_energy / total, 4),
            round(high_energy / total, 4),
        ]

    # ── BGM type classification ──

    def _classify_bgm(
        self,
        bpm: float,
        spectral_centroid: float,
        spectral_bandwidth: float,
        energy_curve: np.ndarray,
        low_ratio: float,
        mid_ratio: float,
        high_ratio: float,
        beat_times: List[float],
    ) -> Tuple[str, float]:
        """Rule-based BGM type classification using weighted scoring.

        Six types:
            激昂/紧张 (Intense/Tense)
            轻松/愉快 (Relaxed/Cheerful)
            舒缓/宁静 (Calm/Serene)
            悲伤/沉郁 (Sad/Melancholic)
            电子/科技 (Electronic/Tech)
            节奏/打击 (Rhythmic/Percussive)

        Returns:
            (bgm_type, confidence) — confidence in [0, 1].
            Falls back to "无法判定" when best score < 0.5.
        """
        rms = np.asarray(energy_curve)
        if rms.size == 0 or np.max(rms) == 0.0:
            return "无法判定", 0.0

        cv = float(np.std(rms) / (np.mean(rms) + 1e-10))

        # Energy trend: linear regression slope (normalised)
        x = np.arange(len(rms), dtype=float)
        slope = float(np.polyfit(x, rms / (np.max(rms) + 1e-10), 1)[0])

        # Beat interval regularity (lower std/mean = more regular)
        beat_regularity = 0.0
        if len(beat_times) >= 4:
            intervals = np.diff(beat_times)
            iv_cv = float(np.std(intervals) / (np.mean(intervals) + 1e-10))
            beat_regularity = max(0.0, 1.0 - iv_cv)

        # Pulse regularity via RMS envelope autocorrelation
        pulse_regularity = 0.0
        if rms.size > 40:
            rms_norm = rms / (np.max(rms) + 1e-10)
            rms_norm = rms_norm - np.mean(rms_norm)
            autocorr = np.correlate(rms_norm, rms_norm, mode="same")
            autocorr = autocorr / (autocorr.max() + 1e-10)
            mid_idx = len(autocorr) // 2
            # Search secondary peak in region away from centre-lag
            search = autocorr[mid_idx + 20 : -20] if len(autocorr) > 40 else autocorr[mid_idx + 1 :]
            if len(search) > 0:
                pulse_regularity = float(np.max(search))

        # ── Dimension scoring helpers ──

        def _linear(val: float, lo: float, hi: float) -> float:
            """0→1 linear ramp from lo→hi, clamped."""
            if val <= lo:
                return 0.0
            if val >= hi:
                return 1.0
            return (val - lo) / (hi - lo)

        def _triangle(val: float, centre: float, half_width: float) -> float:
            """Triangular peak = 1 at centre, 0 at centre±half_width."""
            dist = abs(val - centre)
            if dist >= half_width:
                return 0.0
            return 1.0 - dist / half_width

        def _gaussian(val: float, centre: float, sigma: float) -> float:
            """Gaussian soft peak."""
            return float(np.exp(-0.5 * ((val - centre) / sigma) ** 2))

        scores: dict = {}

        # ── 激昂/紧张 (Intense/Tense) ──
        bpm_s = _linear(bpm, 120, 180)
        sc_s = _gaussian(spectral_centroid, 2500, 1000)  # peak at 2500 Hz
        cv_s = _linear(cv, 0.3, 0.6)
        low_s = _gaussian(low_ratio, 0.30, 0.12)  # "中" around 30%
        scores["激昂/紧张"] = bpm_s * 0.30 + sc_s * 0.20 + cv_s * 0.30 + low_s * 0.20

        # ── 轻松/愉快 (Relaxed/Cheerful) ──
        bpm_s = _triangle(bpm, 110, 30)  # 80–140 → peak at 110
        sc_s = _gaussian(spectral_centroid, 2200, 800)
        cv_s = 1.0 - _linear(cv, 0.15, 0.30)  # lower CV = better
        low_s = _gaussian(low_ratio, 0.30, 0.12)
        scores["轻松/愉快"] = bpm_s * 0.25 + sc_s * 0.20 + cv_s * 0.30 + low_s * 0.25

        # ── 舒缓/宁静 (Calm/Serene) ──
        bpm_s = 1.0 - _linear(bpm, 60, 100)  # lower BPM = better
        sc_s = 1.0 - _linear(spectral_centroid, 800, 2000)  # lower centroid = better
        cv_s = 1.0 - _linear(cv, 0.05, 0.25)
        low_s = _linear(low_ratio, 0.30, 0.60)
        scores["舒缓/宁静"] = bpm_s * 0.25 + sc_s * 0.25 + cv_s * 0.30 + low_s * 0.20

        # ── 悲伤/沉郁 (Sad/Melancholic) ──
        bpm_s = _triangle(bpm, 75, 20)  # 55–95, peak at 75
        sc_s = 1.0 - _linear(spectral_centroid, 800, 2000)
        trend_s = 1.0 - _linear(slope, -0.005, 0.005)  # negative slope preferred
        low_s = _linear(low_ratio, 0.35, 0.65)
        scores["悲伤/沉郁"] = bpm_s * 0.25 + sc_s * 0.20 + trend_s * 0.30 + low_s * 0.25

        # ── 电子/科技 (Electronic/Tech) ──
        bpm_s = _linear(bpm, 110, 170)
        sc_s = _linear(spectral_centroid, 3000, 5000)  # higher = more electronic
        pulse_s = _linear(pulse_regularity, 0.3, 0.8)
        low_s = 1.0 - _linear(low_ratio, 0.15, 0.35)  # lower low = better
        scores["电子/科技"] = bpm_s * 0.25 + sc_s * 0.25 + pulse_s * 0.30 + low_s * 0.20

        # ── 节奏/打击 (Rhythmic/Percussive) ──
        bpm_s = _linear(bpm, 100, 170)
        sc_s = _gaussian(spectral_centroid, 2000, 900)
        reg_s = beat_regularity
        low_s = _linear(low_ratio, 0.40, 0.70)  # very high low-freq
        scores["节奏/打击"] = bpm_s * 0.20 + sc_s * 0.15 + reg_s * 0.25 + low_s * 0.40

        # ── Select best ──
        best_type = "无法判定"
        best_score = 0.0
        for name, score in scores.items():
            if score > best_score:
                best_score = score
                best_type = name

        if best_score < 0.5:
            return "无法判定", round(best_score, 3)

        return best_type, round(best_score, 3)
