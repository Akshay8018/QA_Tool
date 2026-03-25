from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.qa_memory_repository import InMemoryQAMemoryRepository, SqliteQAMemoryRepository


class QAMemoryRepositoryTests(unittest.TestCase):
    def _roundtrip_assertions(self, repo) -> None:
        prompt_id = repo.create_prompt("test login", {"normalized": "test login"})
        self.assertTrue(prompt_id)

        test_case_id = repo.save_test_cases(
            prompt_id=prompt_id,
            test_cases_json={"cases": [{"title": "Valid login", "type": "functional"}]},
            test_type="functional",
        )
        self.assertTrue(test_case_id)

        result_id = repo.save_execution_result(
            test_case_id=test_case_id,
            status="failed",
            error_message="locator timeout",
            screenshot_path="screens/1.png",
            logs={"step": "login", "status": "failed"},
        )
        self.assertTrue(result_id)

        repo.record_fix_strategy("locator_timeout", {"fallback": "text=Login"}, success=False)
        repo.record_fix_strategy("locator_timeout", {"fallback": "text=Login"}, success=True)

        fixes = repo.list_fix_memory()
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0]["error_type"], "locator_timeout")
        self.assertEqual(fixes[0]["attempt_count"], 2)
        self.assertEqual(fixes[0]["success_count"], 1)
        self.assertAlmostEqual(float(fixes[0]["success_rate"]), 0.5, places=2)

    def test_in_memory_repository_roundtrip(self) -> None:
        repo = InMemoryQAMemoryRepository()
        self._roundtrip_assertions(repo)

    def test_sqlite_repository_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "qa-memory.db"
            repo = SqliteQAMemoryRepository(str(db_path))
            self._roundtrip_assertions(repo)


if __name__ == "__main__":
    unittest.main()
