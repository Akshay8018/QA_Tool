from __future__ import annotations

import unittest

from app.services.chat_controller import ChatControllerService
from app.services.session_store import InMemorySessionStore


class ChatControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemorySessionStore()
        self.session = self.store.create_session("Chat")
        self.sid = self.session["session_id"]
        self.controller = ChatControllerService(session_repository=self.store)

    def test_idle_runs_intake_and_clarify(self) -> None:
        result = self.controller.process_message(self.sid, "Test something", flow_stage="idle")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["intake"] is not None or result["suggested_next"] in ("clarify", "confirm_generate"))
        self.assertIn("reply", result)

    def test_confirm_generate_yes_suggests_preview(self) -> None:
        result = self.controller.process_message(self.sid, "yes", flow_stage="confirm_generate")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["suggested_next"], "preview_cases")

    def test_unknown_session_returns_none(self) -> None:
        result = self.controller.process_message("00000000-0000-0000-0000-000000000000", "hello", flow_stage="idle")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
