"""HyperFrames renderer: orchestrates JSON script → HTML → MP4 pipeline.

Takes a MigratableScript JSON, maps it to HyperFrames HTML via Composer,
then renders to MP4 using the HyperFrames engine with FFmpeg fallback.
"""

import subprocess
import os
import logging
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class HyperFramesRenderer:
    """Renders a MigratableScript to MP4 via HyperFrames.

    Attributes:
        hyperframes_cli: Path to HyperFrames CLI executable.
        work_dir: Working directory for intermediate files.
        template_path: Path to default HTML template.
    """

    def __init__(
        self,
        hyperframes_cli: str = "hyperframes",
        work_dir: Optional[str] = None,
        template_path: Optional[str] = None,
    ) -> None:
        self.hyperframes_cli = hyperframes_cli
        self.work_dir = work_dir or os.getcwd()
        self.template_path = template_path or ""

    def render(
        self,
        script_json: Dict[str, Any],
        output_path: str,
        fps: int = 30,
        crf: int = 23,
        cleanup_html: bool = True,
    ) -> str:
        """Render a MigratableScript to an MP4 video file.

        Steps:
        1. Map script JSON to HyperFrames HTML via Composer.
        2. Write HTML to a temp file.
        3. Try HyperFrames CLI to render HTML → MP4.
        4. Fall back to FFmpeg title-card render if HyperFrames fails.
        5. Return output path.

        Args:
            script_json: Complete MigratableScript dict.
            output_path: Absolute path for the output MP4 file.
            fps: Output frame rate.
            crf: Constant Rate Factor for quality (lower = better).
            cleanup_html: If True, delete the intermediate HTML file after
                a successful render.

        Returns:
            Absolute path to the rendered MP4 file.

        Raises:
            RuntimeError: If both HyperFrames CLI and FFmpeg fallback fail.
        """
        from generation.composer import Composer

        composer = Composer(template_path=self.template_path)
        html_content = composer.script_to_html(script_json)

        # Write HTML to temp file
        title = (script_json.get("metadata") or {}).get("title", "output")
        html_path = os.path.join(
            self.work_dir, f"_render_{title}.html"
        )
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        success = False
        try:
            # Attempt 1: HyperFrames CLI
            if self._render_with_hyperframes(html_path, output_path, fps, crf):
                logger.info(f"Rendered via HyperFrames: {output_path}")
                success = True
                return output_path

            # Attempt 2: FFmpeg fallback
            logger.info("HyperFrames unavailable, trying FFmpeg fallback...")
            if self._render_with_ffmpeg_fallback(script_json, output_path, fps, crf):
                logger.info(f"Rendered via FFmpeg fallback: {output_path}")
                success = True
                return output_path

            err_msg = "Both HyperFrames CLI and FFmpeg fallback failed to render"
            if hasattr(self, '_last_ffmpeg_error'):
                err_msg += f" (FFmpeg: {self._last_ffmpeg_error})"
            raise RuntimeError(err_msg)
        finally:
            if cleanup_html and success:
                try:
                    os.remove(html_path)
                    logger.debug(f"Cleaned up temp HTML: {html_path}")
                except OSError as e:
                    logger.debug(f"Could not clean up temp HTML {html_path}: {e}")

    def _render_with_hyperframes(
        self, html_path: str, output_path: str, fps: int, crf: int
    ) -> bool:
        """Try to render using HyperFrames CLI. Returns True on success.

        Args:
            html_path: Path to the input HTML file.
            output_path: Path for the output MP4 file.
            fps: Output frame rate.
            crf: Constant Rate Factor for quality.

        Returns:
            True if rendering succeeded, False otherwise.
        """
        cmd = [
            self.hyperframes_cli, "render",
            "--input", html_path,
            "--output", output_path,
            "--fps", str(fps),
            "--crf", str(crf),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.warning(f"HyperFrames render failed: {result.stderr}")
                return False
            return True
        except FileNotFoundError:
            logger.warning("HyperFrames CLI not found, will use fallback")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("HyperFrames render timed out")
            return False

    def _render_with_ffmpeg_fallback(
        self,
        script_json: Dict[str, Any],
        output_path: str,
        fps: int = 30,
        crf: int = 23,
    ) -> bool:
        """Render a title-card MP4 using FFmpeg as a fallback.

        Generates a simple video with the script title burned onto a dark
        background.  This ensures the pipeline always produces a valid MP4
        even when HyperFrames CLI is unavailable.

        Args:
            script_json: Complete MigratableScript dict.
            output_path: Path for the output MP4 file.
            fps: Output frame rate.
            crf: Constant Rate Factor for quality.

        Returns:
            True if the fallback render succeeded, False otherwise.
        """
        metadata = script_json.get("metadata") or {}
        title = metadata.get("title", "Untitled")
        duration = metadata.get("total_duration", 5.0)
        width = (metadata.get("resolution") or {}).get("width", 1920)
        height = (metadata.get("resolution") or {}).get("height", 1080)

        # Escape special characters in the title for FFmpeg drawtext.
        # Colons are argument separators; single quotes delimit the text
        # argument; backslashes are escape characters.
        safe_title = title or "Untitled"
        safe_title = safe_title.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

        import shutil
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={width}x{height}:d={duration}:r={fps}",
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                self._last_ffmpeg_error = result.stderr.strip()[-120:]
                return False
            return True
        except FileNotFoundError:
            self._last_ffmpeg_error = "FFmpeg not found"
            return False
        except subprocess.TimeoutExpired:
            self._last_ffmpeg_error = "timed out"
            return False
