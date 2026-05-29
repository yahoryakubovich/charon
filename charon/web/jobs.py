"""Job manager: run copy tasks in background threads, persist state to SQLite."""

from __future__ import annotations

import queue
import sqlite3
import threading
import uuid
from collections.abc import Callable, Generator
from datetime import UTC, datetime
from pathlib import Path

from .models import JobStatus, JobSummary

_DB_PATH = Path.home() / ".charon" / "jobs.db"

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    profile      TEXT NOT NULL,
    table_name   TEXT,
    status       TEXT NOT NULL DEFAULT 'queued',
    started_at   TEXT,
    finished_at  TEXT,
    log          TEXT NOT NULL DEFAULT ''
);
"""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class JobManager:
    """Thread-safe job manager backed by SQLite."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(_DDL)
        self._conn.commit()
        # in-memory log queues for live streaming
        self._queues: dict[str, queue.SimpleQueue[str | None]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_job(self, profile: str, table: str | None = None) -> str:
        """Create a job record and return its ID."""
        job_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, profile, table_name, status) VALUES (?, ?, ?, 'queued')",
                (job_id, profile, table),
            )
            self._conn.commit()
            self._queues[job_id] = queue.SimpleQueue()
        return job_id

    def start_job(self, job_id: str, fn: Callable[[Callable[[str], None]], None]) -> None:
        """
        Run *fn* in a background thread.

        *fn* receives a ``log_line`` callable it can call to emit log output.
        """
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, fn),
            daemon=True,
        )
        thread.start()

    def get_job(self, job_id: str) -> JobStatus | None:
        """Return full job details including log lines."""
        row = self._conn.execute(
            "SELECT id, profile, table_name, status, started_at, finished_at, log"
            " FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return JobStatus(
            id=row[0],
            profile=row[1],
            table=row[2],
            status=row[3],
            started_at=row[4],
            finished_at=row[5],
            log_lines=row[6].splitlines() if row[6] else [],
        )

    def list_jobs(self, limit: int = 20) -> list[JobSummary]:
        """Return the most recent *limit* jobs (newest first)."""
        rows = self._conn.execute(
            "SELECT id, profile, table_name, status, started_at, finished_at "
            "FROM jobs ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            JobSummary(
                id=r[0],
                profile=r[1],
                table=r[2],
                status=r[3],
                started_at=r[4],
                finished_at=r[5],
            )
            for r in rows
        ]

    def iter_log(self, job_id: str) -> Generator[str, None, None]:
        """
        Yield log lines as they arrive.

        Yields existing lines first, then blocks until the job finishes or
        the client disconnects. Sentinel ``None`` signals end-of-stream.
        """
        # Yield already-stored lines
        row = self._conn.execute("SELECT log, status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return
        yield from row[0].splitlines()

        if row[1] in ("done", "error"):
            return

        # Stream new lines from the in-memory queue
        q = self._queues.get(job_id)
        if q is None:
            return
        while True:
            item = q.get()
            if item is None:
                break
            yield item

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_job(self, job_id: str, fn: Callable[[Callable[[str], None]], None]) -> None:
        self._set_status(job_id, "running", started_at=_now_iso())
        try:
            fn(lambda line: self._append_log(job_id, line))
            self._set_status(job_id, "done", finished_at=_now_iso())
        except Exception as exc:
            self._append_log(job_id, f"ERROR: {exc}")
            self._set_status(job_id, "error", finished_at=_now_iso())
        finally:
            q = self._queues.get(job_id)
            if q is not None:
                q.put(None)  # signal end of stream

    def _set_status(
        self,
        job_id: str,
        status: str,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        with self._lock:
            if started_at:
                self._conn.execute(
                    "UPDATE jobs SET status=?, started_at=? WHERE id=?",
                    (status, started_at, job_id),
                )
            elif finished_at:
                self._conn.execute(
                    "UPDATE jobs SET status=?, finished_at=? WHERE id=?",
                    (status, finished_at, job_id),
                )
            else:
                self._conn.execute(
                    "UPDATE jobs SET status=? WHERE id=?",
                    (status, job_id),
                )
            self._conn.commit()

    def _append_log(self, job_id: str, line: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET log = log || ? WHERE id = ?",
                (line + "\n", job_id),
            )
            self._conn.commit()
        q = self._queues.get(job_id)
        if q is not None:
            q.put(line)
