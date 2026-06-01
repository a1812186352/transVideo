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
        """Render a modular MP4 using FFmpeg as a fallback.

        Processes the script JSON's tracks/modules structure to produce
        real video content:
          - ``video_segment`` modules are trimmed from source video files
          - ``title`` / ``subtitle`` modules become text overlays via drawtext
          - ``transition`` modules between segments use xfade crossfade
        Together, this covers the core render pipeline when HyperFrames
        CLI is unavailable, closing the project's main rendering gap.

        Args:
            script_json: Complete MigratableScript dict.
            output_path: Path for the output MP4 file.
            fps: Output frame rate.
            crf: Constant Rate Factor for quality.

        Returns:
            True if the fallback render succeeded, False otherwise.
        """
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            self._last_ffmpeg_error = "FFmpeg not found on PATH"
            return False

        metadata = script_json.get("metadata") or {}
        modules: list = script_json.get("modules") or []
        width = (metadata.get("resolution") or {}).get("width", 1920)
        height = (metadata.get("resolution") or {}).get("height", 1080)
        total_duration = metadata.get("total_duration", 5.0)
        fps_val = int(metadata.get("fps", fps) or fps)

        # ── No modules → simple title card ──
        if not modules:
            logger.warning("No modules in script; rendering simple title card")
            return self._render_simple_title_card(
                metadata, output_path, ffmpeg, fps_val, crf, width, height,
            )

        # ── Work directory for intermediate clips ──
        import uuid as _uuid
        work_tag = _uuid.uuid4().hex[:8]
        work_dir = os.path.join(self.work_dir, f"_ffmpeg_fallback_{work_tag}")
        os.makedirs(work_dir, exist_ok=True)

        try:
            # Step 1 — Build sequential clip list from the primary video track
            clip_list = self._build_base_clips(
                modules, ffmpeg, work_dir, fps_val, crf, width, height,
            )

            if not clip_list:
                logger.warning("No renderable video clips from modules")
                return self._render_simple_title_card(
                    metadata, output_path, ffmpeg, fps_val, crf,
                    width, height,
                )

            # Step 2 — Concatenate clips (with transitions where detected)
            intermediate_path = os.path.join(work_dir, "_concat_base.mp4")
            self._concat_clips(
                ffmpeg, clip_list, modules, intermediate_path, crf,
            )

            # Step 3 — Overlay title / subtitle text modules
            text_modules = _collect_text_modules(modules)
            if text_modules:
                from processing import SubtitleBurner
                burner = SubtitleBurner(ffmpeg_path=ffmpeg)
                text_overlaid_path = os.path.join(work_dir, "_with_text.mp4")
                self._apply_text_overlays(
                    burner, intermediate_path, text_modules,
                    text_overlaid_path, width, height, fps_val,
                )
                final_base = text_overlaid_path
            else:
                final_base = intermediate_path

            # Step 3.5 — Apply effect filters (color / fade / speed)
            effect_modules = _collect_effect_modules(modules)
            if effect_modules:
                effect_path = os.path.join(work_dir, "_with_effects.mp4")
                self._apply_effect_filters(
                    final_base, effect_modules, effect_path,
                    width, height, fps_val,
                )
                final_base = effect_path

            # Step 4 — Pad to match total_duration if needed
            final_base = self._ensure_duration(
                ffmpeg, final_base, work_dir, total_duration,
                width, height, fps_val,
            )

            # Step 5 — Final encode to output path
            cmd = [
                ffmpeg, "-y",
                "-i", final_base,
                "-c:v", "libx264",
                "-crf", str(crf),
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                self._last_ffmpeg_error = result.stderr.strip()[-200:]
                return False

            logger.info(
                f"FFmpeg fallback succeeded: {len(clip_list)} clips, "
                f"{len(text_modules)} text overlays"
            )
            return True

        except Exception as e:
            logger.exception("FFmpeg fallback failed")
            self._last_ffmpeg_error = str(e)[-200:]
            return False
        finally:
            # Cleanup intermediate directory
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Fallback helper: simple title card (legacy path)
    # ------------------------------------------------------------------

    def _render_simple_title_card(
        self,
        metadata: Dict[str, Any],
        output_path: str,
        ffmpeg: str,
        fps: int,
        crf: int,
        width: int,
        height: int,
    ) -> bool:
        """Render a minimal title-card MP4 (pure fallback, no modules).

        Generates a coloured background with the script title as a
        drawtext overlay. Used when no modules are present in the script.
        """
        title = metadata.get("title", "Untitled")
        duration = metadata.get("total_duration", 5.0)
        safe_title = _escape_drawtext(title)

        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={width}x{height}:d={duration}:r={fps}",
            "-vf", (
                f"drawtext=text='{safe_title}':"
                f"fontsize={max(width // 20, 24)}:"
                f"fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2"
            ),
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

    # ------------------------------------------------------------------
    # Clip building: video segments → individual clip files
    # ------------------------------------------------------------------

    def _build_base_clips(
        self,
        modules: list,
        ffmpeg: str,
        work_dir: str,
        fps: int,
        crf: int,
        width: int,
        height: int,
    ) -> list:
        """Build a sequential clip list from modules on the primary video track.

        Scans modules on the lowest-numbered track that contains
        ``video_segment`` entries and renders each as a standalone clip
        file. Non-video modules (``transition``, ``effect``) are skipped
        during clip building — they are handled later during concat.

        Returns:
            List of dicts::
                {"path": str, "module_id": str, "duration": float,
                 "start_time": float, "module_type": str}
            Ordered by ``start_time``. Empty list if no renderable clips.
        """
        # Find primary video track (lowest track_index with video_segment)
        video_tracks: set = set()
        for m in modules:
            if m.get("type") == "video_segment" and _has_source_path(m):
                video_tracks.add(m.get("track_index", 0))

        if not video_tracks:
            # No video_segment with source — fall back to track 0
            video_tracks = {0}

        primary_track = min(video_tracks)

        # Collect only renderable modules on the primary track, sorted by time
        track_mods = sorted(
            [m for m in modules
             if m.get("track_index") == primary_track
             and m.get("type") in ("video_segment", "title", "subtitle")
             and m.get("duration", 0) > 0],
            key=lambda m: m.get("start_time", 0.0),
        )

        if not track_mods:
            return []

        clips: list = []
        for mod in track_mods:
            mtype = mod.get("type", "")
            clip_path = os.path.join(work_dir, f"clip_{mod['id']}.mp4")

            if mtype == "video_segment" and _has_source_path(mod):
                # Trim segment from source video
                ok = self._render_video_clip(mod, clip_path, ffmpeg, crf)
            else:
                # Generate coloured card with text if available
                ok = self._render_text_card(
                    mod, clip_path, ffmpeg, fps, crf, width, height,
                )

            if ok and os.path.isfile(clip_path):
                clips.append({
                    "path": clip_path,
                    "module_id": mod["id"],
                    "duration": mod.get("duration", 0),
                    "start_time": mod.get("start_time", 0),
                    "module_type": mtype,
                })

        return clips

    def _render_video_clip(
        self,
        mod: dict,
        clip_path: str,
        ffmpeg: str,
        crf: int,
    ) -> bool:
        """Trim a segment from a source video file to produce a clip.

        Uses ``start_time`` as the offset into the source (trim point),
        and ``duration`` for the clip length. When ``source.start_offset``
        is explicitly set, it takes precedence over ``start_time``.
        """
        source = mod.get("source") or {}
        source_path = source.get("path", "")
        if not source_path or not os.path.isfile(source_path):
            logger.warning(f"Source video not found: {source_path}")
            return False

        duration = mod.get("duration", 0)
        if duration <= 0:
            return False

        # Trim offset: prefer explicit start_offset, fall back to start_time
        trim_offset = source.get("start_offset", mod.get("start_time", 0.0))
        trim_offset = max(0.0, float(trim_offset))

        cmd = [
            ffmpeg, "-y",
            "-ss", str(trim_offset),
            "-i", source_path,
            "-t", str(duration),
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            clip_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                logger.warning(
                    f"Failed to trim clip {mod['id']}: "
                    f"{result.stderr.strip()[-120:]}"
                )
                return False
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Trim clip {mod['id']} failed: {e}")
            return False

    def _render_text_card(
        self,
        mod: dict,
        clip_path: str,
        ffmpeg: str,
        fps: int,
        crf: int,
        width: int,
        height: int,
    ) -> bool:
        """Generate a coloured frame with optional text overlay.

        For ``title`` / ``subtitle`` modules, text is drawn centred.
        For other module types an empty coloured card is generated.
        """
        duration = max(mod.get("duration", 0), 0.5)
        mtype = mod.get("type", "")
        label = mod.get("label", "")
        params = mod.get("params") or {}
        text = params.get("text_content") or label or ""

        # Pick card colour by module type
        card_colors = {
            "title": "0x1a1a2e",
            "subtitle": "0x1a1a2e",
            "video_segment": "0x0a0a1a",
        }
        bg_color = card_colors.get(mtype, "0x222244")

        vf_parts: list = []

        if text:
            safe_text = _escape_drawtext(text)
            font_size = min(width // 24, 48)
            if mtype == "subtitle":
                # Subtitle at bottom
                vf_parts.append(
                    f"drawtext=text='{safe_text}':"
                    f"fontsize={font_size}:fontcolor=white:"
                    f"x=(w-text_w)/2:y=h-text_h-40"
                )
            else:
                # Title centred
                vf_parts.append(
                    f"drawtext=text='{safe_text}':"
                    f"fontsize={font_size}:fontcolor=white:"
                    f"x=(w-text_w)/2:y=(h-text_h)/2"
                )

        vf_str = ":".join(vf_parts) if vf_parts else "null"

        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={width}x{height}:d={duration}:r={fps}",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
        ]
        if vf_parts:
            cmd.extend(["-vf", vf_str])
        cmd.append(clip_path)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.warning(
                    f"Failed to render card {mod['id']}: "
                    f"{result.stderr.strip()[-120:]}"
                )
                return False
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Render card {mod['id']} failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Concatenation with transitions
    # ------------------------------------------------------------------

    def _concat_clips(
        self,
        ffmpeg: str,
        clip_list: list,
        modules: list,
        output_path: str,
        crf: int,
    ) -> None:
        """Concatenate clips with xfade transitions between them.

        Detects ``transition`` modules that sit between consecutive
        clips and applies the appropriate xfade transition.
        Falls back to plain concat when no transitions are needed.
        """
        from processing import VideoConcat

        clip_paths = [c["path"] for c in clip_list]
        concat = VideoConcat(ffmpeg_path=ffmpeg)

        if len(clip_paths) == 1:
            # Single clip — stream copy
            copy_cmd = [
                ffmpeg, "-y", "-i", clip_paths[0],
                "-c", "copy", output_path,
            ]
            subprocess.run(copy_cmd, capture_output=True, text=True, timeout=300)
            return

        # Try xfade if we detect transitions between clips
        transition_map = _extract_transition_map(modules, clip_list)

        if transition_map:
            # Use a common xfade type (default: fade)
            xfade_types = list(set(transition_map.values()))
            xfade_type = xfade_types[0] if xfade_types else "fade"
            # Map transition module type codes to xfade transitions
            xfade_type = _map_transition_type(xfade_type)
            try:
                concat.concat_with_crossfade(
                    clip_paths, output_path,
                    fade_duration=0.3,
                    xfade_transition=xfade_type,
                    crf=crf,
                )
                return
            except Exception:
                logger.debug("xfade concat failed, falling back to plain concat")

        # Plain concat (re-encode to handle codec mismatches)
        concat.concat(clip_paths, output_path, re_encode=True, crf=crf)

    # ------------------------------------------------------------------
    # Text overlay: title / subtitle modules → drawtext on final video
    # ------------------------------------------------------------------

    def _apply_text_overlays(
        self,
        burner: "SubtitleBurner",
        video_path: str,
        text_modules: list,
        output_path: str,
        width: int,
        height: int,
        fps: int,
    ) -> str:
        """Overlay title/subtitle text onto the video using drawtext.

        Each module's text is drawn at its ``start_time`` for
        ``duration`` seconds using FFmpeg's ``enable=between(t, ...)``.
        Multiple drawtext filters are composed into a single ``-vf``.
        """
        vf_filters: list = []
        for mod in text_modules:
            text = _get_text_content(mod)
            if not text:
                continue

            safe_text = _escape_drawtext(text)
            start = mod.get("start_time", 0.0)
            duration = mod.get("duration", 3.0)
            mtype = mod.get("type", "title")
            params = mod.get("params") or {}

            # Font size: params > type default > fallback
            font_size = params.get("font_size", 0)
            if not font_size:
                font_size = max(width // 24, 36) if mtype == "title" else max(width // 32, 28)

            font_color = params.get("font_color", "white")
            position = params.get("position", {})
            x = position.get("x", "(w-text_w)/2")
            y = position.get("y", "(h-text_h)/2" if mtype != "subtitle" else "h-text_h-40")

            drawtext = (
                f"drawtext=text='{safe_text}':"
                f"fontsize={font_size}:fontcolor={font_color}:"
                f"x={x}:y={y}:"
                f"enable='between(t,{start},{start + duration})'"
            )
            vf_filters.append(drawtext)

        if not vf_filters:
            # No text to overlay — passthrough
            shutil_cmd = [burner.ffmpeg_path or "ffmpeg",
                          "-y", "-i", video_path,
                          "-c", "copy", output_path]
            subprocess.run(shutil_cmd, capture_output=True, text=True, timeout=300)
            return output_path

        # Compose all drawtext filters into one complex filter
        vf_str = ",".join(vf_filters)

        cmd = [
            burner.ffmpeg_path or "ffmpeg",
            "-y",
            "-i", video_path,
            "-vf", vf_str,
            "-c:a", "copy",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.warning(
                f"Text overlay failed: {result.stderr.strip()[-200:]}"
            )
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout, stderr=result.stderr,
            )
        return output_path

    # ------------------------------------------------------------------
    # Effect filters: fade / color / speed applied at time ranges
    # ------------------------------------------------------------------

    def _apply_effect_filters(
        self,
        video_path: str,
        effect_modules: list,
        output_path: str,
        width: int,
        height: int,
        fps: int,
    ) -> str:
        """Apply effect filters (fade, color, speed) to the video.

        Each effect module's ``params.transition_type`` determines the
        FFmpeg filter:
          - ``fade`` / ``fade_in``  → fade filter at module start
          - ``fade_out``            → fade filter at module end
          - ``color_filter``        → eq + colorbalance filter
        Filters are time-ranged via ``enable='between(t,start,end)'``
        so they only affect the module's time window.
        """
        import shutil
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"

        vf_filters: list = []

        for mod in effect_modules:
            start = mod.get("start_time", 0.0)
            duration = mod.get("duration", 0.0)
            if duration <= 0:
                continue
            params = mod.get("params") or {}
            effect_type = params.get("transition_type", "fade")

            if effect_type in ("fade", "fade_in"):
                vf_filters.append(
                    f"fade=t=in:st={start}:d={min(duration, 2.0)}"
                )
            elif effect_type == "fade_out":
                vf_filters.append(
                    f"fade=t=out:st={start}:d={min(duration, 2.0)}"
                )
            elif effect_type == "color_filter":
                # Apply hue / saturation / brightness adjustments
                hue_val = params.get("hue", 0)
                sat_val = params.get("saturation", 1.0)
                bright_val = params.get("brightness", 0.0)
                eq_parts = [
                    f"contrast={params.get('contrast', 1.0)}",
                    f"brightness={bright_val}",
                    f"saturation={sat_val}",
                ]
                eq_str = "eq=" + ":".join(eq_parts)
                if hue_val != 0:
                    eq_str += f":hue=H={hue_val}"
                vf_filters.append(
                    f"{eq_str}:enable='between(t,{start},{start + duration})'"
                )
            elif effect_type == "speed_change":
                # setpts changes clip timing — apply to whole video segment
                # by trimming and re-inserting at correct time (skipped for now
                # — speed_change on a time range requires re-trimming)
                logger.debug(
                    f"Effect '{mod.get('id')}': speed_change skipped "
                    f"(not supported in time-range mode)"
                )

        if not vf_filters:
            # No applicable effects — stream copy
            cmd = [
                ffmpeg, "-y", "-i", video_path,
                "-c:v", "copy", "-c:a", "copy",
                output_path,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return output_path

        vf_str = ",".join(vf_filters)

        cmd = [
            ffmpeg, "-y",
            "-i", video_path,
            "-vf", vf_str,
            "-c:a", "copy",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.warning(
                f"Effect filter failed: {result.stderr.strip()[-200:]}"
            )
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout, stderr=result.stderr,
            )
        return output_path

    # ------------------------------------------------------------------
    # Duration padding
    # ------------------------------------------------------------------

    def _ensure_duration(
        self,
        ffmpeg: str,
        video_path: str,
        work_dir: str,
        target_duration: float,
        width: int,
        height: int,
        fps: int,
    ) -> str:
        """Pad the video to *target_duration* if shorter, else return as-is.

        If the video is already at or longer than target, a simple
        stream-copy is made (so the caller always gets a new file they
        can clean up independently).
        """
        from processing.transcoder import FFmpegTranscoder

        try:
            transcoder = FFmpegTranscoder(ffmpeg_path=ffmpeg)
            meta = transcoder.get_metadata(video_path)
            actual_dur = meta.get("duration", 0)
        except Exception:
            actual_dur = 0

        padded = os.path.join(work_dir, "_padded.mp4")

        if actual_dur > 0 and target_duration > actual_dur + 0.5:
            pad_dur = target_duration - actual_dur
            cmd = [
                ffmpeg, "-y",
                "-i", video_path,
                "-f", "lavfi",
                "-i", f"color=c=black:s={width}x{height}:d={pad_dur}:r={fps}",
                "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex",
                f"[0:v][1:v]concat=n=2:v=1:a=0[vo];[0:a][2:a]concat=n=2:v=0:a=1[ao]",
                "-map", "[vo]",
                "-map", "[ao]",
                "-c:v", "libx264",
                "-crf", "28",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                padded,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return padded

        # Stream copy as safe return (same content, different path)
        cmd = [ffmpeg, "-y", "-i", video_path, "-c:v", "copy", "-c:a", "copy", padded]
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return padded


# ═══════════════════════════════════════════════════════════════════
# Module-level helpers (not class methods — stateless)
# ═══════════════════════════════════════════════════════════════════

def _escape_drawtext(text: str) -> str:
    """Escape text for FFmpeg drawtext filter argument.

    FFmpeg drawtext uses single quotes for text delimiters internally,
    so we must escape: backslashes, single quotes, colons, and percent
    signs (drawtext format specifiers).
    """
    return (text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace("%", "\\%"))


def _get_text_content(mod: dict) -> str:
    """Extract best available text from a module.

    Preference: ``params.text_content`` > ``label`` > empty string.
    """
    params = mod.get("params") or {}
    text = params.get("text_content") or ""
    if not text:
        text = mod.get("label", "")
    return text


def _has_source_path(mod: dict) -> bool:
    """Check if a module references an existing source video file."""
    source = mod.get("source") or {}
    path = source.get("path", "")
    return bool(path) and os.path.isfile(path)


def _collect_text_modules(modules: list) -> list:
    """Return all modules with renderable text content.

    Includes ``title`` and ``subtitle`` types that have non-empty text.
    """
    result = []
    for m in modules:
        mtype = m.get("type", "")
        if mtype not in ("title", "subtitle"):
            continue
        if _get_text_content(m):
            result.append(m)
    return result


def _collect_effect_modules(modules: list) -> list:
    """Return all effect modules that can be rendered.

    Includes ``effect`` type modules with a recognised
    ``params.transition_type`` (fade, fade_in, fade_out, color_filter).
    Modules with ``speed_change`` are excluded — they require per-clip
    timing changes that the time-range filter model doesn't support.
    """
    SUPPORTED = {"fade", "fade_in", "fade_out", "color_filter"}
    result = []
    for m in modules:
        if m.get("type") != "effect":
            continue
        params = m.get("params") or {}
        etype = params.get("transition_type", "")
        if etype in SUPPORTED and m.get("duration", 0) > 0:
            result.append(m)
    return result


def _extract_transition_map(
    modules: list,
    clip_list: list,
) -> dict:
    """Build a mapping of clip index → transition type.

    Scans all ``transition`` modules and matches them to the gap
    between consecutive clips based on ``start_time``.

    Returns:
        Dict ``{clip_index_before: transition_type}``.
        E.g. ``{0: "dissolve", 2: "fade"}`` means a dissolve transition
        between clip 0 → clip 1, and a fade between clip 2 → clip 3.
    """
    if len(clip_list) < 2:
        return {}

    transition_map: dict = {}

    for mod in modules:
        if mod.get("type") != "transition":
            continue
        t_start = mod.get("start_time", 0.0)
        t_dur = mod.get("duration", 0.0)
        params = mod.get("params") or {}
        trans_type = params.get("transition_type", "fade")

        # Find which clip gap this transition falls into
        for ci in range(len(clip_list) - 1):
            c_end = clip_list[ci]["start_time"] + clip_list[ci]["duration"]
            c_next_start = clip_list[ci + 1]["start_time"]
            # Transition should be around the boundary (±0.5s tolerance)
            gap_mid = (c_end + c_next_start) / 2
            if abs(t_start - gap_mid) < 1.0:
                transition_map[ci] = trans_type
                break

    return transition_map


def _map_transition_type(trans_type: str) -> str:
    """Map script transition type names to FFmpeg xfade transition names.

    FFmpeg xfade supports: fade, wipeleft, wiperight, wipeup, wipedown,
    slideleft, slideright, fadegrays, etc.
    """
    mapping = {
        "dissolve": "fade",
        "fade": "fade",
        "fade_in": "fade",
        "fade_out": "fade",
        "wipeleft": "wipeleft",
        "wiperight": "wiperight",
        "wipeup": "wipeup",
        "wipedown": "wipedown",
        "slideleft": "slideleft",
        "slideright": "slideright",
        "fadegrays": "fadegrays",
        "fadeblack": "fadeblack",
        "fadewhite": "fadewhite",
        "circlecrop": "circleclamp",
    }
    return mapping.get(trans_type.lower(), "fade")
