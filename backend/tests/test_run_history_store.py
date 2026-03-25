from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.run_history import InMemoryRunHistoryStore, SqliteRunHistoryStore


class RunHistoryStoreTests(unittest.TestCase):
    def _sample_payload(self, run_id: str) -> tuple[dict, dict, str]:
        report = {
            "run_id": run_id,
            "status": "passed",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:10Z",
        }
        human = {"summary": "ok"}
        instruction = "Open https://example.com and verify dashboard"
        return report, human, instruction

    def test_in_memory_store_roundtrip(self) -> None:
        store = InMemoryRunHistoryStore()
        report, human, instruction = self._sample_payload("run-mem-1")
        store.save(report, human, instruction)

        runs = store.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], "run-mem-1")
        full = store.get("run-mem-1")
        self.assertIsNotNone(full)
        assert full is not None
        self.assertEqual(full["json_report"]["status"], "passed")
        self.assertEqual(full["human_report"]["summary"], "ok")

    def test_sqlite_store_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "run-history.db"
            store = SqliteRunHistoryStore(str(db_path))
            report, human, instruction = self._sample_payload("run-sqlite-1")
            store.save(report, human, instruction)

            runs = store.list_runs()
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["run_id"], "run-sqlite-1")
            full = store.get("run-sqlite-1")
            self.assertIsNotNone(full)
            assert full is not None
            self.assertEqual(full["json_report"]["status"], "passed")
            self.assertEqual(full["human_report"]["summary"], "ok")


if __name__ == "__main__":
    unittest.main()
