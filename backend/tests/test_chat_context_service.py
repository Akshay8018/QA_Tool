from __future__ import annotations

import unittest

from app.services.chat_context_service import ChatContextService
from app.services.session_store import InMemorySessionStore


class ChatContextServiceTests(unittest.TestCase):
    def test_build_context_for_existing_session(self) -> None:
        store = InMemorySessionStore()
        session = store.create_session("QA Chat")
        sid = session["session_id"]
        store.append_message(sid, "user", "Test login flow")
        store.append_message(sid, "assistant", "Sure, share URL")
        store.append_message(sid, "user", "https://example.com")

        svc = ChatContextService(session_repository=store, max_context_messages=10)
        context = svc.build_context(sid)
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context["session_id"], sid)
        self.assertEqual(context["message_count"], 3)
        self.assertEqual(context["last_user_message"], "https://example.com")
        self.assertEqual(len(context["context_window"]), 3)
        self.assertIn("Recent:", context["summary"])

    def test_build_context_returns_none_for_unknown_session(self) -> None:
        store = InMemorySessionStore()
        svc = ChatContextService(session_repository=store)
        context = svc.build_context("unknown")
        self.assertIsNone(context)


if __name__ == "__main__":
    unittest.main()
