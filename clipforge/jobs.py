"""Tiny SQLite job log. Today it just records runs; later a worker can poll it as a queue."""
from __future__ import annotations
import json
import sqlite3
import time
import uuid
from pathlib import Path
from contextlib import AbstractContextManager


class JobStore(AbstractContextManager):
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, source TEXT, status TEXT, "
            "error TEXT, created REAL, result TEXT, progress INTEGER NOT NULL DEFAULT 0, "
            "stage TEXT NOT NULL DEFAULT 'Queued', logs TEXT NOT NULL DEFAULT '[]')"
        )
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(jobs)")}
        for name, declaration in (("progress", "INTEGER NOT NULL DEFAULT 0"),
                                  ("stage", "TEXT NOT NULL DEFAULT 'Queued'"),
                                  ("logs", "TEXT NOT NULL DEFAULT '[]'")):
            if name not in columns:
                self.db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {declaration}")
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None

    def create(self, source: str) -> str:
        job_id = uuid.uuid4().hex[:8]
        self.db.execute("INSERT INTO jobs (id,source,status,error,created,result,progress,stage,logs) "
                        "VALUES (?,?,?,?,?,?,0,'Queued','[]')",
                        (job_id, source, "queued", None, time.time(), None))
        self.db.commit()
        return job_id

    def start(self, job_id: str) -> None:
        self.db.execute("UPDATE jobs SET status='running', stage='Starting' WHERE id=?", (job_id,))
        self.db.commit()

    def update(self, job_id: str, *, stage: str | None = None, progress: int | None = None,
               message: str | None = None) -> None:
        row = self.db.execute("SELECT logs FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return
        logs = json.loads(row["logs"] or "[]")
        if message:
            logs.append({"time": time.time(), "message": message})
            logs = logs[-250:]
        self.db.execute("UPDATE jobs SET stage=COALESCE(?,stage), progress=COALESCE(?,progress), logs=? WHERE id=?",
                         (stage, progress, json.dumps(logs), job_id))
        self.db.commit()

    def finish(self, job_id: str, result: dict) -> None:
        self.db.execute("UPDATE jobs SET status='done', result=?, progress=100, stage='Complete' WHERE id=?",
                        (json.dumps(result), job_id))
        self.db.commit()

    def fail(self, job_id: str, error: str) -> None:
        self.db.execute("UPDATE jobs SET status='failed', stage='Failed', error=? WHERE id=?", (error, job_id))
        self.db.commit()

    def delete(self, job_id: str) -> None:
        self.db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        self.db.commit()

    def fail_interrupted(self) -> None:
        """Jobs still 'running' or 'queued' at server start were cut off when the app closed."""
        self.db.execute("UPDATE jobs SET status='failed', stage='Interrupted', "
                        "error='ClipForge was closed before this job finished.' "
                        "WHERE status IN ('queued','running')")
        self.db.commit()

    def get(self, job_id: str) -> dict | None:
        row = self.db.execute("SELECT id,source,status,error,result,created,progress,stage,logs FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["result"] = json.loads(item["result"]) if item["result"] else None
        item["logs"] = json.loads(item["logs"] or "[]")
        return item

    def list(self) -> list[dict]:
        ids = [row[0] for row in self.db.execute("SELECT id FROM jobs ORDER BY created DESC")]
        return [self.get(job_id) for job_id in ids]
