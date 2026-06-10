"""JobStore: SQLite-backed persistence for background task state.

Single-table schema with progress throttling, stale-job recovery,
and automatic cleanup of old tasks.

Schema
------
jobs (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL DEFAULT 'analysis',
    status      TEXT NOT NULL DEFAULT 'pending',
    input_path  TEXT NOT NULL DEFAULT '',
    progress    REAL NOT NULL DEFAULT 0.0,
    result      TEXT NOT NULL DEFAULT '{}',
    error       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
)

Progress writes are throttled to once every 2 s per job.  Stale
jobs (status in ``pending`` / ``processing`` / ``queued``) are
recoverable after a process restart.
"""

from __future__ import annotations

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

# ── Stale statuses — jobs that may need recovery after restart ──

STALE_STATUSES = {"pending", "processing", "queued"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

# ── Progress write throttle (seconds) ──

PROGRESS_THROTTLE_SEC = 2.0

# ── Cleanup default (hours) ──

DEFAULT_CLEANUP_AGE_HOURS = 24




# ═══════════════════════════════════════════════════════════════════
#  SQLite schema (new: single-table design)
# ═══════════════════════════════════════════════════════════════════

_NEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL DEFAULT 'analysis',
    status      TEXT NOT NULL DEFAULT 'pending',
    input_path  TEXT NOT NULL DEFAULT '',
    progress    REAL NOT NULL DEFAULT 0.0,
    result      TEXT NOT NULL DEFAULT '{}',
    error       TEXT,
    heartbeat_at TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(type);
CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at);
CREATE INDEX IF NOT EXISTS idx_jobs_heartbeat ON jobs(heartbeat_at);
"""

# ── Heartbeat decay (seconds) — a job whose heartbeat is older than
#     this threshold is considered stale regardless of status.
HEARTBEAT_STALE_SEC = 90.0

# ── Old schema (for auto-migration) ──

_OLD_SCHEMA_HINT = "video_path"  # column only in old schema


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check whether *column* exists in *table*."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


class JobStore:
    """SQLite-backed job store with progress throttling.

    Replaces the legacy dict + JSON-file implementation.  Public
    API includes both a dict-like interface for backward
    compatibility and named methods (``create_job``, ``get_job``,
    ``update_progress``, ``list_jobs``, ``cleanup_old``).

    Thread-safe — suitable for FastAPI ``BackgroundTasks``.

    Usage::

        store = JobStore("analysis", base_dir="/var/transvideo")

        # New API
        store.create_job("abc123", type="analysis", input_path="/v/abc.mp4")
        store.update_progress("abc123", 0.5)
        job = store.get_job("abc123")

        # Dict-compat API
        store["abc123"] = {"status": "completed", "result": {...}}
        data = store.get("abc123")
    """

    # ── Initialisation ─────────────────────────────────────────────

    def __init__(self, namespace: str, base_dir: str = "") -> None:
        self._namespace = namespace
        self._base_dir = base_dir or os.getcwd()
        self._store_root = os.path.join(self._base_dir, "job_store")
        self._db_path = os.path.join(self._store_root, f"{namespace}.db")

        # In-memory cache: job_id → row dict
        self._cache: Dict[str, Dict[str, Any]] = {}
        # Progress throttle: job_id → last SQLite write timestamp (monotonic)
        self._progress_last_write: Dict[str, float] = {}
        self._lock = threading.Lock()

        os.makedirs(self._store_root, exist_ok=True)

        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        # ── Schema bootstrap + migration ──
        self._init_schema()

        # ── Import legacy JSON files (pre-SQLite era) ──
        self._migrate_json_files()

    def _init_schema(self) -> None:
        """Create new schema; if old schema detected, migrate in-place.

        Also adds missing columns on existing DBs (e.g. heartbeat_at).
        """
        # Check if jobs table already exists
        existing = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        ).fetchone()

        if existing is None:
            # Fresh DB — create new schema directly
            self._conn.executescript(_NEW_SCHEMA)
            return

        # Table exists — check whether it has the old or new shape
        if _table_has_column(self._conn, "jobs", "video_path"):
            # Old schema detected → migrate
            self._migrate_old_schema()
        elif not _table_has_column(self._conn, "jobs", "type"):
            # Partial / corrupt — rebuild
            self._conn.execute("DROP TABLE IF EXISTS jobs")
            self._conn.execute("DROP TABLE IF EXISTS job_data")
            self._conn.executescript(_NEW_SCHEMA)

        # ── Add missing columns (safe to repeat) ──
        if not _table_has_column(self._conn, "jobs", "heartbeat_at"):
            try:
                self._conn.execute(
                    "ALTER TABLE jobs ADD COLUMN heartbeat_at TEXT"
                )
            except sqlite3.OperationalError:
                pass  # column already exists (race)

    def _migrate_old_schema(self) -> None:
        """Migrate from old two-table schema to new single-table schema.

        Old:  jobs(id, status, video_path, created_at, updated_at)
              job_data(id, job_id, data_json, created_at)
        New:  jobs(id, type, status, input_path, progress, result,
                   error, created_at, updated_at)
        """
        # 1. Read all old data
        old_jobs = {}
        try:
            rows = self._conn.execute("SELECT id, status, video_path, created_at, updated_at FROM jobs").fetchall()
            for r in rows:
                old_jobs[r["id"]] = {
                    "status": r["status"],
                    "input_path": r["video_path"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
        except sqlite3.OperationalError:
            pass

        # 2. Read latest job_data for each job
        try:
            data_rows = self._conn.execute(
                "SELECT job_id, data_json FROM job_data "
                "WHERE id IN (SELECT MAX(id) FROM job_data GROUP BY job_id)"
            ).fetchall()
            for dr in data_rows:
                jid = dr["job_id"]
                if jid in old_jobs:
                    try:
                        extra = json.loads(dr["data_json"])
                    except json.JSONDecodeError:
                        extra = {}
                    old_jobs[jid].update(extra)
        except sqlite3.OperationalError:
            pass

        # 3. Drop old tables
        self._conn.execute("DROP TABLE IF EXISTS job_data")
        self._conn.execute("DROP TABLE IF EXISTS jobs")

        # 4. Create new schema
        self._conn.executescript(_NEW_SCHEMA)

        # 5. Insert migrated data
        for jid, data in old_jobs.items():
            status = data.get("status", "unknown")
            input_path = data.get("input_path", "")
            progress = float(data.get("progress", 0.0))
            error = data.get("error")
            created_at = data.get("created_at") or "datetime('now')"
            updated_at = data.get("updated_at") or "datetime('now')"

            result = json.dumps(
                {k: v for k, v in data.items()
                 if k not in ("status", "type", "input_path", "progress",
                              "result", "error", "created_at", "updated_at")},
                ensure_ascii=False,
                default=str,
            )

            try:
                self._conn.execute(
                    "INSERT INTO jobs (id, type, status, input_path, progress, "
                    "result, error, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (jid, "analysis", status, input_path, progress,
                     result, error, created_at, updated_at),
                )
            except sqlite3.IntegrityError:
                pass  # duplicate key — skip

    # ── Legacy JSON → SQLite migration ─────────────────────────────

    def _migrate_json_files(self) -> None:
        """On first startup after upgrade from JSON era, import legacy
        .json job files, insert into SQLite, rename to .json.bak."""
        legacy_dir = os.path.join(self._store_root, self._namespace)
        if not os.path.isdir(legacy_dir):
            return

        json_files = sorted(
            f for f in os.listdir(legacy_dir)
            if f.endswith(".json") and not f.endswith(".json.bak")
        )
        if not json_files:
            return

        for filename in json_files:
            path = os.path.join(legacy_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data: dict = json.load(fh)
            except (json.JSONDecodeError, OSError):
                continue

            video_id = filename[:-5]  # strip ".json"
            if not video_id:
                continue

            self.create_job(
                job_id=video_id,
                type=data.get("type", "analysis"),
                input_path=data.get("input_path", ""),
                status=data.get("status", "unknown"),
            )

            # Copy extra fields into result
            extra = {
                k: v for k, v in data.items()
                if k not in ("id", "type", "status", "input_path",
                             "progress", "result", "error")
            }
            if extra:
                self._conn.execute(
                    "UPDATE jobs SET result = ? WHERE id = ?",
                    (json.dumps(extra, ensure_ascii=False, default=str), video_id),
                )

            # Backup original
            try:
                os.rename(path, path + ".bak")
            except OSError:
                pass

    # ── Public API (new methods) ───────────────────────────────────

    def create_job(
        self,
        job_id: str,
        type: str = "analysis",
        input_path: str = "",
        status: str = "pending",
        progress: float = 0.0,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert a new job record.

        Args:
            job_id: Unique job identifier (usually a video_id).
            type: Job type — ``"analysis"``, ``"export"``, etc.
            input_path: Path to the input file.
            status: Initial status (default ``"pending"``).
            progress: Initial progress 0.0–1.0.
            result: Optional result dict (serialised to JSON).
        """
        result_json = json.dumps(result or {}, ensure_ascii=False, default=str)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO jobs "
                "(id, type, status, input_path, progress, result) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, type, status, input_path, progress, result_json),
            )

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return a job record as a dict, or ``None``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_dict(row)

    def update_progress(self, job_id: str, progress: float) -> None:
        """Update job progress (0.0–1.0), throttled to ≤1 write / 2 s.

        Writes to the in-memory cache immediately for fast reads;
        the SQLite ``progress`` column is only flushed when ≥2 s
        have elapsed since the last write for this job.
        """
        progress = max(0.0, min(1.0, float(progress)))
        now = time.monotonic()

        with self._lock:
            # Always update cache
            if job_id in self._cache:
                self._cache[job_id]["progress"] = progress
                self._cache[job_id]["updated_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%S", time.gmtime()
                )

            last = self._progress_last_write.get(job_id, 0.0)
            if now - last < PROGRESS_THROTTLE_SEC:
                return  # throttled

            self._progress_last_write[job_id] = now
            self._conn.execute(
                "UPDATE jobs SET progress = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (progress, job_id),
            )

    def set_status(self, job_id: str, status: str, error: Optional[str] = None) -> None:
        """Atomically update job status and optional error message.

        Args:
            job_id: Job identifier.
            status: New status (``"processing"``, ``"completed"``,
                    ``"failed"``, ``"cancelled"``).
            error: Error message when status is ``"failed"``.
        """
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status = ?, error = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (status, error, job_id),
            )
            # Invalidate cache so next read hits DB
            self._cache.pop(job_id, None)

    def set_result(self, job_id: str, result: Dict[str, Any]) -> None:
        """Store a complete result dict, mark job completed."""
        result_json = json.dumps(result, ensure_ascii=False, default=str)
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status = 'completed', result = ?, "
                "progress = 1.0, updated_at = datetime('now') WHERE id = ?",
                (result_json, job_id),
            )
            self._cache.pop(job_id, None)

    def set_error(self, job_id: str, error: str) -> None:
        """Record an error and mark the job as failed."""
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status = 'failed', error = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (error, job_id),
            )
            self._cache.pop(job_id, None)

    def list_jobs(
        self,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List jobs with optional filters.

        Args:
            status: Filter by status (``"processing"``, ``"completed"``, etc.).
            job_type: Filter by type (``"analysis"``, ``"export"``, etc.).
            limit: Max number of results.
            offset: Pagination offset.

        Returns:
            List of job dicts, most-recently-updated first.
        """
        clauses = []
        params: List[Any] = []

        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if job_type is not None:
            clauses.append("type = ?")
            params.append(job_type)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])

        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM jobs {where} "
                "ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def update_heartbeat(self, job_id: str) -> None:
        """Touch the heartbeat timestamp for a running job.

        Should be called periodically (every 15-30 s) during long-running
        tasks so that ``list_stale()`` can distinguish "running" from
        "crashed".
        """
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET heartbeat_at = datetime('now') WHERE id = ?",
                (job_id,),
            )

    def list_stale(self) -> List[Dict[str, Any]]:
        """Return jobs that may need recovery after a process restart.

        A job is stale when:
        - Its status is in ``STALE_STATUSES`` (``pending`` / ``processing`` /
          ``queued``) **AND** either:
          - ``heartbeat_at`` is ``NULL`` (never beat — legacy),
          - ``heartbeat_at`` is older than ``HEARTBEAT_STALE_SEC`` (90 s).

        This prevents false-positives on genuinely running jobs that
        just haven't written a terminal status yet.

        Each returned dict includes an extra ``stale_age_seconds``
        field (time since ``updated_at``).
        """
        now_ts = time.time()
        placeholders = ",".join("?" * len(STALE_STATUSES))
        with self._lock:
            # Jobs in stale status AND (heartbeat is NULL OR heartbeat is expired)
            rows = self._conn.execute(
                f"SELECT * FROM jobs WHERE status IN ({placeholders}) "
                "AND (heartbeat_at IS NULL OR "
                f"  strftime('%%s','now') - strftime('%%s', heartbeat_at) > {int(HEARTBEAT_STALE_SEC)}) "
                "ORDER BY updated_at ASC",
                list(STALE_STATUSES),
            ).fetchall()
            result = []
            for r in rows:
                d = self._row_to_dict(r)
                # Compute stale age from updated_at (stored in UTC)
                try:
                    updated = r["updated_at"]
                    parsed = time.strptime(updated, "%Y-%m-%d %H:%M:%S")
                    import calendar
                    updated_epoch = calendar.timegm(parsed)
                    d["stale_age_seconds"] = round(now_ts - updated_epoch, 1)
                except (ValueError, OSError):
                    d["stale_age_seconds"] = -1.0
                result.append(d)
            return result

    def reset_stale_to_failed(self) -> int:
        """Mark all stale jobs as ``failed`` (for namespaces that
        cannot auto-resume, e.g. export / rendering).

        Returns:
            Number of jobs updated.
        """
        placeholders = ",".join("?" * len(STALE_STATUSES))
        with self._lock:
            cursor = self._conn.execute(
                f"UPDATE jobs SET status = 'failed', "
                f"error = 'Process restarted — job was stale', "
                f"updated_at = datetime('now') "
                f"WHERE status IN ({placeholders})",
                list(STALE_STATUSES),
            )
            count = cursor.rowcount
            # Invalidate cache
            self._cache.clear()
            return count

    def count_by_status(self) -> Dict[str, int]:
        """Return a histogram of job counts by status."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM jobs GROUP BY status"
            ).fetchall()
            return {r["status"]: r["cnt"] for r in rows}

    def list_active(self) -> List[Dict[str, Any]]:
        """Return jobs that are running and have a recent heartbeat.

        These are truly live jobs (status processing/queued + heartbeat
        within ``HEARTBEAT_STALE_SEC``) — not stale, not dead.
        """
        placeholders = ",".join("?" * len(STALE_STATUSES))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM jobs WHERE status IN ({placeholders}) "
                "AND heartbeat_at IS NOT NULL "
                f"AND strftime('%%s','now') - strftime('%%s', heartbeat_at) <= {int(HEARTBEAT_STALE_SEC)} "
                "ORDER BY heartbeat_at DESC",
                list(STALE_STATUSES),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def cleanup_old(self, max_age_hours: float = DEFAULT_CLEANUP_AGE_HOURS) -> int:
        """Delete jobs older than *max_age_hours* and their temp files.

        Also removes associated artifacts and uploaded input files.

        Returns:
            Number of deleted job records.
        """
        cutoff = time.time() - max_age_hours * 3600
        cutoff_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(cutoff))

        # ── Collect IDs before deletion ──
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, input_path FROM jobs WHERE updated_at < ?",
                (cutoff_str,),
            ).fetchall()
            ids_to_delete = [r["id"] for r in rows]
            input_paths = [r["input_path"] for r in rows]

            if ids_to_delete:
                placeholders = ",".join("?" * len(ids_to_delete))
                self._conn.execute(
                    f"DELETE FROM jobs WHERE id IN ({placeholders})",
                    ids_to_delete,
                )
                # Purge from cache
                for jid in ids_to_delete:
                    self._cache.pop(jid, None)
                    self._progress_last_write.pop(jid, None)

        # ── Clean up files on disk (outside lock) ──
        for path in input_paths:
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

        # Remove artifact dirs for cleaned-up jobs
        for jid in ids_to_delete:
            artifact_dir = os.path.join(self._store_root, "artifacts", jid)
            if os.path.isdir(artifact_dir):
                import shutil
                try:
                    shutil.rmtree(artifact_dir, ignore_errors=True)
                except Exception:
                    pass

        return len(ids_to_delete)

    # ── Dict-like backward-compat interface ────────────────────────

    def save(self, video_id: str, data: Dict[str, Any]) -> None:
        """Persist job data (dict-compat)."""
        with self._lock:
            self._cache[video_id] = data
            status = data.get("status", "unknown")
            input_path = data.get("input_path", "")
            progress = float(data.get("progress", 0.0))
            error = data.get("error")
            job_type = data.get("type", "analysis")

            result = json.dumps(
                {k: v for k, v in data.items()
                 if k not in ("id", "type", "status", "input_path",
                              "progress", "result", "error",
                              "created_at", "updated_at")},
                ensure_ascii=False,
                default=str,
            )

            self._conn.execute(
                "INSERT OR REPLACE INTO jobs "
                "(id, type, status, input_path, progress, result, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (video_id, job_type, status, input_path, progress, result, error),
            )

    def load(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Load job data (cache-first, then SQLite)."""
        with self._lock:
            if video_id in self._cache:
                return self._cache[video_id]
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (video_id,)
            ).fetchone()
            if row is None:
                return None
            data = self._row_to_dict(row)
            self._cache[video_id] = data
            return data

    def delete(self, video_id: str) -> None:
        """Remove job from cache and SQLite."""
        with self._lock:
            self._cache.pop(video_id, None)
            self._progress_last_write.pop(video_id, None)
            self._conn.execute("DELETE FROM jobs WHERE id = ?", (video_id,))

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

    # ── Checkpoint (pipeline resume) ───────────────────────────────

    def update_checkpoint(self, video_id: str, stage: str) -> Dict[str, Any]:
        """Mark a pipeline stage as completed for the given job.

        Returns:
            The updated checkpoint dict.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (video_id,)
            ).fetchone()
            job = self._row_to_dict(row) if row is not None else {}
            result_raw = job.get("result", "{}")
            try:
                result_data = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
            except json.JSONDecodeError:
                result_data = {}
            cp: dict = result_data.get("pipeline_checkpoint", {})
            completed: list = cp.get("completed_stages", [])
            if stage not in completed:
                completed.append(stage)
            cp["completed_stages"] = completed
            cp["last_updated"] = round(time.time(), 2)
            result_data["pipeline_checkpoint"] = cp
            self._conn.execute(
                "UPDATE jobs SET result = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (json.dumps(result_data, ensure_ascii=False, default=str), video_id),
            )
            self._cache.pop(video_id, None)
        return cp

    def get_checkpoint(self, video_id: str) -> Dict[str, Any]:
        """Return current pipeline checkpoint for a job."""
        job = self.load(video_id) or {}
        result_raw = job.get("result", "{}")
        try:
            result_data = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
        except json.JSONDecodeError:
            result_data = {}
        return result_data.get("pipeline_checkpoint", {
            "completed_stages": [],
            "last_updated": 0.0,
        })

    # ── Artifact I/O ───────────────────────────────────────────────

    def _artifact_dir(self, video_id: str) -> str:
        return os.path.join(self._store_root, "artifacts", video_id)

    def save_artifact(self, video_id: str, name: str, data: Any) -> str:
        """Persist an intermediate pipeline artifact to a JSON file.

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
        """Close the underlying SQLite connection."""
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.ProgrammingError:
                pass

    # ── Helpers ────────────────────────────────────────────────────

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a sqlite3.Row to a plain dict, parsing ``result`` JSON."""
        d = dict(row)
        # Parse result JSON if present
        result_raw = d.get("result", "{}")
        try:
            if isinstance(result_raw, str):
                d["result"] = json.loads(result_raw)
        except json.JSONDecodeError:
            d["result"] = {}
        return d
