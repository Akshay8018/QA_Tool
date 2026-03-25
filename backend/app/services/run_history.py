from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


class RunHistoryRepository:
    def save(self, json_report: dict[str, Any], human_report: dict[str, Any], instruction: str) -> None:
        raise NotImplementedError

    def list_runs(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get(self, run_id: str) -> dict[str, Any] | None:
        raise NotImplementedError


@dataclass
class InMemoryRunHistoryStore(RunHistoryRepository):
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def save(self, json_report: dict[str, Any], human_report: dict[str, Any], instruction: str) -> None:
        run_id = str(json_report.get("run_id", "unknown"))
        self.runs[run_id] = {
            "run_id": run_id,
            "instruction": instruction[:180],
            "status": json_report.get("status", "unknown"),
            "started_at": json_report.get("started_at"),
            "finished_at": json_report.get("finished_at"),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "json_report": json_report,
            "human_report": human_report,
        }

    def list_runs(self) -> list[dict[str, Any]]:
        return sorted(self.runs.values(), key=lambda x: x.get("saved_at", ""), reverse=True)

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self.runs.get(run_id)


class SqliteRunHistoryStore(RunHistoryRepository):
    def __init__(self, db_path: str) -> None:
        self._lock = threading.Lock()
        self._db_path = Path(db_path)
        if not self._db_path.is_absolute():
            self._db_path = Path.cwd() / self._db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._db_path), check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS run_history (
                    run_id TEXT PRIMARY KEY,
                    instruction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    saved_at TEXT NOT NULL,
                    json_report TEXT NOT NULL,
                    human_report TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def save(self, json_report: dict[str, Any], human_report: dict[str, Any], instruction: str) -> None:
        run_id = str(json_report.get("run_id", "unknown"))
        payload = {
            "run_id": run_id,
            "instruction": instruction[:180],
            "status": str(json_report.get("status", "unknown")),
            "started_at": json_report.get("started_at"),
            "finished_at": json_report.get("finished_at"),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "json_report": json_report,
            "human_report": human_report,
        }
        with self._lock:
            with closing(self._connect()) as connection:
                connection.execute(
                    """
                    INSERT INTO run_history (
                        run_id, instruction, status, started_at, finished_at, saved_at, json_report, human_report
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        instruction=excluded.instruction,
                        status=excluded.status,
                        started_at=excluded.started_at,
                        finished_at=excluded.finished_at,
                        saved_at=excluded.saved_at,
                        json_report=excluded.json_report,
                        human_report=excluded.human_report
                    """,
                    (
                        payload["run_id"],
                        payload["instruction"],
                        payload["status"],
                        payload["started_at"],
                        payload["finished_at"],
                        payload["saved_at"],
                        json.dumps(payload["json_report"]),
                        json.dumps(payload["human_report"]),
                    ),
                )
                connection.commit()

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT run_id, instruction, status, started_at, finished_at, saved_at
                    FROM run_history
                    ORDER BY saved_at DESC
                    """
                ).fetchall()
        return [dict(row) for row in rows]

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """
                    SELECT run_id, instruction, status, started_at, finished_at, saved_at, json_report, human_report
                    FROM run_history
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["json_report"] = json.loads(data["json_report"])
        data["human_report"] = json.loads(data["human_report"])
        return data


def _build_history_store() -> RunHistoryRepository:
    backend = settings.run_history_backend.lower().strip()
    if backend == "memory":
        return InMemoryRunHistoryStore()
    return SqliteRunHistoryStore(settings.run_history_sqlite_path)


run_history_store: RunHistoryRepository = _build_history_store()
