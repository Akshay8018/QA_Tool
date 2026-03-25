from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.session_store import InMemorySessionStore, SqliteSessionStore


class SessionStoreTests(unittest.TestCase):
    def test_in_memory_session_roundtrip(self) -> None:
        store = InMemorySessionStore()
        session = store.create_session("QA Chat 1")
        self.assertIn("session_id", session)

        message = store.append_message(session["session_id"], "user", "Hello")
        self.assertIsNotNone(message)
        details = store.get_session(session["session_id"])
        self.assertIsNotNone(details)
        assert details is not None
        self.assertEqual(len(details["messages"]), 1)
        self.assertEqual(details["messages"][0]["text"], "Hello")

    def test_sqlite_session_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "sessions.db"
            store = SqliteSessionStore(str(db_path))
            session = store.create_session("QA Chat DB")
            message = store.append_message(session["session_id"], "assistant", "Hi there")
            self.assertIsNotNone(message)

            listed = store.list_sessions()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["session_id"], session["session_id"])

            details = store.get_session(session["session_id"])
            self.assertIsNotNone(details)
            assert details is not None
            self.assertEqual(details["messages"][0]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
