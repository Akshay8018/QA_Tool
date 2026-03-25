from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings


class QAMemoryRepository:
    def create_prompt(self, user_input: str, normalized_input: dict[str, Any] | str) -> str:
        raise NotImplementedError

    def save_test_cases(self, prompt_id: str, test_cases_json: dict[str, Any], test_type: str) -> str:
        raise NotImplementedError

    def save_execution_result(
        self,
        test_case_id: str,
        status: str,
        error_message: str | None,
        screenshot_path: str | None,
        logs: dict[str, Any] | list[Any] | str | None,
    ) -> str:
        raise NotImplementedError

    def record_fix_strategy(self, error_type: str, fix_strategy: dict[str, Any] | str, success: bool) -> None:
        raise NotImplementedError

    def list_fix_memory(self) -> list[dict[str, Any]]:
        raise NotImplementedError


@dataclass
class InMemoryQAMemoryRepository(QAMemoryRepository):
    prompts: dict[str, dict[str, Any]] = field(default_factory=dict)
    test_cases: dict[str, dict[str, Any]] = field(default_factory=dict)
    execution_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    fix_memory: dict[str, dict[str, Any]] = field(default_factory=dict)

    def create_prompt(self, user_input: str, normalized_input: dict[str, Any] | str) -> str:
        prompt_id = str(uuid4())
        self.prompts[prompt_id] = {
            "id": prompt_id,
            "user_input": user_input,
            "normalized_input": normalized_input,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return prompt_id

    def save_test_cases(self, prompt_id: str, test_cases_json: dict[str, Any], test_type: str) -> str:
        test_case_id = str(uuid4())
        self.test_cases[test_case_id] = {
            "id": test_case_id,
            "prompt_id": prompt_id,
            "test_cases_json": test_cases_json,
            "test_type": test_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return test_case_id

    def save_execution_result(
        self,
        test_case_id: str,
        status: str,
        error_message: str | None,
        screenshot_path: str | None,
        logs: dict[str, Any] | list[Any] | str | None,
    ) -> str:
        result_id = str(uuid4())
        self.execution_results[result_id] = {
            "id": result_id,
            "test_case_id": test_case_id,
            "status": status,
            "error_message": error_message,
            "screenshot_path": screenshot_path,
            "logs": logs,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return result_id

    def record_fix_strategy(self, error_type: str, fix_strategy: dict[str, Any] | str, success: bool) -> None:
        row = self.fix_memory.get(error_type)
        if row is None:
            row = {
                "id": str(uuid4()),
                "error_type": error_type,
                "fix_strategy": fix_strategy,
                "attempt_count": 0,
                "success_count": 0,
                "success_rate": 0.0,
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.fix_memory[error_type] = row
        row["attempt_count"] += 1
        if success:
            row["success_count"] += 1
        row["success_rate"] = row["success_count"] / max(row["attempt_count"], 1)
        row["fix_strategy"] = fix_strategy
        row["last_updated_at"] = datetime.now(timezone.utc).isoformat()

    def list_fix_memory(self) -> list[dict[str, Any]]:
        return sorted(self.fix_memory.values(), key=lambda x: x["last_updated_at"], reverse=True)


class SqliteQAMemoryRepository(QAMemoryRepository):
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
                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT PRIMARY KEY,
                    user_input TEXT NOT NULL,
                    normalized_input TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS test_cases (
                    id TEXT PRIMARY KEY,
                    prompt_id TEXT NOT NULL,
                    test_cases_json TEXT NOT NULL,
                    test_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(prompt_id) REFERENCES prompts(id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_results (
                    id TEXT PRIMARY KEY,
                    test_case_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    screenshot_path TEXT,
                    logs TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(test_case_id) REFERENCES test_cases(id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fix_memory (
                    id TEXT PRIMARY KEY,
                    error_type TEXT UNIQUE NOT NULL,
                    fix_strategy TEXT NOT NULL,
                    success_rate REAL NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    success_count INTEGER NOT NULL,
                    last_updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def create_prompt(self, user_input: str, normalized_input: dict[str, Any] | str) -> str:
        prompt_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        normalized_payload = normalized_input if isinstance(normalized_input, str) else json.dumps(normalized_input)
        with self._lock:
            with closing(self._connect()) as connection:
                connection.execute(
                    "INSERT INTO prompts (id, user_input, normalized_input, created_at) VALUES (?, ?, ?, ?)",
                    (prompt_id, user_input, normalized_payload, now),
                )
                connection.commit()
        return prompt_id

    def save_test_cases(self, prompt_id: str, test_cases_json: dict[str, Any], test_type: str) -> str:
        test_case_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with closing(self._connect()) as connection:
                connection.execute(
                    """
                    INSERT INTO test_cases (id, prompt_id, test_cases_json, test_type, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (test_case_id, prompt_id, json.dumps(test_cases_json), test_type, now),
                )
                connection.commit()
        return test_case_id

    def save_execution_result(
        self,
        test_case_id: str,
        status: str,
        error_message: str | None,
        screenshot_path: str | None,
        logs: dict[str, Any] | list[Any] | str | None,
    ) -> str:
        result_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        logs_payload = logs if isinstance(logs, str) else json.dumps(logs if logs is not None else {})
        with self._lock:
            with closing(self._connect()) as connection:
                connection.execute(
                    """
                    INSERT INTO execution_results (id, test_case_id, status, error_message, screenshot_path, logs, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (result_id, test_case_id, status, error_message, screenshot_path, logs_payload, now),
                )
                connection.commit()
        return result_id

    def record_fix_strategy(self, error_type: str, fix_strategy: dict[str, Any] | str, success: bool) -> None:
        now = datetime.now(timezone.utc).isoformat()
        strategy_payload = fix_strategy if isinstance(fix_strategy, str) else json.dumps(fix_strategy)
        with self._lock:
            with closing(self._connect()) as connection:
                existing = connection.execute(
                    """
                    SELECT id, attempt_count, success_count
                    FROM fix_memory
                    WHERE error_type = ?
                    """,
                    (error_type,),
                ).fetchone()
                if existing is None:
                    attempt_count = 1
                    success_count = 1 if success else 0
                    success_rate = success_count / attempt_count
                    connection.execute(
                        """
                        INSERT INTO fix_memory (
                            id, error_type, fix_strategy, success_rate, attempt_count, success_count, last_updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (str(uuid4()), error_type, strategy_payload, success_rate, attempt_count, success_count, now),
                    )
                else:
                    attempt_count = int(existing["attempt_count"]) + 1
                    success_count = int(existing["success_count"]) + (1 if success else 0)
                    success_rate = success_count / attempt_count
                    connection.execute(
                        """
                        UPDATE fix_memory
                        SET fix_strategy = ?, success_rate = ?, attempt_count = ?, success_count = ?, last_updated_at = ?
                        WHERE error_type = ?
                        """,
                        (strategy_payload, success_rate, attempt_count, success_count, now, error_type),
                    )
                connection.commit()

    def list_fix_memory(self) -> list[dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT id, error_type, fix_strategy, success_rate, attempt_count, success_count, last_updated_at
                    FROM fix_memory
                    ORDER BY last_updated_at DESC
                    """
                ).fetchall()
        return [dict(r) for r in rows]


def _build_qa_memory_repository() -> QAMemoryRepository:
    backend = settings.qa_memory_backend.lower().strip()
    if backend == "memory":
        return InMemoryQAMemoryRepository()
    return SqliteQAMemoryRepository(settings.qa_memory_sqlite_path)


qa_memory_repository: QAMemoryRepository = _build_qa_memory_repository()
