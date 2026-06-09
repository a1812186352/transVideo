"""Whisper model auto-download and cache manager.

Handles model existence checks, automatic download on first run,
progress callbacks, and network error recovery for both openai-whisper
and faster-whisper backends.

Cache directory: ``~/.cache/whisper`` (shared by both backends upstream).
"""

import os
import sys
import logging
from pathlib import Path
from typing import Callable, Optional, Tuple

_log = logging.getLogger(__name__)

# ── Cache directory ──

def _cache_dir() -> Path:
    """Return the Whisper cache directory (respects WHISPER_CACHE_DIR env)."""
    env = os.environ.get("WHISPER_CACHE_DIR", "")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        return Path(base) / ".cache" / "whisper"
    return Path.home() / ".cache" / "whisper"


CACHE_DIR = _cache_dir()


# ── Model file lookup ──

def _model_filename(model_name: str, backend: str) -> str:
    """Map model_name → expected file on disk.

    openai-whisper saves as e.g. ``small.pt`` under the cache root.
    faster-whisper uses the CTranslate2-format directory structure:
    ``models--Systran--faster-whisper-small/`` inside the cache.
    """
    if backend == "openai":
        return f"{model_name}.pt"
    # faster-whisper: the directory is created by huggingface_hub
    return f"models--Systran--faster-whisper-{model_name}"


def is_model_cached(model_name: str, backend: str = "faster") -> bool:
    """Check whether a Whisper model exists in the local cache.

    Args:
        model_name: e.g. ``"small"``, ``"medium"``, ``"large-v3"``.
        backend: ``"faster"`` (faster-whisper) or ``"openai"`` (openai-whisper).

    Returns:
        True if the model file(s) exist on disk.
    """
    target = CACHE_DIR / _model_filename(model_name, backend)
    return target.exists()


# ── Model size estimates ──

_MODEL_SIZE = {
    "tiny":    "~150 MB",
    "base":    "~300 MB",
    "small":   "~1 GB",
    "medium":  "~3 GB",
    "large-v1": "~6 GB",
    "large-v2": "~6 GB",
    "large-v3": "~6 GB",
    "large":   "~6 GB",
}


def model_size_hint(model_name: str) -> str:
    return _MODEL_SIZE.get(model_name, "unknown")


# ── Download orchestrator ──

def ensure_model(
    model_name: str = "small",
    backend: str = "faster",
    device: str = "cpu",
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> Tuple[bool, Optional[Exception]]:
    """Ensure a Whisper model is downloaded and loadable.

    If the model is already cached, returns immediately.
    Otherwise triggers the upstream download and reports progress.

    Args:
        model_name: Model size / variant name.
        backend: ``"faster"`` (faster-whisper) or ``"openai"`` (openai-whisper).
        device: ``"cpu"`` or ``"cuda"``.
        on_progress: Optional ``(tag, msg)`` callback.

    Returns:
        (success, error) — True and None on success; False + Exception on failure.
    """
    if is_model_cached(model_name, backend):
        if on_progress:
            on_progress("模型加载", f"Whisper {model_name} 模型缓存已就绪")
        return True, None

    size_hint = model_size_hint(model_name)
    if on_progress:
        on_progress("模型下载", f"首次使用需下载 Whisper {model_name} 模型 ({size_hint})，请稍候…")

    try:
        _download_model(model_name, backend, device, on_progress)
    except Exception as exc:
        _log.error("Model download failed: %s", exc)
        if on_progress:
            on_progress("模型下载", f"下载失败: {exc}")
        return False, exc

    if on_progress:
        on_progress("模型加载", f"Whisper {model_name} 模型就绪")

    return True, None


def _download_model(
    model_name: str,
    backend: str,
    device: str,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Trigger the actual model download by loading it once.

    Both openai-whisper and faster-whisper download + cache automatically
    on first ``load_model()`` call.  This function forces that first load
    so that the caller can wrap it with progress reporting and error handling.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    size_hint = model_size_hint(model_name)

    if backend == "faster":
        from faster_whisper import WhisperModel
        compute = "int8"
        dev = "cuda" if device == "cuda" else "cpu"

        if on_progress:
            on_progress("模型下载", f"正在下载 faster-whisper {model_name} ({size_hint})…")
        # This triggers download via huggingface_hub on first call
        _model = WhisperModel(model_name, device=dev, compute_type=compute)
        del _model

    else:
        import whisper
        if on_progress:
            on_progress("模型下载", f"正在下载 openai-whisper {model_name} ({size_hint})…")
        # This triggers download via torch.hub on first call
        _model = whisper.load_model(model_name, device=device)
        del _model
