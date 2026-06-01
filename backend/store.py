"""JobStore: SQLite-backed persistence for background task state.

Replaces JSON-per-file storage with sqlite3 (Python stdlib, zero
external dependencies).  WAL mode for concurrent reads; thread-safe
via per-instance lock.  Migration: first init imports legacy JSON
files then renames them to .json.bak.

Checkpoint stages for pipeline resume:
    frame_diff → scene_detect → audio_transcribe → audio_analysis
    → visual_features → structure → script_build
"""

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional


# ── Checkpoint stage identifiers (ordered) ──

STAGE_FRAME_DIFF = "frame_diff"
STAGE_SCENE_DETECT = "scene_detect"
STAGE_AUDIO_TRANSCRIBE = "audio_transcribe"
STAGE_AUDIO_ANALYSIS = "audio_analysis"
STAGE_VISUAL_FEATURES = "visual_features"
STAGE_STRUCTURE = "structure"
STAGE_SCRIPT_BUILD = "script_build"

CHECKPOINT_STAGES: List[str] = [
    STAGE_FRAME_DIFF,
    STAGE_SCENE_DETECT,
    STAGE_AUDIO_TRANSCRIBE,
    STAGE_AUDIO_ANALYSIS,
    STAGE_VISUAL_FEATURES,
    STAGE_STRUCTURE,
    STAGE_SCRIPT_BUILD,
]


# ── VisionConfig: persisted vision provider settings ──

DEFAULT_VISION_CONFIG: Dict[str, Any] = {
    "provider": "local",       # "local" | "api"
    "api_url": "",
    "api_key": "",
    "model": "qwen-vl-max",
}

_VISION_CONFIG_PATH: str = ""


def _ensure_config_path(base_dir: str = "") -> str:
    global _VISION_CONFIG_PATH
    if not _VISION_CONFIG_PATH:
        _VISION_CONFIG_PATH = os.path.join(
            base_dir or os.getcwd(), "job_store", "vision_config.json"
        )
    return _VISION_CONFIG_PATH


def load_vision_config(base_dir: str = "") -> Dict[str, Any]:
    """Load vision config from disk, falling back to defaults."""
    path = _ensure_config_path(base_dir)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data: dict = json.load(f)
                merged = dict(DEFAULT_VISION_CONFIG)
                merged.update(data)
                return merged
    except (json.JSONDecodeError, OSError):
        pass
    return dict(DEFAULT_VISION_CONFIG)


def save_vision_config(config: Dict[str, Any], base_dir: str = "") -> Dict[str, Any]:
    """Validate and persist vision config to disk."""
    merged = dict(DEFAULT_VISION_CONFIG)
    merged.update(config)
    if merged["provider"] not in ("local", "api"):
        merged["provider"] = "local"
    path = _ensure_config_path(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    return merged


# ═══════════════════════════════════════════════════════
#  SQLite schema
# ═══════════════════════════════════════════════════════

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'unknown',
    video_path  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS job_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL,
    data_json   TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_job_data_job_id ON job_data(job_id);
CREATE INDEX IF NOT EXISTS idx_job_data_created ON job_data(job_id, created_at DESC);
"""


class JobStore:
    """Dict-like key-value store backed by SQLite.

    Each ``namespace`` maps to a separate .db file under
    ``{base_dir}/job_store/``.  Public API is unchanged from
    the previous JSON-file implementation — all callers work
    without modification.

    Thread-safe for use with FastAPI BackgroundTasks.

    Usage::

        jobs = JobStore("analysis", base_dir="/var/transvideo")
        jobs["abc123"] = {"status": "processing"}
        status = jobs.get("abc123")  # {"status": "processing"}
    """

    def __init__(self, namespace: str, base_dir: str = "") -> None:
        self._namespace = namespace
        self._base_dir = base_dir or os.getcwd()
        self._store_root = os.path.join(self._base_dir, "job_store")
        self._db_path = os.path.join(self._store_root, f"{namespace}.db")
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

        os.makedirs(self._store_root, exist_ok=True)

        # Open connection (check_same_thread=False required for
        # cross-thread access from FastAPI BackgroundTasks).
        self._conn = sqlite3.connect(
            self._db_path, check_same_thread=False,
            isolation_level=None,  # autocommit mode
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)

        # ── One-shot migration: import legacy JSON files ──
        self._migrate_json_files()

    # ── JSON → SQLite migration ──

    def _migrate_json_files(self) -> None:
        """On first startup after upgrade, scan for legacy .json job files,
        import them into SQLite, then rename them to .json.bak."""
        legacy_dir = os.path.join(self._store_root, self._namespace)
        if not os.path.isdir(legacy_dir):
            return

        json_files = sorted(
            f for f in os.listdir(legacy_dir)
            if f.endswith(".json") and not f.endswith(".json.bak")
        )
        if not json_files:
            return

        imported = 0
        for filename in json_files:
            path = os.path.join(legacy_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data: dict = json.load(fh)
            except (json.JSONDecodeError, OSError):
                # Corrupt file — skip, don't crash
                continue

            # video_id from filename: "{video_id}.json"
            video_id = filename[:-5]  # strip ".json"
            if not video_id:
                continue

            status = data.get("status", "unknown")

            self._conn.execute(
                "INSERT OR REPLACE INTO jobs (id, status, updated_at) "
                "VALUES (?, ?, datetime('now'))",
                (video_id, status),
            )
            self._conn.execute(
                "INSERT INTO job_data (job_id, data_json) VALUES (?, ?)",
                (video_id, json.dumps(data, ensure_ascii=False, default=str)),
            )

            # Backup original file
            bak_path = path + ".bak"
            try:
                os.rename(path, bak_path)
            except OSError:
                pass  # best-effort rename

            imported += 1

        if imported:
            # Commit after all imports complete
            self._conn.commit()

    # ── I/O ──

    def _read(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Read job from SQLite, assembling status + data_json."""
        row = self._conn.execute(
            "SELECT status FROM jobs WHERE id = ?", (video_id,)
        ).fetchone()
        if row is None:
            return None

        data_row = self._conn.execute(
            "SELECT data_json FROM job_data "
            "WHERE job_id = ? ORDER BY created_at DESC LIMIT 1",
            (video_id,),
        ).fetchone()

        if data_row is None:
            return {"status": row["status"]}

        try:
            data = json.loads(data_row["data_json"])
        except json.JSONDecodeError:
            data = {}
        data["status"] = row["status"]
        return data

    def _write(self, video_id: str, data: Dict[str, Any]) -> None:
        """Write job data to SQLite (status → jobs, full blob → job_data)."""
        status = data.get("status", "unknown")
        self._conn.execute(
            "INSERT OR REPLACE INTO jobs (id, status, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (video_id, status),
        )
        self._conn.execute(
            "INSERT INTO job_data (job_id, data_json) VALUES (?, ?)",
            (video_id, json.dumps(data, ensure_ascii=False, default=str)),
        )

    def _delete_row(self, video_id: str) -> None:
        """Delete job from SQLite (CASCADE deletes job_data rows)."""
        self._conn.execute("DELETE FROM jobs WHERE id = ?", (video_id,))

    # ── dict interface ──

    def save(self, video_id: str, data: Dict[str, Any]) -> None:
        """Persist job data to SQLite and cache."""
        with self._lock:
            self._cache[video_id] = data
            self._write(video_id, data)

    def load(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Load job data (cache-first, then SQLite)."""
        with self._lock:
            if video_id in self._cache:
                return self._cache[video_id]
            data = self._read(video_id)
            if data is not None:
                self._cache[video_id] = data
            return data

    def delete(self, video_id: str) -> None:
        """Remove job from cache and SQLite."""
        with self._lock:
            self._cache.pop(video_id, None)
            self._delete_row(video_id)

    # ── Checkpoint (pipeline resume) ──

    def update_checkpoint(self, video_id: str, stage: str) -> Dict[str, Any]:
        """Mark a pipeline stage as completed for the given job.

        Args:
            video_id: Job / video identifier.
            stage: Stage name from CHECKPOINT_STAGES.

        Returns:
            The updated checkpoint dict.
        """
        with self._lock:
            job = self._read(video_id) or {}
            cp: dict = job.get("pipeline_checkpoint", {})
            completed: list = cp.get("completed_stages", [])
            if stage not in completed:
                completed.append(stage)
            cp["completed_stages"] = completed
            cp["last_updated"] = round(time.time(), 2)
            job["pipeline_checkpoint"] = cp
            self._write(video_id, job)
            self._cache[video_id] = job
        return cp

    def get_checkpoint(self, video_id: str) -> Dict[str, Any]:
        """Return current pipeline checkpoint for a job.

        Returns:
            Dict with keys: completed_stages (list), last_updated (float).
            Empty checkpoint if job or field doesn't exist.
        """
        job = self.load(video_id) or {}
        return job.get("pipeline_checkpoint", {
            "completed_stages": [],
            "last_updated": 0.0,
        })

    # ── Artifact I/O (large intermediate data, JSON files on disk) ──

    def _artifact_dir(self, video_id: str) -> str:
        return os.path.join(self._store_root, "artifacts", video_id)

    def save_artifact(self, video_id: str, name: str, data: Any) -> str:
        """Persist an intermediate pipeline artifact to a JSON file.

        Args:
            video_id: Job / video identifier.
            name: Artifact name (e.g. ``"frame_diff"``, ``"audio_data"``).
            data: JSON-serialisable data.

        Returns:
            Path to the artifact file.
        """
        d = self._artifact_dir(video_id)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{name}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp, path)
        return path

    def load_artifact(self, video_id: str, name: str) -> Optional[Any]:
        """Read a previously-saved pipeline artifact.

        Args:
            video_id: Job / video identifier.
            name: Artifact name.

        Returns:
            Deserialized data, or None if missing / corrupt.
        """
        path = os.path.join(self._artifact_dir(video_id), f"{name}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def close(self) -> None:
        """Close the underlying SQLite connection.

        Optional; the OS will close it on process exit.  Call this
        only when you're sure no more operations will be performed.
        """
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.ProgrammingError:
                pass  # already closed

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
