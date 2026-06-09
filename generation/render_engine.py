"""Render engine: strategy-pattern abstraction over video rendering backends.

Provides a family of interchangeable render engines (HyperFrames, FFmpeg,
composite) with progress callback support, timeout control, and graceful
degradation.  New engines implement :class:`RenderEngine` and register
via the factory :func:`get_engine`.
"""

import abc
import asyncio
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# ── Progress callback type ──
#   progress: 0-100 integer
#   stage:    human-readable stage name
#   eta:      estimated seconds remaining (0 if unknown)
ProgressCallback = Callable[[int, str, int], None]

# Sentinel used as a no-op progress callback
_NULL_PROGRESS: ProgressCallback = lambda p, s, e: None


# ═══════════════════════════════════════════════════════════════════
#  Abstract base
# ═══════════════════════════════════════════════════════════════════

class RenderEngine(abc.ABC):
    """Abstract base for all render engines.

    Subclasses must implement :meth:`render` and, optionally, override
    the default timeout or report capabilities via class attributes.
    """

    # Default timeout in seconds (30 min).  Callers can override per-call.
    DEFAULT_TIMEOUT: int = 1800

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Short human-readable identifier, e.g. ``"hyperframes"``."""

    @abc.abstractmethod
    async def render(
        self,
        script_json: Dict[str, Any],
        output_path: str,
        *,
        progress_callback: ProgressCallback = _NULL_PROGRESS,
        timeout: Optional[int] = None,
    ) -> str:
        """Render a MigratableScript to an MP4 video file.

        Args:
            script_json: Complete MigratableScript dict.
            output_path: Absolute path for the output MP4 file.
            progress_callback: Called with ``(progress, stage, eta)``
                during rendering.
            timeout: Max seconds for the full render. Falls back to
                ``self.DEFAULT_TIMEOUT``.

        Returns:
            Absolute path to the rendered MP4 file.

        Raises:
            RuntimeError: If rendering fails for any reason.
        """

    def check_available(self) -> bool:
        """Return True if this engine's dependencies are satisfied.

        Base implementation returns True.  Subclasses may override
        to check for CLI executables, libraries, etc.
        """
        return True


# ═══════════════════════════════════════════════════════════════════
#  HyperFrames engine
# ═══════════════════════════════════════════════════════════════════

class HyperFramesEngine(RenderEngine):
    """Renders via the HyperFrames CLI pipeline.

    Uses HtmlComposer → temp HTML → ``hyperframes render`` CLI.
    """

    @property
    def name(self) -> str:
        return "hyperframes"

    def __init__(
        self,
        cli_path: str = "hyperframes",
        work_dir: Optional[str] = None,
        template_path: Optional[str] = None,
        fps: int = 30,
        crf: int = 23,
    ) -> None:
        self.cli_path = cli_path
        self.work_dir = work_dir or os.getcwd()
        self.template_path = template_path or ""
        self.fps = fps
        self.crf = crf

    def check_available(self) -> bool:
        """Verify HyperFrames CLI is on PATH and responds."""
        found = shutil.which(self.cli_path)
        if not found:
            return False
        try:
            result = subprocess.run(
                [found, "--version"],
                capture_output=True, text=True, timeout=15,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    async def render(
        self,
        script_json: Dict[str, Any],
        output_path: str,
        *,
        progress_callback: ProgressCallback = _NULL_PROGRESS,
        timeout: Optional[int] = None,
    ) -> str:
        from generation.composer import Composer

        time_budget = timeout or self.DEFAULT_TIMEOUT
        metadata = script_json.get("metadata") or {}
        title = metadata.get("title", "output")

        # 1. Compose HTML
        progress_callback(5, "合成 HTML 模板", 0)
        composer = Composer(template_path=self.template_path)
        html = composer.script_to_html(script_json)

        html_path = os.path.join(self.work_dir, f"_hf_{title}.html")
        Path(html_path).parent.mkdir(parents=True, exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # 2. Ensure output dir exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 3. Run HyperFrames CLI
        progress_callback(15, "调用 HyperFrames CLI 渲染", 0)
        cmd = [
            self.cli_path, "render",
            "--input", html_path,
            "--output", output_path,
            "--fps", str(self.fps),
            "--crf", str(self.crf),
        ]

        t0 = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=time_budget,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"HyperFrames CLI exited {result.returncode}: "
                    f"{result.stderr.strip()[-300:]}"
                )

        except FileNotFoundError as exc:
            raise RuntimeError(
                f"HyperFrames CLI not found ('{self.cli_path}'): {exc}"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"HyperFrames render timed out after {time_budget}s"
            )
        finally:
            try:
                os.remove(html_path)
            except OSError:
                pass

        elapsed = time.time() - t0
        progress_callback(100, "HyperFrames 渲染完成", 0)
        logger.info(
            "HyperFramesEngine: rendered in %.1fs → %s", elapsed, output_path
        )
        return output_path


# ═══════════════════════════════════════════════════════════════════
#  FFmpeg engine
# ═══════════════════════════════════════════════════════════════════

class FFmpegEngine(RenderEngine):
    """Renders directly via FFmpeg (modular fallback path).

    Handles ``video_segment``, ``title``, ``subtitle``, ``transition``,
    and ``effect`` module types.  See :class:`HyperFramesRenderer` for
    implementation details.
    """

    @property
    def name(self) -> str:
        return "ffmpeg"

    def __init__(
        self,
        work_dir: Optional[str] = None,
        fps: int = 30,
        crf: int = 23,
    ) -> None:
        self.work_dir = work_dir or os.getcwd()
        self.fps = fps
        self.crf = crf

    def check_available(self) -> bool:
        """Verify FFmpeg is on PATH and responds."""
        found = shutil.which("ffmpeg")
        if not found:
            return False
        try:
            result = subprocess.run(
                [found, "-version"],
                capture_output=True, text=True, timeout=15,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    # ------------------------------------------------------------------
    #  Public render — inline FFmpeg pipeline (no renderer.py dependency)
    # ------------------------------------------------------------------

    async def render(
        self,
        script_json: Dict[str, Any],
        output_path: str,
        *,
        progress_callback: ProgressCallback = _NULL_PROGRESS,
        timeout: Optional[int] = None,
    ) -> str:
        """Render via modular FFmpeg pipeline.

        Handles ``video_segment`` (trim from source), ``title`` / ``subtitle``
        (drawtext overlay), ``transition`` (xfade between clips), and
        ``effect`` (fade / color filter) module types.
        """
        time_budget = timeout or self.DEFAULT_TIMEOUT
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        progress_callback(5, "初始化 FFmpeg 渲染器", 0)

        def _run_sync() -> str:
            self._render_sync(script_json, output_path)
            return output_path

        t0 = time.time()
        try:
            progress_callback(10, "提取视频段并裁剪", 0)
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _run_sync),
                timeout=time_budget,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"FFmpeg render timed out after {time_budget}s")

        elapsed = time.time() - t0
        progress_callback(100, "FFmpeg 渲染完成", 0)
        logger.info("FFmpegEngine: rendered in %.1fs → %s", elapsed, output_path)
        return result

    # ------------------------------------------------------------------
    #  Synchronous rendering pipeline
    # ------------------------------------------------------------------

    def _render_sync(
        self,
        script_json: Dict[str, Any],
        output_path: str,
    ) -> None:
        """Synchronous FFmpeg render (runs in thread pool)."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("FFmpeg not found on PATH")

        metadata = script_json.get("metadata") or {}
        modules: list = script_json.get("modules") or []
        width = (metadata.get("resolution") or {}).get("width", 1920)
        height = (metadata.get("resolution") or {}).get("height", 1080)
        total_duration = metadata.get("total_duration", 5.0)
        fps_val = int(metadata.get("fps", self.fps) or self.fps)

        if not modules:
            logger.warning("No modules; rendering simple title card")
            self._render_simple_title_card(
                ffmpeg, metadata, output_path, fps_val, width, height,
            )
            return

        import uuid as _uuid
        work_tag = _uuid.uuid4().hex[:8]
        work_dir = os.path.join(self.work_dir, f"_ffmpeg_{work_tag}")
        os.makedirs(work_dir, exist_ok=True)

        try:
            clip_list = self._build_base_clips(
                modules, ffmpeg, work_dir, fps_val, width, height,
            )

            if not clip_list:
                logger.warning("No renderable clips; rendering title card")
                self._render_simple_title_card(
                    ffmpeg, metadata, output_path, fps_val, width, height,
                )
                return

            intermediate = os.path.join(work_dir, "_concat.mp4")
            self._concat_clips(ffmpeg, clip_list, modules, intermediate)

            text_mods = _collect_text_modules(modules)
            if text_mods:
                text_path = os.path.join(work_dir, "_text.mp4")
                self._apply_text_overlays(
                    ffmpeg, intermediate, text_mods, text_path,
                    width, height, fps_val,
                )
                final_base = text_path
            else:
                final_base = intermediate

            effect_mods = _collect_effect_modules(modules)
            if effect_mods:
                effect_path = os.path.join(work_dir, "_effect.mp4")
                self._apply_effect_filters(
                    ffmpeg, final_base, effect_mods, effect_path,
                )
                final_base = effect_path

            final_base = self._ensure_duration(
                ffmpeg, final_base, work_dir, total_duration,
                width, height, fps_val,
            )

            subprocess.run([
                ffmpeg, "-y", "-i", final_base,
                "-c:v", "libx264", "-crf", str(self.crf),
                "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                output_path,
            ], capture_output=True, text=True, timeout=600)

        finally:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    #  Simple title card
    # ------------------------------------------------------------------

    def _render_simple_title_card(
        self, ffmpeg: str, metadata: dict, output_path: str,
        fps: int, width: int, height: int,
    ) -> None:
        title = _escape_drawtext(metadata.get("title", "Untitled"))
        duration = metadata.get("total_duration", 5.0)
        subprocess.run([
            ffmpeg, "-y", "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={width}x{height}:d={duration}:r={fps}",
            "-vf", f"drawtext=text='{title}':fontsize={max(width//20,24)}:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264", "-crf", str(self.crf),
            "-preset", "fast", "-pix_fmt", "yuv420p",
            output_path,
        ], capture_output=True, text=True, timeout=300)

    # ------------------------------------------------------------------
    #  Clip building
    # ------------------------------------------------------------------

    def _build_base_clips(
        self, modules: list, ffmpeg: str, work_dir: str,
        fps: int, width: int, height: int,
    ) -> list:
        video_tracks: set = set()
        for m in modules:
            if m.get("type") == "video_segment" and _has_source_path(m):
                video_tracks.add(m.get("track_index", 0))
        if not video_tracks:
            video_tracks = {0}
        primary = min(video_tracks)

        track_mods = sorted(
            [m for m in modules
             if m.get("track_index") == primary
             and m.get("type") in ("video_segment", "title", "subtitle")
             and m.get("duration", 0) > 0],
            key=lambda m: m.get("start_time", 0.0),
        )
        if not track_mods:
            return []

        clips = []
        for mod in track_mods:
            cp = os.path.join(work_dir, f"clip_{mod['id']}.mp4")
            ok = False
            if mod["type"] == "video_segment" and _has_source_path(mod):
                ok = self._render_video_clip(mod, cp, ffmpeg)
            else:
                ok = self._render_text_card(
                    mod, cp, ffmpeg, fps, width, height,
                )
            if ok and os.path.isfile(cp):
                clips.append({
                    "path": cp, "module_id": mod["id"],
                    "duration": mod.get("duration", 0),
                    "start_time": mod.get("start_time", 0),
                    "module_type": mod["type"],
                })
        return clips

    def _render_video_clip(self, mod: dict, clip_path: str, ffmpeg: str) -> bool:
        source = mod.get("source") or {}
        src_path = source.get("path", "")
        if not src_path or not os.path.isfile(src_path):
            return False
        duration = mod.get("duration", 0)
        if duration <= 0:
            return False
        offset = max(0.0, float(source.get("start_offset", mod.get("start_time", 0.0))))
        r = subprocess.run([
            ffmpeg, "-y", "-ss", str(offset), "-i", src_path,
            "-t", str(duration),
            "-c:v", "libx264", "-crf", str(self.crf),
            "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            clip_path,
        ], capture_output=True, text=True, timeout=600)
        return r.returncode == 0

    def _render_text_card(
        self, mod: dict, clip_path: str, ffmpeg: str,
        fps: int, width: int, height: int,
    ) -> bool:
        duration = max(mod.get("duration", 0), 0.5)
        mtype = mod.get("type", "")
        text = mod.get("params", {}).get("text_content", "") or mod.get("label", "")
        colors = {"title": "0x1a1a2e", "subtitle": "0x1a1a2e", "video_segment": "0x0a0a1a"}
        bg = colors.get(mtype, "0x222244")

        cmd = [
            ffmpeg, "-y", "-f", "lavfi",
            "-i", f"color=c={bg}:s={width}x{height}:d={duration}:r={fps}",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-c:v", "libx264", "-crf", str(self.crf),
            "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest",
        ]
        if text:
            safe = _escape_drawtext(text)
            fs = max(width // 24, 48) if mtype == "title" else max(width // 32, 28)
            y_pos = "h-text_h-40" if mtype == "subtitle" else "(h-text_h)/2"
            cmd.extend(["-vf", f"drawtext=text='{safe}':fontsize={fs}:fontcolor=white:x=(w-text_w)/2:y={y_pos}"])
        cmd.append(clip_path)

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return r.returncode == 0

    # ------------------------------------------------------------------
    #  Concat with transitions
    # ------------------------------------------------------------------

    def _concat_clips(
        self, ffmpeg: str, clip_list: list,
        modules: list, output_path: str,
    ) -> None:
        from processing import VideoConcat
        paths = [c["path"] for c in clip_list]
        concat = VideoConcat(ffmpeg_path=ffmpeg)

        if len(paths) == 1:
            subprocess.run([ffmpeg, "-y", "-i", paths[0], "-c", "copy", output_path],
                           capture_output=True, text=True, timeout=300)
            return

        tmap = _extract_transition_map(modules, clip_list)
        if tmap:
            xtype = _map_transition_type(list(tmap.values())[0])
            try:
                concat.concat_with_crossfade(paths, output_path, fade_duration=0.3,
                                              xfade_transition=xtype, crf=self.crf)
                return
            except Exception:
                pass
        concat.concat(paths, output_path, re_encode=True, crf=self.crf)

    # ------------------------------------------------------------------
    #  Text overlays
    # ------------------------------------------------------------------

    def _apply_text_overlays(
        self, ffmpeg: str, video_path: str,
        text_modules: list, output_path: str,
        width: int, height: int, fps: int,
    ) -> str:
        vf = []
        for mod in text_modules:
            text = _get_text_content(mod)
            if not text:
                continue
            safe = _escape_drawtext(text)
            s = mod.get("start_time", 0.0)
            d = mod.get("duration", 3.0)
            mt = mod.get("type", "title")
            p = mod.get("params", {})
            fs = p.get("font_size", 0) or (max(width // 24, 36) if mt == "title" else max(width // 32, 28))
            fc = p.get("font_color", "white")
            pos = p.get("position", {})
            x = pos.get("x", "(w-text_w)/2")
            y = pos.get("y", "h-text_h-40" if mt == "subtitle" else "(h-text_h)/2")
            vf.append(
                f"drawtext=text='{safe}':fontsize={fs}:fontcolor={fc}:"
                f"x={x}:y={y}:enable='between(t,{s},{s+d})'"
            )

        if not vf:
            subprocess.run([ffmpeg, "-y", "-i", video_path, "-c", "copy", output_path],
                           capture_output=True, text=True, timeout=300)
            return output_path

        subprocess.run(
            [ffmpeg, "-y", "-i", video_path, "-vf", ",".join(vf), "-c:a", "copy", output_path],
            capture_output=True, text=True, timeout=600,
        )
        return output_path

    # ------------------------------------------------------------------
    #  Effect filters
    # ------------------------------------------------------------------

    def _apply_effect_filters(
        self, ffmpeg: str, video_path: str,
        effect_modules: list, output_path: str,
    ) -> str:
        vf = []
        for mod in effect_modules:
            s = mod.get("start_time", 0.0)
            d = mod.get("duration", 0.0)
            if d <= 0:
                continue
            etype = mod.get("params", {}).get("transition_type", "fade")

            if etype in ("fade", "fade_in"):
                vf.append(f"fade=t=in:st={s}:d={min(d, 2.0)}")
            elif etype == "fade_out":
                vf.append(f"fade=t=out:st={s}:d={min(d, 2.0)}")
            elif etype == "color_filter":
                p = mod.get("params", {})
                eq = "eq=" + ":".join([
                    f"contrast={p.get('contrast', 1.0)}",
                    f"brightness={p.get('brightness', 0.0)}",
                    f"saturation={p.get('saturation', 1.0)}",
                ])
                if p.get("hue", 0):
                    eq += f":hue=H={p['hue']}"
                vf.append(f"{eq}:enable='between(t,{s},{s+d})'")

        if not vf:
            subprocess.run([ffmpeg, "-y", "-i", video_path, "-c", "copy", output_path],
                           capture_output=True, text=True, timeout=300)
            return output_path

        subprocess.run(
            [ffmpeg, "-y", "-i", video_path, "-vf", ",".join(vf), "-c:a", "copy", output_path],
            capture_output=True, text=True, timeout=600,
        )
        return output_path

    # ------------------------------------------------------------------
    #  Duration padding
    # ------------------------------------------------------------------

    def _ensure_duration(
        self, ffmpeg: str, video_path: str, work_dir: str,
        target: float, width: int, height: int, fps: int,
    ) -> str:
        from processing.transcoder import FFmpegTranscoder
        try:
            meta = FFmpegTranscoder(ffmpeg_path=ffmpeg).get_metadata(video_path)
            actual = meta.get("duration", 0)
        except Exception:
            actual = 0

        padded = os.path.join(work_dir, "_padded.mp4")
        if actual > 0 and target > actual + 0.5:
            pad = target - actual
            subprocess.run([
                ffmpeg, "-y", "-i", video_path,
                "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d={pad}:r={fps}",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex",
                f"[0:v][1:v]concat=n=2:v=1:a=0[vo];[0:a][2:a]concat=n=2:v=0:a=1[ao]",
                "-map", "[vo]", "-map", "[ao]",
                "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                padded,
            ], capture_output=True, text=True, timeout=300)
            return padded

        subprocess.run(
            [ffmpeg, "-y", "-i", video_path, "-c:v", "copy", "-c:a", "copy", padded],
            capture_output=True, text=True, timeout=300,
        )
        return padded


# ═══════════════════════════════════════════════════════════════════
#  Composite engine (auto-select + graceful degradation)
# ═══════════════════════════════════════════════════════════════════

class CompositeEngine(RenderEngine):
    """Automatically selects the best available engine with fallback.

    Strategy:
      1. Try ``preferred`` engine (or HyperFrames by default).
      2. If it fails, fall back to FFmpeg.
      3. If both fail, raise RuntimeError.

    Progress is forwarded from whichever engine is currently active.
    """

    @property
    def name(self) -> str:
        return "composite"

    def __init__(
        self,
        preferred: Optional[str] = None,
        work_dir: Optional[str] = None,
        fps: int = 30,
        crf: int = 23,
        hyperframes_cli: str = "hyperframes",
        template_path: str = "",
    ) -> None:
        self.preferred = preferred or "hyperframes"
        self.work_dir = work_dir or os.getcwd()
        self.fps = fps
        self.crf = crf
        self.hyperframes_cli = hyperframes_cli
        self.template_path = template_path

        # Build engines lazily
        self._hf_engine: Optional[HyperFramesEngine] = None
        self._ffmpeg_engine: Optional[FFmpegEngine] = None
        self._last_error: Optional[str] = None

    def check_available(self) -> bool:
        """At least one engine must be available."""
        try:
            eng = self._resolve_engine()
            return eng is not None and eng.check_available()
        except RuntimeError:
            return False

    def _resolve_engine(self) -> RenderEngine:
        """Return the best available engine based on preference."""
        # If both engines can run, prefer the user's choice
        hf = HyperFramesEngine(
            cli_path=self.hyperframes_cli,
            work_dir=self.work_dir,
            template_path=self.template_path,
            fps=self.fps, crf=self.crf,
        )
        ff = FFmpegEngine(
            work_dir=self.work_dir,
            fps=self.fps, crf=self.crf,
        )

        available_hf = hf.check_available()
        available_ff = ff.check_available()

        if available_hf and self.preferred == "hyperframes":
            return hf
        if available_ff and self.preferred == "ffmpeg":
            return ff
        if available_hf:
            return hf
        if available_ff:
            return ff

        raise RuntimeError(
            "No render engine available — HyperFrames CLI and FFmpeg "
            "are both missing or broken.  Install FFmpeg from "
            "https://ffmpeg.org/download.html"
        )

    async def render(
        self,
        script_json: Dict[str, Any],
        output_path: str,
        *,
        progress_callback: ProgressCallback = _NULL_PROGRESS,
        timeout: Optional[int] = None,
    ) -> str:
        # ── Phase 1: try primary engine ──
        time_budget = timeout or self.DEFAULT_TIMEOUT
        metadata = script_json.get("metadata") or {}
        title = metadata.get("title", "Untitled")

        primary = self._resolve_engine()
        logger.info(
            "CompositeEngine: primary engine = %s (%s)",
            primary.name, primary.__class__.__name__,
        )

        def _wrap_pb(prefix: str) -> ProgressCallback:
            def _inner(p: int, s: str, e: int) -> None:
                progress_callback(p, f"[{prefix}] {s}", e)
            return _inner

        if primary.name == "hyperframes":
            progress_callback(0, "尝试 HyperFrames CLI 渲染", 0)
        else:
            progress_callback(0, "使用 FFmpeg 直接渲染", 0)

        try:
            # Engine gets 90% of the budget for phase 1
            return await primary.render(
                script_json, output_path,
                progress_callback=_wrap_pb(primary.name),
                timeout=max(int(time_budget * 0.9), 60),
            )
        except RuntimeError as e:
            logger.warning("Primary engine %s failed: %s", primary.name, e)
            self._last_error = str(e)

        # ── Phase 2: fallback ──
        fallback = self._get_fallback(primary)

        if fallback is None:
            raise RuntimeError(
                f"Primary engine ({primary.name}) failed and no fallback "
                f"available: {self._last_error}"
            )

        progress_callback(0, f"降级到 {fallback.name} 引擎渲染", 0)
        logger.info(
            "CompositeEngine: falling back to %s", fallback.name
        )

        remaining = max(int(time_budget * 0.5), 60)
        return await fallback.render(
            script_json, output_path,
            progress_callback=_wrap_pb(fallback.name),
            timeout=remaining,
        )

    def _get_fallback(
        self, failed_engine: RenderEngine
    ) -> Optional[RenderEngine]:
        """Return an engine different from *failed_engine*, or None."""
        if isinstance(failed_engine, HyperFramesEngine):
            return FFmpegEngine(
                work_dir=self.work_dir,
                fps=self.fps, crf=self.crf,
            )
        if isinstance(failed_engine, FFmpegEngine):
            return HyperFramesEngine(
                cli_path=self.hyperframes_cli,
                work_dir=self.work_dir,
                template_path=self.template_path,
                fps=self.fps, crf=self.crf,
            )
        # Unknown engine type — try both
        hf = HyperFramesEngine(
            cli_path=self.hyperframes_cli,
            work_dir=self.work_dir,
            template_path=self.template_path,
            fps=self.fps, crf=self.crf,
        )
        if hf.check_available():
            return hf
        ff = FFmpegEngine(
            work_dir=self.work_dir,
            fps=self.fps, crf=self.crf,
        )
        return ff if ff.check_available() else None


# ═══════════════════════════════════════════════════════════════════
#  Factory
# ═══════════════════════════════════════════════════════════════════

_ENGINE_REGISTRY: Dict[str, type] = {
    "hyperframes": HyperFramesEngine,
    "ffmpeg": FFmpegEngine,
    "composite": CompositeEngine,
}


def get_engine(
    preference: str = "composite",
    *,
    work_dir: Optional[str] = None,
    fps: int = 30,
    crf: int = 23,
    hyperframes_cli: str = "hyperframes",
    template_path: str = "",
) -> RenderEngine:
    """Return a :class:`RenderEngine` instance matching *preference*.

    Args:
        preference: ``"hyperframes"`` | ``"ffmpeg"`` | ``"composite"``
            (default).  ``"composite"`` auto-selects with degradation.
        work_dir: Working directory for intermediate files (default CWD).
        fps: Output frame rate.
        crf: Constant Rate Factor.
        hyperframes_cli: Path to HyperFrames CLI.
        template_path: Path to custom HTML template.

    Returns:
        A ready-to-use :class:`RenderEngine` instance.

    Raises:
        ValueError: If *preference* is not recognised.
    """
    cls = _ENGINE_REGISTRY.get(preference)
    if cls is None:
        raise ValueError(
            f"Unknown engine preference '{preference}'. "
            f"Valid: {list(_ENGINE_REGISTRY)}"
        )

    if cls is HyperFramesEngine:
        return cls(
            cli_path=hyperframes_cli,
            work_dir=work_dir,
            template_path=template_path,
            fps=fps, crf=crf,
        )
    if cls is FFmpegEngine:
        return cls(
            work_dir=work_dir,
            fps=fps, crf=crf,
        )
    # CompositeEngine
    return cls(
        preferred=preference,
        work_dir=work_dir,
        fps=fps, crf=crf,
        hyperframes_cli=hyperframes_cli,
        template_path=template_path,
    )


def register_engine(name: str, engine_cls: type) -> None:
    """Register a custom engine class under *name* for use with factory.

    Args:
        name: Short identifier (e.g. ``"remotion"``).
        engine_cls: Subclass of :class:`RenderEngine`.
    """
    _ENGINE_REGISTRY[name] = engine_cls


# ═══════════════════════════════════════════════════════════════════
#  Module-level helpers (shared by FFmpegEngine)
# ═══════════════════════════════════════════════════════════════════

def _escape_drawtext(text: str) -> str:
    return (text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace("%", "\\%"))


def _get_text_content(mod: dict) -> str:
    params = mod.get("params") or {}
    text = params.get("text_content") or ""
    if not text:
        text = mod.get("label", "")
    return text


def _has_source_path(mod: dict) -> bool:
    source = mod.get("source") or {}
    path = source.get("path", "")
    return bool(path) and os.path.isfile(path)


def _collect_text_modules(modules: list) -> list:
    result = []
    for m in modules:
        mtype = m.get("type", "")
        if mtype not in ("title", "subtitle"):
            continue
        if _get_text_content(m):
            result.append(m)
    return result


def _collect_effect_modules(modules: list) -> list:
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


def _extract_transition_map(modules: list, clip_list: list) -> dict:
    if len(clip_list) < 2:
        return {}
    tmap: dict = {}
    for mod in modules:
        if mod.get("type") != "transition":
            continue
        t_start = mod.get("start_time", 0.0)
        params = mod.get("params") or {}
        trans_type = params.get("transition_type", "fade")
        for ci in range(len(clip_list) - 1):
            c_end = clip_list[ci]["start_time"] + clip_list[ci]["duration"]
            c_next_start = clip_list[ci + 1]["start_time"]
            gap_mid = (c_end + c_next_start) / 2
            if abs(t_start - gap_mid) < 1.0:
                tmap[ci] = trans_type
                break
    return tmap


def _map_transition_type(trans_type: str) -> str:
    mapping = {
        "dissolve": "fade", "fade": "fade", "fade_in": "fade",
        "fade_out": "fade", "wipeleft": "wipeleft", "wiperight": "wiperight",
        "wipeup": "wipeup", "wipedown": "wipedown", "slideleft": "slideleft",
        "slideright": "slideright", "fadegrays": "fadegrays",
        "fadeblack": "fadeblack", "fadewhite": "fadewhite",
        "circlecrop": "circleclamp",
    }
    return mapping.get(trans_type.lower(), "fade")
