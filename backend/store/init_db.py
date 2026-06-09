#!/usr/bin/env python3
"""Database initialisation / migration script for transVideo JobStore.

Run once after deployment to bootstrap (or migrate) the SQLite
database for all store namespaces::

    python backend/store/init_db.py [--base-dir /path/to/project]

Without ``--base-dir`` the current working directory is used (which
is normally the project root when invoked from the repo).

What it does
------------
1. Opens (or creates) the SQLite database for each known namespace
   (``analysis``, ``export``).
2. Runs ``JobStore.__init__`` which auto-creates the schema and
   migrates legacy data (old two-table schema, JSON-per-file).
3. Prints a summary of existing jobs per namespace.

Safe to run repeatedly — the schema uses ``CREATE TABLE IF NOT EXISTS``
and migration is idempotent.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone


def _project_root() -> str:
    """Return the project root (one level above this script)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialise / migrate transVideo SQLite databases.",
    )
    parser.add_argument(
        "--base-dir",
        default=_project_root(),
        help="Project root directory (default: auto-detected).",
    )
    parser.add_argument(
        "--namespace",
        nargs="*",
        default=["analysis", "export"],
        help="Namespaces to init (default: analysis export).",
    )
    parser.add_argument(
        "--cleanup-old",
        type=float,
        default=0,
        help="If >0, delete jobs older than N hours after init.",
    )
    args = parser.parse_args()

    base_dir = os.path.abspath(args.base_dir)
    if not os.path.isdir(base_dir):
        print(f"ERROR: base-dir does not exist: {base_dir}", file=sys.stderr)
        sys.exit(1)

    # Ensure backend is importable
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    from backend.store.job_store import JobStore

    print(f"Base dir : {base_dir}")
    print(f"Time     : {datetime.now(timezone.utc).isoformat()}")
    print()

    for ns in args.namespace:
        store_path = os.path.join(base_dir, "job_store", f"{ns}.db")
        existed = os.path.exists(store_path)
        label = "(migrated)" if existed else "(new)"

        store = JobStore(ns, base_dir=base_dir)

        all_jobs = store.list_jobs(limit=10_000)
        by_status: dict[str, int] = {}
        for j in all_jobs:
            s = j.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1

        stale = store.list_stale()

        print(f"  {ns}.db {label}")
        print(f"    Total jobs : {len(all_jobs)}")
        for s, c in sorted(by_status.items()):
            print(f"      {s:12s} : {c}")
        if stale:
            print(f"    Stale (recoverable) : {len(stale)}")
        print()

        if args.cleanup_old > 0:
            removed = store.cleanup_old(max_age_hours=args.cleanup_old)
            if removed:
                print(f"    Cleaned up {removed} old job(s)")
                print()

        store.close()

    print("Done — all namespaces initialised successfully.")


if __name__ == "__main__":
    main()
