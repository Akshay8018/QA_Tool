from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings


class SessionRepository:
    def create_session(self, title: str) -> dict[str, Any]:
        raise NotImplementedError

    def list_sessions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def append_message(self, session_id: str, role: str, text: str) -> dict[str, Any] | None:
        raise NotImplementedError


@dataclass
class InMemorySessionStore(SessionRepository):
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    messages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def create_session(self, title: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        session_id = str(uuid4())
        item = {"session_id": session_id, "title": title[:120], "created_at": now, "updated_at": now}
        self.sessions[session_id] = item
        self.messages[session_id] = []
        return item

    def list_sessions(self) -> list[dict[str, Any]]:
        return sorted(self.sessions.values(), key=lambda x: x.get("updated_at", ""), reverse=True)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.sessions.get(session_id)
        if not session:
            return None
        return {**session, "messages": list(self.messages.get(session_id, []))}

    def append_message(self, session_id: str, role: str, text: str) -> dict[str, Any] | None:
        if session_id not in self.sessions:
            return None
        message = {
            "message_id": str(uuid4()),
            "session_id": session_id,
            "role": role[:20],
            "text": text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.messages.setdefault(session_id, []).append(message)
        self.sessions[session_id]["updated_at"] = message["created_at"]
        return message


class SqliteSessionStore(SessionRepository):
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
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS session_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            connection.commit()

    def create_session(self, title: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        session_id = str(uuid4())
        item = {"session_id": session_id, "title": title[:120], "created_at": now, "updated_at": now}
        with self._lock:
            with closing(self._connect()) as connection:
                connection.execute(
                    "INSERT INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (item["session_id"], item["title"], item["created_at"], item["updated_at"]),
                )
                connection.commit()
        return item

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT session_id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
                ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            with closing(self._connect()) as connection:
                session_row = connection.execute(
                    "SELECT session_id, title, created_at, updated_at FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if session_row is None:
                    return None
                messages = connection.execute(
                    """
                    SELECT message_id, session_id, role, text, created_at
                    FROM session_messages
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                ).fetchall()
        return {**dict(session_row), "messages": [dict(m) for m in messages]}

    def append_message(self, session_id: str, role: str, text: str) -> dict[str, Any] | None:
        with self._lock:
            with closing(self._connect()) as connection:
                exists = connection.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
                if exists is None:
                    return None
                message = {
                    "message_id": str(uuid4()),
                    "session_id": session_id,
                    "role": role[:20],
                    "text": text,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                connection.execute(
                    """
                    INSERT INTO session_messages (message_id, session_id, role, text, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        message["message_id"],
                        message["session_id"],
                        message["role"],
                        message["text"],
                        message["created_at"],
                    ),
                )
                connection.execute(
                    "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                    (message["created_at"], session_id),
                )
                connection.commit()
        return message


def _build_session_store() -> SessionRepository:
    backend = settings.session_backend.lower().strip()
    if backend == "memory":
        return InMemorySessionStore()
    return SqliteSessionStore(settings.session_sqlite_path)


session_store: SessionRepository = _build_session_store()
