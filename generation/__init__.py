"""Generation layer: rendering engine composition and deprecated adaptor."""

from generation.composer import Composer
from generation.renderer import HyperFramesRenderer
from generation.render_engine import (
    RenderEngine,
    HyperFramesEngine,
    FFmpegEngine,
    CompositeEngine,
    get_engine,
    register_engine,
)

__all__ = [
    "Composer",
    "HyperFramesRenderer",
    "RenderEngine",
    "HyperFramesEngine",
    "FFmpegEngine",
    "CompositeEngine",
    "get_engine",
    "register_engine",
]
