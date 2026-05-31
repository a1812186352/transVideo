"""JobStore: file-level JSON persistence for background task state.

Replaces in-memory dicts so analysis/export jobs survive process restarts.
Zero external dependencies — uses only stdlib json + os.
"""

import json
import os
import threading
from typing import Any, Dict, Optional


class JobStore:
    """Dict-like key-value store backed by per-key JSON files.

    Each video_id gets its own .json file under ``{base_dir}/{namespace}/``.
    Reads first check an in-memory cache; writes flush to cache + disk
    with a cross-thread lock.

    Thread-safe for use with FastAPI BackgroundTasks (no async needed — all
    I/O is synchronous and short).

    Usage::

        jobs = JobStore("analysis", base_dir="/var/transvideo")
        jobs["abc123"] = {"status": "processing"}
        status = jobs.get("abc123")  # {"status": "processing"}
    """

    def __init__(self, namespace: str, base_dir: str = "") -> None:
        self._namespace = namespace
        self._base_dir = base_dir or os.getcwd()
        self._store_dir = os.path.join(self._base_dir, "job_store", namespace)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        os.makedirs(self._store_dir, exist_ok=True)

    # ── file paths ──

    def _filepath(self, video_id: str) -> str:
        # Sanitise video_id to prevent path traversal
        safe_id = video_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return os.path.join(self._store_dir, f"{safe_id}.json")

    # ── I/O ──

    def _read(self, video_id: str) -> Optional[Dict[str, Any]]:
        path = self._filepath(video_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _write(self, video_id: str, data: Dict[str, Any]) -> None:
        path = self._filepath(video_id)
        # Atomic-ish: write to temp, then rename
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp, path)

    def _delete_file(self, video_id: str) -> None:
        path = self._filepath(video_id)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    # ── dict interface ──

    def save(self, video_id: str, data: Dict[str, Any]) -> None:
        """Persist job data to disk and cache."""
        with self._lock:
            self._cache[video_id] = data
            self._write(video_id, data)

    def load(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Load job data (cache-first, then disk)."""
        with self._lock:
            if video_id in self._cache:
                return self._cache[video_id]
            data = self._read(video_id)
            if data is not None:
                self._cache[video_id] = data
            return data

    def delete(self, video_id: str) -> None:
        """Remove job from cache and disk."""
        with self._lock:
            self._cache.pop(video_id, None)
            self._delete_file(video_id)

    def get(self, video_id: str, default: Any = None) -> Any:
        data = self.load(video_id)
        return data if data is not None else default

    def __getitem__(self, video_id: str) -> Dict[str, Any]:
        data = self.load(video_id)
        if data is None:
            raise KeyError(video_id)
        return data

    def __setitem__(self, video_id: str, data: Dict[str, Any]) -> None:
        self.save(video_id, data)

    def __contains__(self, video_id: str) -> bool:
        return self.load(video_id) is not None

    def __delitem__(self, video_id: str) -> None:
        if video_id not in self:
            raise KeyError(video_id)
        self.delete(video_id)
