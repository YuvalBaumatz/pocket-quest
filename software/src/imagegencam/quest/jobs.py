"""Transactional job journal: approval, dispatch budget and restart recovery.

SQLite is local and part of Python. A transaction reserves a dispatch and its budget
slot together; no cloud database or second worker may open this data directory.
"""

import fcntl
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .filters import Style
from .storage import atomic_write


class JobState(StrEnum):
    AWAITING = "awaiting_approval"
    READY = "ready"
    RUNNING = "running"
    RETRY = "retry_wait"
    UNKNOWN = "unknown"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Job:
    id: str
    style: str
    provider: str
    model: str
    prompt: str
    state: JobState
    attempts: int
    retry_at: float
    error: str


class JobQueue:
    def __init__(self, root: Path, daily_limit: int = 10, pending_limit: int = 50) -> None:
        if daily_limit < 1 or pending_limit < 1:
            raise ValueError("Queue limits must be positive")
        self.root, self.daily_limit, self.pending_limit = root, daily_limit, pending_limit
        root.mkdir(parents=True, exist_ok=True)
        self._file = (root / "generation.lock").open("a")
        try:
            fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._file.close()
            raise ValueError("Pocket Quest is already using this data directory") from None
        self.lock = threading.RLock()
        self.closed = False
        self.budget_blocked = False
        try:
            self.db = sqlite3.connect(
                root / "generation.sqlite3", check_same_thread=False, isolation_level=None
            )
            self._initialize()
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self._file.close()
            raise

    def _initialize(self) -> None:
        self.db.row_factory = sqlite3.Row
        self.closed = False
        self.budget_blocked = False
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ValueError("Unsupported generation database version")
        self.db.executescript("""
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, style TEXT NOT NULL, provider TEXT NOT NULL,
              model TEXT NOT NULL, prompt TEXT NOT NULL, state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0,
              error TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS dispatches (at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS clock (id INTEGER PRIMARY KEY, highwater REAL NOT NULL);
            INSERT OR IGNORE INTO clock VALUES (1, 0);
            PRAGMA user_version=1;
        """)
        with self.transaction():
            self.db.execute(
                "UPDATE jobs SET state=?, error='interrupted' WHERE state=?",
                (JobState.UNKNOWN, JobState.RUNNING),
            )
        # If a crash happened after the image write but before the SQLite commit,
        # finish locally instead of offering a potentially charged second request.
        from .providers import EditError, validated_png

        for job in self.all():
            if job.state == JobState.UNKNOWN:
                output = self.root / "photos" / job.id / "magic.png"
                if output.is_file():
                    try:
                        validated_png(output.read_bytes())
                    except (OSError, EditError):
                        continue
                    with self.transaction():
                        self.db.execute(
                            "UPDATE jobs SET state=?, error='' WHERE id=?",
                            (JobState.SUCCEEDED, job.id),
                        )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self.lock:
            if not self.closed:
                self.db.close()
                self._file.close()
                self.closed = True

    def all(self) -> list[Job]:
        with self.lock:
            return [
                self._job(row) for row in self.db.execute("SELECT * FROM jobs ORDER BY rowid DESC")
            ]

    @staticmethod
    def _job(row: sqlite3.Row) -> Job:
        if not re.fullmatch(r"[0-9a-f]{32}", row["id"]):
            raise ValueError("Invalid job ID")
        return Job(
            row["id"],
            row["style"],
            row["provider"],
            row["model"],
            row["prompt"],
            JobState(row["state"]),
            row["attempts"],
            row["retry_at"],
            row["error"],
        )

    def enqueue(self, photo_id: str, style: Style, provider: str, model: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", photo_id):
            raise ValueError("Invalid photo ID")
        if not style.is_ai or not model or provider not in ("demo", "openai", "gemini"):
            raise ValueError("Invalid generation request")
        with self.transaction():
            if self.db.execute("SELECT 1 FROM jobs WHERE id=?", (photo_id,)).fetchone():
                return
            count = self.db.execute(
                "SELECT COUNT(*) FROM jobs WHERE state NOT IN (?, ?)",
                (JobState.SUCCEEDED, JobState.CANCELLED),
            ).fetchone()[0]
            if count >= self.pending_limit:
                raise ValueError("Magic queue is full")
            self.db.execute(
                "INSERT INTO jobs (id,style,provider,model,prompt,state) VALUES (?,?,?,?,?,?)",
                (photo_id, style.value, provider, model, style.prompt, JobState.AWAITING),
            )

    def approve(self, job_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise ValueError("Invalid job ID")
        from .providers import EditError, validated_png

        output = self.root / "photos" / job_id / "magic.png"
        if output.is_file():
            try:
                validated_png(output.read_bytes())
            except (OSError, EditError):
                pass
            else:
                with self.transaction():
                    self.db.execute(
                        "UPDATE jobs SET state=?, error='' WHERE id=? AND state=?",
                        (JobState.SUCCEEDED, job_id, JobState.UNKNOWN),
                    )
        with self.transaction():
            self.db.execute(
                "UPDATE jobs SET state=?, error='' WHERE id=? AND state IN (?,?,?) AND attempts<3",
                (JobState.READY, job_id, JobState.AWAITING, JobState.FAILED, JobState.UNKNOWN),
            )

    def cancel(self, job_id: str) -> None:
        with self.transaction():
            self.db.execute(
                "UPDATE jobs SET state=? WHERE id=? AND state NOT IN (?,?)",
                (JobState.CANCELLED, job_id, JobState.SUCCEEDED, JobState.CANCELLED),
            )

    def claim(
        self, now: float | None = None, providers: tuple[str, ...] | None = None
    ) -> Job | None:
        now = time.time() if now is None else now
        with self.transaction():
            high = self.db.execute("SELECT highwater FROM clock WHERE id=1").fetchone()[0]
            now = max(now, high)
            params: list[object] = [JobState.READY, JobState.RETRY, now]
            provider_filter = ""
            if providers is not None:
                if not providers:
                    return None
                provider_filter = " AND provider IN (" + ",".join("?" for _ in providers) + ")"
                params.extend(providers)
            row = self.db.execute(
                "SELECT * FROM jobs WHERE (state=? OR (state=? AND retry_at<=?)) AND attempts<3"
                + provider_filter
                + " ORDER BY rowid LIMIT 1",
                params,
            ).fetchone()
            self.budget_blocked = False
            if row is None:
                return None
            count = self.db.execute(
                "SELECT COUNT(*) FROM dispatches WHERE at>?", (now - 86400,)
            ).fetchone()[0]
            if count >= self.daily_limit:
                self.budget_blocked = True
                return None
            self.db.execute("UPDATE clock SET highwater=? WHERE id=1", (now,))
            self.db.execute("DELETE FROM dispatches WHERE at<=?", (now - 86400,))
            self.db.execute(
                "UPDATE jobs SET state=?, attempts=attempts+1 WHERE id=?",
                (JobState.RUNNING, row["id"]),
            )
            self.db.execute("INSERT INTO dispatches VALUES (?)", (now,))
            return self._job(
                self.db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            )

    def fail(
        self, job: Job, code: str, *, unknown: bool = False, retry_after: float | None = None
    ) -> None:
        state = JobState.UNKNOWN if unknown else JobState.FAILED
        if retry_after is not None and job.attempts < 3:
            state = JobState.RETRY
        with self.transaction():
            self.db.execute(
                "UPDATE jobs SET state=?, error=?, retry_at=? WHERE id=? AND state=?",
                (state, code, time.time() + (retry_after or 0), job.id, JobState.RUNNING),
            )

    def complete(self, job: Job, image: bytes) -> bool:
        with self.transaction():
            row = self.db.execute("SELECT state FROM jobs WHERE id=?", (job.id,)).fetchone()
            if row is None or row[0] != JobState.RUNNING:
                return False  # Cancellation wins over a late provider response.
            atomic_write(self.root / "photos" / job.id / "magic.png", image)
            self.db.execute(
                "UPDATE jobs SET state=?, error='' WHERE id=?", (JobState.SUCCEEDED, job.id)
            )
            return True
