"""Video concatenation and format conversion using FFmpeg.

Concatenates multiple video files into a single output, handling
codec consistency, crossfade transitions, and format conversion.
"""

import subprocess
import os
import json
import shutil
from typing import List, Optional, Callable

from .ffmpeg_utils import parse_ffmpeg_progress

# Sentinel found in FFmpeg progress lines on stderr.
_PROGRESS_LINE_SENTINEL = "time="

# Format-to-codec mapping used by convert_format
_FORMAT_CODEC_MAP = {
    "mp4": "libx264",
    "mov": "libx264",
    "webm": "libvpx-vp9",
    "avi": "libx264",
}

# Audio codec for container formats
_FORMAT_AUDIO_CODEC = {
    "mp4": "aac",
    "mov": "aac",
    "webm": "libvorbis",
    "avi": "aac",
}


class VideoConcat:
    """Concatenates multiple video files using FFmpeg.

    Supports the concat demuxer for stream-copy (fast) and re-encode
    modes, single-file pass-through, and crossfade transitions between
    segments via the ``xfade`` filter.

    Attributes:
        ffmpeg_path: Path to ffmpeg executable (resolved at init time).
    """

    def __init__(self, ffmpeg_path: Optional[str] = None) -> None:
        """Initialise the concat engine, locating FFmpeg on PATH.

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

    def concat(
        self,
        file_paths: List[str],
        output_path: str,
        re_encode: bool = False,
        codec: str = "libx264",
        crf: int = 23,
        timeout: int = 600,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> str:
        """Concatenate multiple video files into one.

        Uses the FFmpeg concat demuxer.  All input files must have the same
        codec, resolution, and frame rate for stream-copy mode to work; use
        ``re_encode=True`` to normalise files with differing parameters.

        If only a single file is provided it is stream-copied or re-encoded
        directly — no concat overhead.

        Args:
            file_paths: List of absolute paths to video files, in order.
            output_path: Path for the concatenated output.
            re_encode: If True, re-encode all inputs to ensure
                consistency.  If False, uses stream-copy (faster but
                requires identical codecs).
            codec: Video codec when re-encoding.
            crf: Constant Rate Factor when re-encoding (0-51).
            timeout: Maximum time in seconds for the subprocess (default 600).
            progress_callback: Optional callable receiving progress dicts.

        Returns:
            Path to the output file.

        Raises:
            ValueError: If file_paths is empty.
            FileNotFoundError: If any input file does not exist.
            subprocess.TimeoutExpired: If the operation exceeds *timeout*.
            subprocess.CalledProcessError: If FFmpeg fails.
        """
        if not file_paths:
            raise ValueError("file_paths must not be empty")

        # Validate all inputs exist before any work
        for path in file_paths:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Input file not found: {path}")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Single-file shortcut — just copy or transcode
        if len(file_paths) == 1:
            return self._handle_single_file(
                file_paths[0], output_path, re_encode, codec, crf,
                timeout, progress_callback,
            )

        # Multi-file concat via file list
        return self._concat_via_filelist(
            file_paths, output_path, re_encode, codec, crf,
            timeout, progress_callback,
        )

    def concat_with_crossfade(
        self,
        file_paths: List[str],
        output_path: str,
        fade_duration: float = 0.5,
        xfade_transition: str = "fade",
        codec: str = "libx264",
        crf: int = 23,
        timeout: int = 600,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> str:
        """Concatenate videos with a crossfade transition between segments.

        Uses the FFmpeg ``xfade`` filter to blend the end of one segment
        into the beginning of the next.  This requires re-encoding and
        offsets segment start times to create overlap for the transition.

        Args:
            file_paths: List of absolute paths to video files, in order.
            output_path: Path for the output file.
            fade_duration: Duration of the crossfade in seconds (default 0.5).
            xfade_transition: ``xfade`` transition type (e.g. ``"fade"``,
                ``"wipeleft"``, ``"fadegrays"``).  See FFmpeg xfade docs
                for the full list.
            codec: Video codec for the re-encoded output.
            crf: Quality CRF value.
            timeout: Maximum time in seconds for the subprocess (default 600).
            progress_callback: Optional callable receiving progress dicts.

        Returns:
            Path to the output file.

        Raises:
            ValueError: If file_paths has fewer than 2 entries or
                fade_duration is <= 0.
            FileNotFoundError: If any input file does not exist.
            subprocess.TimeoutExpired: If the operation exceeds *timeout*.
            subprocess.CalledProcessError: If FFmpeg fails.
        """
        if len(file_paths) < 2:
            raise ValueError(
                "Crossfade requires at least 2 input files, "
                f"got {len(file_paths)}"
            )
        if fade_duration <= 0:
            raise ValueError(
                f"fade_duration must be > 0, got {fade_duration}"
            )

        for path in file_paths:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Input file not found: {path}")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        return self._concat_with_xfade(
            file_paths, output_path, fade_duration, xfade_transition,
            codec, crf, timeout, progress_callback,
        )

    def convert_format(
        self,
        input_path: str,
        output_path: str,
        output_format: str = "mp4",
        timeout: int = 600,
    ) -> str:
        """Convert a video to a different container format.

        Args:
            input_path: Path to source video.
            output_path: Path for output file.
            output_format: Target container format (``"mp4"``, ``"mov"``,
                ``"webm"``, ``"avi"``).
            timeout: Maximum time in seconds for the subprocess (default 600).

        Returns:
            Path to the converted file.

        Raises:
            FileNotFoundError: If input_path does not exist.
            ValueError: If output_format is unsupported.
            subprocess.TimeoutExpired: If the operation exceeds *timeout*.
            subprocess.CalledProcessError: If FFmpeg fails.
        """
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if output_format not in _FORMAT_CODEC_MAP:
            raise ValueError(
                f"Unsupported output format '{output_format}'. "
                f"Valid: {list(_FORMAT_CODEC_MAP)}"
            )

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        codec = _FORMAT_CODEC_MAP[output_format]
        audio_codec = _FORMAT_AUDIO_CODEC.get(output_format, "aac")

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-c:v", codec,
            "-crf", "23",
            "-preset", "medium",
            "-c:a", audio_codec,
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

    def _handle_single_file(
        self,
        file_path: str,
        output_path: str,
        re_encode: bool,
        codec: str,
        crf: int,
        timeout: int,
        progress_callback: Optional[Callable[[dict], None]],
    ) -> str:
        """Handle the single-input case: stream-copy or re-encode."""
        if re_encode:
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i", file_path,
                "-c:v", codec,
                "-crf", str(crf),
                "-preset", "medium",
                "-c:a", "aac",
                output_path,
            ]
        else:
            # Stream-copy single file (remux without re-encoding)
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i", file_path,
                "-c", "copy",
                output_path,
            ]

        result = self._run_ffmpeg(cmd, timeout, progress_callback)

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout, stderr=result.stderr,
            )

        return output_path

    def _concat_via_filelist(
        self,
        file_paths: List[str],
        output_path: str,
        re_encode: bool,
        codec: str,
        crf: int,
        timeout: int,
        progress_callback: Optional[Callable[[dict], None]],
    ) -> str:
        """Concatenate using the FFmpeg concat demuxer with a file list."""
        concat_list_path = output_path + ".concat.txt"

        try:
            self._write_concat_list(concat_list_path, file_paths)

            if re_encode:
                cmd = [
                    self.ffmpeg_path,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_list_path,
                    "-c:v", codec,
                    "-crf", str(crf),
                    "-preset", "medium",
                    "-c:a", "aac",
                    output_path,
                ]
            else:
                cmd = [
                    self.ffmpeg_path,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i",  concat_list_path,
                    "-c", "copy",
                    output_path,
                ]

            result = self._run_ffmpeg(cmd, timeout, progress_callback)

            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, cmd,
                    output=result.stdout, stderr=result.stderr,
                )

            return output_path

        finally:
            if os.path.exists(concat_list_path):
                os.remove(concat_list_path)

    def _concat_with_xfade(
        self,
        file_paths: List[str],
        output_path: str,
        fade_duration: float,
        xfade_transition: str,
        codec: str,
        crf: int,
        timeout: int,
        progress_callback: Optional[Callable[[dict], None]],
    ) -> str:
        """Concatenate using the xfade filter for crossfade transitions.

        Probes segment durations via ffprobe, then builds a complex
        filtergraph with correct xfade offsets.  Requires re-encoding.
        """
        # Probe durations of all input files
        durations = [self._probe_duration(path) for path in file_paths]

        # Build input arguments
        inputs: List[str] = []
        for path in file_paths:
            inputs.extend(["-i", path])

        # xfade chain: final video output label is always the last xfade step.
        final_video_label = f"xfade{len(file_paths) - 2}"

        filter_complex = self._build_xfade_filtergraph(
            file_paths, durations, fade_duration, xfade_transition,
        )

        cmd = [
            self.ffmpeg_path,
            "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{final_video_label}]",
            "-map", "[aout]",
            "-c:v", codec,
            "-crf", str(crf),
            "-preset", "medium",
            output_path,
        ]

        result = self._run_ffmpeg(cmd, timeout, progress_callback)

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout, stderr=result.stderr,
            )

        return output_path

    def _probe_duration(self, file_path: str) -> float:
        """Return the duration of a video file in seconds via ffprobe.

        Returns:
            Duration in seconds, or 0.0 if probing fails.
        """
        ffprobe_path = self.ffmpeg_path.replace("ffmpeg", "ffprobe") \
            if "ffmpeg" in os.path.basename(self.ffmpeg_path) \
            else shutil.which("ffprobe") or "ffprobe"

        try:
            result = subprocess.run(
                [
                    ffprobe_path,
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                return float(data.get("format", {}).get("duration", 0))
        except (subprocess.TimeoutExpired, json.JSONDecodeError,
                ValueError, FileNotFoundError, OSError):
            pass
        # Fallback: return a short default so xfade still attempts to work
        return 10.0

    @staticmethod
    def _build_xfade_filtergraph(
        file_paths: List[str],
        durations: List[float],
        fade_duration: float,
        xfade_transition: str,
    ) -> str:
        """Build the complete filter_complex string for video + audio crossfade.

        Returns:
            The full filter_complex string.
        """
        filter_parts: List[str] = []

        # --- Video: xfade chain ---
        filter_parts.append("[0:v]setpts=PTS-STARTPTS[v0]")
        cumulative_offset = durations[0] - fade_duration

        for i in range(1, len(durations)):
            prev_label = f"v{i - 1}" if i == 1 else f"xfade{i - 2}"
            out_label = f"xfade{i - 1}"

            filter_parts.append(
                f"[{i}:v]setpts=PTS-STARTPTS+{cumulative_offset}/TB[vin{i}]"
            )
            filter_parts.append(
                f"[{prev_label}][vin{i}]xfade=transition={xfade_transition}:"
                f"duration={fade_duration}:offset={cumulative_offset}[{out_label}]"
            )
            cumulative_offset += durations[i] - fade_duration

        # --- Audio: acrossfade chain (all first audio streams) ---
        audio_inputs = "".join(f"[{j}:a]" for j in range(len(file_paths)))
        audio_filter = (
            f"{audio_inputs}acrossfade=d={fade_duration}:c1=tri:c2=tri[aout]"
        )

        filter_parts.append(audio_filter)

        return ";".join(filter_parts)

    @staticmethod
    def _write_concat_list(path: str, file_paths: List[str]) -> None:
        """Write an FFmpeg concat demuxer file list."""
        with open(path, "w", encoding="utf-8") as f:
            for p in file_paths:
                safe = p.replace("\\", "/")
                f.write(f"file '{safe}'\n")

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
