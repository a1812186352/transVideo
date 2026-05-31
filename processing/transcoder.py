"""FFmpeg transcoder: video codec conversion and quality control.

Wraps FFmpeg CLI for transcoding operations: codec conversion,
resolution scaling, CRF-based quality control, with progress reporting
and robust error handling.
"""

import subprocess
import os
import json
import shutil
from typing import List, Optional, Callable

from .ffmpeg_utils import parse_ffmpeg_progress

# FFmpeg progress line pattern for callback streaming.
# We look for lines containing "time=" as the primary progress indicator.
_PROGRESS_LINE_SENTINEL = "time="

# Valid CRF range
_CRF_MIN, _CRF_MAX = 0, 51

# Valid presets for x264/x265
_VALID_PRESETS = frozenset({
    "ultrafast", "superfast", "veryfast", "faster",
    "fast", "medium", "slow", "slower", "veryslow",
    "placebo",  # x264/x265 include placebo
})

# Commonly-used video codecs that FFmpeg handles
_VALID_CODECS = frozenset({
    "libx264", "libx265", "libvpx", "libvpx-vp9",
    "libaom-av1", "libsvtav1", "h264_amf", "hevc_amf",
    "h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv",
})


class FFmpegTranscoder:
    """Transcodes video files using FFmpeg.

    Attributes:
        ffmpeg_path: Path to ffmpeg executable (resolved at init time
            via ``shutil.which`` if not provided).
    """

    def __init__(self, ffmpeg_path: Optional[str] = None) -> None:
        """Initialise the transcoder, locating FFmpeg on PATH.

        Args:
            ffmpeg_path: Explicit path to ffmpeg. If None, resolved
                automatically via ``shutil.which("ffmpeg")``.

        Raises:
            RuntimeError: If FFmpeg cannot be located.
        """
        if ffmpeg_path is None:
            ffmpeg_path = shutil.which("ffmpeg")
            if ffmpeg_path is None:
                raise RuntimeError(
                    "FFmpeg is not installed or not on PATH. "
                    "Install FFmpeg from https://ffmpeg.org/download.html"
                )
        self.ffmpeg_path = ffmpeg_path

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def check_ffmpeg() -> str:
        """Verify FFmpeg is available and return its path.

        Combines a PATH check with a quick version probe to confirm
        the executable is functional.

        Returns:
            Resolved path to the ffmpeg executable.

        Raises:
            RuntimeError: If FFmpeg is missing or cannot be executed.
        """
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            raise RuntimeError(
                "FFmpeg is not installed or not on PATH. "
                "Install FFmpeg from https://ffmpeg.org/download.html"
            )
        # Quick liveness check
        try:
            subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                timeout=15,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            raise RuntimeError(
                f"FFmpeg found at '{ffmpeg_path}' but failed to execute: {exc}"
            ) from exc
        return ffmpeg_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcode(
        self,
        input_path: str,
        output_path: str,
        crf: int = 23,
        preset: str = "medium",
        codec: str = "libx264",
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        extra_args: Optional[List[str]] = None,
        timeout: int = 600,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> str:
        """Transcode a video with specified parameters.

        Args:
            input_path: Path to source video file.
            output_path: Path for output video file.
            crf: Constant Rate Factor (0-51, lower = better quality).
                Default 23 provides good balance.
            preset: x264/x265 preset (ultrafast … veryslow).
            codec: Video codec (libx264, libx265, libvpx-vp9, etc.).
            width: Output width in pixels (optional, maintains aspect ratio).
            height: Output height in pixels (optional).
            fps: Output frame rate (optional).
            extra_args: Additional FFmpeg arguments.
            timeout: Maximum time in seconds to allow for the FFmpeg
                subprocess (default 600).  Raises ``TimeoutExpired`` on expiry.
            progress_callback: Optional callable receiving a dict with
                ``time_sec``, ``bitrate_kbps``, ``speed`` for each
                progress update parsed from FFmpeg stderr.

        Returns:
            Path to the output file.

        Raises:
            FileNotFoundError: If input_path does not exist.
            ValueError: If CRF, preset, or codec values are invalid.
            subprocess.TimeoutExpired: If the encode exceeds *timeout*.
            subprocess.CalledProcessError: If FFmpeg exits with non-zero status.
        """
        self._validate_transcode_params(crf, preset, codec)
        self._ensure_input_exists(input_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        cmd: List[str] = [
            self.ffmpeg_path,
            "-y",  # Overwrite output
            "-i", input_path,
            "-c:v", codec,
            "-crf", str(crf),
            "-preset", preset,
        ]

        self._append_scale(cmd, width, height)
        if fps:
            cmd.extend(["-r", str(fps)])
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(output_path)

        result = self._run_ffmpeg(cmd, timeout, progress_callback)

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout, stderr=result.stderr,
            )

        return output_path

    def get_metadata(self, video_path: str) -> dict:
        """Extract metadata from a video file using ffprobe.

        Args:
            video_path: Path to the video file.

        Returns:
            Dict with keys: duration, width, height, fps, codec, bitrate.
        """
        self._ensure_input_exists(video_path)

        ffprobe_path = self.ffmpeg_path.replace("ffmpeg", "ffprobe") \
            if "ffmpeg" in os.path.basename(self.ffmpeg_path) \
            else shutil.which("ffprobe") or "ffprobe"

        cmd = [
            ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path,
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout, stderr=result.stderr,
            )

        data = json.loads(result.stdout)

        # Extract video stream info
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        fmt = data.get("format", {})

        return {
            "duration": float(fmt.get("duration", 0)),
            "width": video_stream.get("width", 0) if video_stream else 0,
            "height": video_stream.get("height", 0) if video_stream else 0,
            "fps": self._parse_fps(video_stream) if video_stream else 0.0,
            "codec": video_stream.get("codec_name", "") if video_stream else "",
            "bitrate": int(fmt.get("bit_rate", 0)),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_transcode_params(
        self, crf: int, preset: str, codec: str
    ) -> None:
        """Validate transcode parameters before launching FFmpeg.

        Raises:
            ValueError: If any parameter is out of range or unrecognised.
        """
        if not (_CRF_MIN <= crf <= _CRF_MAX):
            raise ValueError(
                f"CRF must be between {_CRF_MIN} and {_CRF_MAX}, got {crf}"
            )
        if preset not in _VALID_PRESETS:
            raise ValueError(
                f"Invalid preset '{preset}'. Valid: {sorted(_VALID_PRESETS)}"
            )
        if codec not in _VALID_CODECS:
            raise ValueError(
                f"Unknown codec '{codec}'. Valid: {sorted(_VALID_CODECS)}"
            )

    @staticmethod
    def _ensure_input_exists(path: str) -> None:
        """Raise FileNotFoundError if *path* does not exist."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Input file not found: {path}")

    @staticmethod
    def _append_scale(
        cmd: List[str], width: Optional[int], height: Optional[int]
    ) -> None:
        """Append scale video filter to command list."""
        if width and height:
            cmd.extend(["-vf", f"scale={width}:{height}"])
        elif width:
            cmd.extend(["-vf", f"scale={width}:-1"])
        elif height:
            cmd.extend(["-vf", f"scale=-1:{height}"])

    def _run_ffmpeg(
        self,
        cmd: List[str],
        timeout: int,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> subprocess.CompletedProcess:
        """Run FFmpeg, optionally streaming progress updates.

        When *progress_callback* is provided, stderr is read line-by-line
        and each line that matches FFmpeg's progress format is parsed and
        passed to the callback.  This keeps memory usage low for long encodes
        while still capturing full stderr for error reporting.
        """
        if progress_callback is None:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        # Stream stderr line-by-line to give real-time progress,
        # accumulating both stdout and stderr for error reporting.
        stdout_chunks: List[str] = []
        stderr_chunks: List[str] = []

        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as proc:
            try:
                # Read stderr line-by-line (where FFmpeg writes progress).
                # Use a separate read loop so the callback fires in real time.
                assert proc.stderr is not None
                for line in proc.stderr:
                    stderr_chunks.append(line)
                    if _PROGRESS_LINE_SENTINEL in line:
                        parsed = parse_ffmpeg_progress(line)
                        if parsed:
                            progress_callback(parsed)

                # Consume stdout (usually empty or minimal for FFmpeg).
                if proc.stdout:
                    stdout_chunks.extend(proc.stdout.readlines())

                proc.wait(timeout=timeout)

            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise

        return subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
        )

    @staticmethod
    def _parse_fps(video_stream: dict) -> float:
        """Parse frame rate from ffprobe stream data."""
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        try:
            num, denom = r_frame_rate.split("/")
            return float(num) / float(denom) if int(denom) != 0 else 0.0
        except (ValueError, ZeroDivisionError):
            return 0.0
