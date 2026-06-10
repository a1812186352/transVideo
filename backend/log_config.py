"""Centralized logging configuration with rotating file handler.

Call ``setup_logging()`` once at application startup (from ``main.py``)
to enable both console and file-based logging with rotation.

Log directory: ``{project_root}/logs/``
Rotation: 10 MB per file, keep 5 backups.
"""

import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def setup_logging(
    log_dir: Optional[str] = None,
    level: int = logging.INFO,
    console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> str:
    """Configure root logger with rotating file handler + optional console.

    Args:
        log_dir: Directory for log files. Defaults to ``{project_root}/logs/``.
        level: Logging level (default ``logging.INFO``).
        console: Whether to also log to stderr (default True).
        max_bytes: Max size per log file before rotation (default 10 MB).
        backup_count: Number of rotated backups to keep (default 5).

    Returns:
        Path to the active log file.
    """
    if log_dir is None:
        log_dir = _default_log_dir()

    os.makedirs(log_dir, exist_ok=True)

    # Determine the effective log file path
    log_file = os.path.join(log_dir, "transvideo.log")

    # Remove any pre-existing handlers on the root logger
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    # ── File handler with rotation (JSON structured format) ──
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(JsonFormatter())

    root.addHandler(file_handler)

    # ── Console handler (stderr) ──
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(_formatter(is_file=False))
        root.addHandler(console_handler)

    root.setLevel(level)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info(
        "Logging initialized — file=%s level=%s console=%s",
        log_file, logging.getLevelName(level), console,
    )
    return log_file


def _default_log_dir() -> str:
    """Resolve the project-root ``logs/`` directory."""
    # Walk up from this file's location until we find the project root
    # (signalled by the presence of backend/ and frontend/ dirs)
    here = Path(__file__).resolve().parent
    for parent in [here, here.parent, here.parent.parent]:
        if (parent / "backend").is_dir() and (parent / "frontend").is_dir():
            return str(parent / "logs")
    return str(here.parent / "logs")


def _formatter(is_file: bool = False) -> logging.Formatter:
    """Return an appropriate formatter.

    File format includes timestamp, logger name, level — suitable for
    post-mortem analysis.  Console format is more compact.
    """
    if is_file:
        fmt = (
            "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | "
            "%(message)s"
        )
        return logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        return logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )


class JsonFormatter(logging.Formatter):
    """Optional structured JSON formatter for machine-parsable logs."""

    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        # Inject structured fields from the adapter
        extras = getattr(record, "structured_fields", None)
        if extras:
            obj.update(extras)
        if record.exc_info and record.exc_info[0]:
            obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


class StructuredLogger:
    """Logger adapter that injects structured context into every log call.

    Usage::

        log = StructuredLogger(__name__, video_id="abc123", stage="signal")
        log.info("Frame diff complete", n_frames=2100, elapsed_ms=3450)
        # → JSON log includes:
        #   {"video_id": "abc123", "stage": "signal",
        #    "n_frames": 2100, "elapsed_ms": 3450, ...}

    The structured fields are persisted across calls.  Use ``with_stage()``,
    ``elapsed()``, or ``child(**fields)`` to create derivative loggers.
    """

    def __init__(
        self,
        name: str,
        level: int = logging.INFO,
        **extra: Any,
    ) -> None:
        self._name = name
        self._level = level
        self._extra: Dict[str, Any] = dict(extra)
        self._start = time.time()

    def _log(self, level: int, msg: str, **fields: Any) -> None:
        logger = logging.getLogger(self._name)
        record = logger.makeRecord(
            self._name, level, "", 0, msg, (), None,
        )
        structured = dict(self._extra)
        structured.update(fields)
        record.structured_fields = structured
        logger.handle(record)

    def debug(self, msg: str, **kw: Any) -> None:
        self._log(logging.DEBUG, msg, **kw)

    def info(self, msg: str, **kw: Any) -> None:
        self._log(logging.INFO, msg, **kw)

    def warning(self, msg: str, **kw: Any) -> None:
        self._log(logging.WARNING, msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._log(logging.ERROR, msg, **kw)

    def exception(self, msg: str, **kw: Any) -> None:
        self._log(logging.ERROR, msg, exc_info=True, **kw)

    def elapsed(self) -> Dict[str, float]:
        """Return elapsed_ms since this logger was created."""
        return {"elapsed_ms": round((time.time() - self._start) * 1000, 1)}

    def with_stage(self, stage: str) -> "StructuredLogger":
        """Return a new logger with the given stage (preserving other fields)."""
        return StructuredLogger(self._name, self._level,
                                **{**self._extra, "stage": stage})

    def child(self, **fields: Any) -> "StructuredLogger":
        """Return a new logger with additional structured fields."""
        return StructuredLogger(self._name, self._level,
                                **{**self._extra, **fields})
