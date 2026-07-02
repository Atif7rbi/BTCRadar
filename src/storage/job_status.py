from __future__ import annotations

from datetime import datetime, timezone
import json
from .database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStatusStore:
    def __init__(self, db: Database):
        self.db = db
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.db.connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS btc_radar_job_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_name TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    rows_saved INTEGER DEFAULT 0,
                    duration_ms INTEGER,
                    error TEXT,
                    details_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_btc_radar_job_runs_name_id
                ON btc_radar_job_runs(job_name, id)
                """
            )

    def record(self, job_name: str, *, started_at: str | None, finished_at: str | None,
               status: str, rows_saved: int = 0, duration_ms: int | None = None,
               error: str | None = None, details: dict | None = None) -> None:
        with self.db.connect() as con:
            con.execute(
                """
                INSERT INTO btc_radar_job_runs
                (job_name, started_at, finished_at, status, rows_saved, duration_ms, error, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_name,
                    started_at,
                    finished_at,
                    status,
                    int(rows_saved or 0),
                    duration_ms,
                    error,
                    json.dumps(details or {}, ensure_ascii=False),
                    _now(),
                ),
            )

    def latest(self, job_name: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute(
                "SELECT * FROM btc_radar_job_runs WHERE job_name=? ORDER BY id DESC LIMIT 1",
                (job_name,),
            ).fetchone()
            return dict(row) if row else None

    def recent(self, job_name: str | None = None, limit: int = 20) -> list[dict]:
        with self.db.connect() as con:
            if job_name:
                rows = con.execute(
                    "SELECT * FROM btc_radar_job_runs WHERE job_name=? ORDER BY id DESC LIMIT ?",
                    (job_name, int(limit)),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM btc_radar_job_runs ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            return [dict(r) for r in rows]
