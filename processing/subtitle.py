"""Subtitle burner: burns subtitles into video using FFmpeg.

Supports SRT, ASS/SSA, and VTT subtitle formats with customizable styling,
as well as static text overlays via the drawtext filter.
"""

import subprocess
import os
import shutil
from typing import Callable, Optional, Dict, Any

from .ffmpeg_utils import parse_ffmpeg_progress

# Sentinel found in FFmpeg progress lines on stderr.
_PROGRESS_LINE_SENTINEL = "time="


class SubtitleBurner:
    """Burns subtitles into a video file using the FFmpeg subtitles filter.

    Supports SRT, ASS/SSA, and VTT subtitle files.  Allows caller control
    over styling via ``force_style`` parameters and provides a
    ``burn_subtitles()`` convenience alias for ``burn()``.

    Attributes:
        ffmpeg_path: Path to ffmpeg executable (resolved at init time).
    """

    def __init__(self, ffmpeg_path: Optional[str] = None) -> None:
        """Initialise the subtitle burner, locating FFmpeg on PATH.

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
    # Public API
    # ------------------------------------------------------------------

    def burn(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        subtitle_format: str = "auto",
        style: Optional[dict] = None,
        timeout: int = 600,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> str:
        """Burn subtitles into the video.

        Args:
            video_path: Path to the source video file.
            subtitle_path: Path to the subtitle file (SRT/ASS/VTT).
            output_path: Path for output video with burned subtitles.
            subtitle_format: Subtitle format hint. One of ``"auto"`` (detect
                from file extension), ``"srt"``, ``"ass"``, ``"ssa"``, ``"vtt"``.
                ASS/SSA subtitles can carry embedded styles; SRT subtitles
                accept styling via the *style* parameter.
            style: Optional styling dict with keys:
                - font_name: Font family name
                - font_size: Font size in pixels
                - primary_color: Text color in ASS format (&HBBGGRR)
                - outline_color: Outline color
                - alignment: Subtitle alignment (1-9, ASS standard)
                - margin_v: Vertical margin
            timeout: Maximum time in seconds for the FFmpeg subprocess
                (default 600).
            progress_callback: Optional callable receiving a dict with
                ``time_sec``, ``bitrate_kbps``, ``speed`` for each
                progress update parsed from FFmpeg stderr.

        Returns:
            Path to the output file.

        Raises:
            FileNotFoundError: If video_path or subtitle_path does not exist.
            subprocess.TimeoutExpired: If the burn exceeds *timeout*.
            subprocess.CalledProcessError: If FFmpeg exits non-zero.
        """
        return self.burn_subtitles(
            video_path=video_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            subtitle_format=subtitle_format,
            style=style,
            timeout=timeout,
            progress_callback=progress_callback,
        )

    def burn_subtitles(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        subtitle_format: str = "auto",
        style: Optional[dict] = None,
        timeout: int = 600,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> str:
        """Burn subtitles into the video (primary entry-point).

        This is the canonical method for hardcoding subtitles.  See
        :meth:`burn` for full documentation (``burn`` delegates here).

        Args:
            video_path: Path to the source video file.
            subtitle_path: Path to the subtitle file.
            output_path: Path for output video.
            subtitle_format: ``"auto"``, ``"srt"``, ``"ass"``, ``"ssa"``, ``"vtt"``.
            style: Optional styling dict (see :meth:`burn`).
            timeout: Subprocess timeout (seconds).
            progress_callback: Optional progress callback.

        Returns:
            Path to the output file.
        """
        self._validate_inputs(video_path, subtitle_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        subtitle_path_escaped = self._escape_path_for_ffmpeg(subtitle_path)
        force_style = self._build_force_style(style)

        vf_filter = self._build_subtitles_filter(
            subtitle_path_escaped, force_style
        )

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", video_path,
            "-vf", vf_filter,
            "-c:a", "copy",
            output_path,
        ]

        result = self._run_ffmpeg(cmd, timeout, progress_callback)

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout, stderr=result.stderr,
            )

        return output_path

    def burn_text_overlay(
        self,
        video_path: str,
        text: str,
        output_path: str,
        start_time: float = 0.0,
        duration: Optional[float] = None,
        font_size: int = 24,
        font_color: str = "white",
        x: str = "(w-text_w)/2",
        y: str = "(h-text_h)/2",
        font_file: Optional[str] = None,
        timeout: int = 600,
    ) -> str:
        """Overlay static text on a video segment.

        Args:
            video_path: Path to the source video file.
            text: Text string to overlay.
            output_path: Path for output video.
            start_time: Time in seconds when text appears.
            duration: How long text stays. None means until end of video.
            font_size: Font size.
            font_color: Text color (CSS color name or hex).
            x: X position expression (FFmpeg drawtext syntax).
            y: Y position expression (FFmpeg drawtext syntax).
            font_file: Path to .ttf font file.
            timeout: Maximum time in seconds for the subprocess (default 600).

        Returns:
            Path to the output file.

        Raises:
            FileNotFoundError: If video_path does not exist.
            subprocess.TimeoutExpired: If the operation exceeds *timeout*.
            subprocess.CalledProcessError: If FFmpeg fails.
        """
        self._validate_input(video_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        drawtext = (
            f"fontsize={font_size}:fontcolor={font_color}"
            f":x={x}:y={y}:text='{text}'"
        )

        if font_file:
            if not os.path.isfile(font_file):
                raise FileNotFoundError(f"Font file not found: {font_file}")
            drawtext += f":fontfile='{font_file}'"

        if start_time > 0:
            if duration is not None:
                drawtext += (
                    f":enable='between(t,{start_time},{start_time + duration})'"
                )
            else:
                drawtext += f":enable='gte(t,{start_time})'"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", video_path,
            "-vf", f"drawtext={drawtext}",
            "-c:a", "copy",
            output_path,
        ]

        result = self._run_ffmpeg(cmd, timeout)

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout, stderr=result.stderr,
            )

        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _escape_path_for_ffmpeg(path: str) -> str:
        """Escape a file-system path for FFmpeg filter arguments.

        Converts Windows backslashes and escapes colons so the path can
        be embedded safely inside a filter string.
        """
        return path.replace("\\", "/").replace(":", "\\\\:")

    @staticmethod
    def _build_force_style(style: Optional[dict]) -> str:
        """Build the ``force_style`` argument string from a style dict.

        Returns:
            A comma-separated string of ``Key=Value`` pairs, or an empty
            string if *style* is None or empty.
        """
        if not style:
            return ""

        # Map of dict keys to ASS force_style field names.
        _KEY_MAP: Dict[str, str] = {
            "font_name": "FontName",
            "font_size": "FontSize",
            "primary_color": "PrimaryColour",
            "outline_color": "OutlineColour",
            "alignment": "Alignment",
            "margin_v": "MarginV",
        }

        parts = []
        for key, ass_key in _KEY_MAP.items():
            value = style.get(key)
            if value is not None:
                parts.append(f"{ass_key}={value}")

        return ",".join(parts)

    @staticmethod
    def _build_subtitles_filter(
        subtitle_path_escaped: str, force_style: str
    ) -> str:
        """Construct the ``subtitles=...`` FFmpeg filter string."""
        if force_style:
            return (
                f"subtitles='{subtitle_path_escaped}'"
                f":force_style='{force_style}'"
            )
        return f"subtitles='{subtitle_path_escaped}'"

    def _validate_inputs(self, video_path: str, subtitle_path: str) -> None:
        """Validate that both input files exist."""
        self._validate_input(video_path)
        if not os.path.isfile(subtitle_path):
            raise FileNotFoundError(
                f"Subtitle file not found: {subtitle_path}"
            )

    @staticmethod
    def _validate_input(path: str) -> None:
        """Raise FileNotFoundError if a single input file is missing."""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Input file not found: {path}")

    def _run_ffmpeg(
        self,
        cmd: list,
        timeout: int,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> subprocess.CompletedProcess:
        """Run FFmpeg, optionally streaming progress updates."""
        if progress_callback is None:
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )

        stdout_chunks: list = []
        stderr_chunks: list = []

        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as proc:
            try:
                assert proc.stderr is not None
                for line in proc.stderr:
                    stderr_chunks.append(line)
                    if _PROGRESS_LINE_SENTINEL in line:
                        parsed = parse_ffmpeg_progress(line)
                        if parsed:
                            progress_callback(parsed)

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
