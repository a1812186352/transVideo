"""FFmpeg utility functions: detection, version, progress parsing, command building.

Provides shared helpers used across the processing layer for FFmpeg
availability checks, progress parsing from stderr output, and cross-platform
command list construction.
"""

import shutil
import subprocess
import re
from typing import Any, List, Optional, Dict


def check_ffmpeg_available() -> bool:
    """Check whether FFmpeg is available on the system PATH.

    Uses shutil.which to locate the ffmpeg executable. Works cross-platform
    (on Windows this finds ffmpeg.exe).

    Returns:
        True if ffmpeg is found on PATH, False otherwise.
    """
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_version() -> Optional[str]:
    """Return the FFmpeg version string, or None if not available.

    Runs ``ffmpeg -version`` and extracts the first line, which contains
    the version number and build info.

    Returns:
        Version string (e.g. "ffmpeg version 6.0-essentials_build..."),
        or None if FFmpeg is not available or the call fails.
    """
    if not check_ffmpeg_available():
        return None

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.splitlines()[0].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return None


def parse_ffmpeg_progress(stderr_line: str) -> Optional[Dict[str, Any]]:
    """Parse a single line of FFmpeg progress output from stderr.

    FFmpeg writes progress lines like::

        frame=  123 fps= 30 q=28.0 size=    1024kB time=00:00:05.00 bitrate=1677.7kbits/s speed=1.5x

    This function extracts ``time`` (in seconds), ``bitrate`` (in kbits/s),
    and ``speed`` (multiplier) into a dict.  Returns None if the line does
    not contain a ``time=`` field (indicating it is not a progress line).

    Args:
        stderr_line: One line from FFmpeg's stderr stream.

    Returns:
        A dict with keys ``time_sec``, ``bitrate_kbps``, ``speed``, and
        ``raw_time``, or None if the line cannot be parsed as a progress
        update.
    """
    # Only parse lines that contain "time=" — these are the progress lines
    if "time=" not in stderr_line:
        return None

    parsed: Dict[str, Any] = {}

    # Time: HH:MM:SS.ms
    time_match = re.search(r"time=(\d+):(\d+):(\d+)\.(\d+)", stderr_line)
    if time_match:
        h, m, s, cs = (
            int(time_match.group(1)),
            int(time_match.group(2)),
            int(time_match.group(3)),
            time_match.group(4),
        )
        total_seconds = h * 3600.0 + m * 60.0 + s + float("0." + cs)
        parsed["time_sec"] = total_seconds
        parsed["raw_time"] = f"{h:02d}:{m:02d}:{s:02d}.{cs}"

    # Bitrate (e.g. "1677.7kbits/s")
    bitrate_match = re.search(r"bitrate=\s*([\d.]+)kbits/s", stderr_line)
    if bitrate_match:
        parsed["bitrate_kbps"] = float(bitrate_match.group(1))

    # Speed (e.g. "1.5x")
    speed_match = re.search(r"speed=\s*([\d.]+)x", stderr_line)
    if speed_match:
        parsed["speed"] = float(speed_match.group(1))

    return parsed if parsed else None


def build_ffmpeg_cmd(*args: str) -> List[str]:
    """Build a cross-platform FFmpeg command list.

    Resolves the FFmpeg path via ``shutil.which`` and returns a command
    list suitable for passing to ``subprocess.run``.  On Windows the
    resolved path will typically end in ``ffmpeg.exe``.

    Args:
        *args: Arguments to pass to FFmpeg (e.g. ``-y``, ``-i``, ``input.mp4``).

    Returns:
        A list of strings starting with the resolved FFmpeg path followed
        by the supplied arguments.

    Raises:
        RuntimeError: If FFmpeg is not found on PATH.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError(
            "FFmpeg is not installed or not on PATH. "
            "Install FFmpeg from https://ffmpeg.org/download.html"
        )
    return [ffmpeg_path, *args]
