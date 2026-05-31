"""Processing layer: FFmpeg transcode, subtitle, concat, and utilities.

Exports:
    - FFmpegTranscoder — video codec conversion and quality control.
    - SubtitleBurner — burn subtitles into video (SRT/ASS/VTT).
    - VideoConcat — concatenate videos with optional crossfade.
    - check_ffmpeg_available — verify FFmpeg is on PATH.
    - get_ffmpeg_version — retrieve FFmpeg version string.
    - parse_ffmpeg_progress — parse progress lines from FFmpeg stderr.
    - build_ffmpeg_cmd — build a cross-platform FFmpeg command list.
"""

from .transcoder import FFmpegTranscoder
from .subtitle import SubtitleBurner
from .concat import VideoConcat
from .ffmpeg_utils import (
    check_ffmpeg_available,
    get_ffmpeg_version,
    parse_ffmpeg_progress,
    build_ffmpeg_cmd,
)

__all__ = [
    "FFmpegTranscoder",
    "SubtitleBurner",
    "VideoConcat",
    "check_ffmpeg_available",
    "get_ffmpeg_version",
    "parse_ffmpeg_progress",
    "build_ffmpeg_cmd",
]
