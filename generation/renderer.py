"""Deprecated adaptor — delegates to :mod:`generation.render_engine`.

.. deprecated::
    Use :func:`generation.render_engine.get_engine` and
    :class:`~generation.render_engine.CompositeEngine` directly.
    This module is preserved for backward compatibility.
"""

import asyncio
import logging
import os
import warnings
from typing import Any, Dict, Optional
from pathlib import Path

warnings.warn(
    "HyperFramesRenderer is deprecated — use "
    "generation.render_engine.get_engine() instead.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)


class HyperFramesRenderer:
    """Deprecated — delegates to :class:`generation.render_engine.CompositeEngine`.

    .. deprecated::
        Use ``from generation.render_engine import get_engine`` and
        ``get_engine("composite").render(...)`` instead.
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
        """Render a MigratableScript to MP4 (delegates to CompositeEngine).

        .. deprecated::
            Use ``get_engine("composite").render(...)`` for new code.

        Args:
            script_json: Complete MigratableScript dict.
            output_path: Absolute path for the output MP4 file.
            fps: Output frame rate.
            crf: Constant Rate Factor.
            cleanup_html: Kept for API compat (no-op).

        Returns:
            Absolute path to the rendered MP4 file.

        Raises:
            RuntimeError: If rendering fails.
        """
        from generation.render_engine import get_engine

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        engine = get_engine(
            "composite",
            work_dir=self.work_dir,
            fps=fps,
            crf=crf,
            hyperframes_cli=self.hyperframes_cli,
            template_path=self.template_path,
        )

        async def _run() -> str:
            return await engine.render(
                script_json,
                output_path,
                progress_callback=lambda p, s, e: None,
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(_run())).result(timeout=1800)

        return asyncio.run(_run())
