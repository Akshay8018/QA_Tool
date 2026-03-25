from __future__ import annotations

import unittest

from app.api.schemas import TestRequest
from app.services.testcase_generation_service import TestCaseGenerationService


class TestCaseGenerationServiceTests(unittest.TestCase):
    def test_generate_returns_four_case_types(self) -> None:
        service = TestCaseGenerationService()
        request = TestRequest(
            instruction="Test login flow",
            target_url="https://example.com/login",
            test_data={"expected_text": "dashboard"},
        )
        generated = service.generate(request)
        case_types = {c.case_type for c in generated}
        self.assertEqual(case_types, {"functional", "negative", "edge", "security"})
        self.assertEqual(len(generated), 4)

    def test_to_scenarios_maps_generated_cases(self) -> None:
        service = TestCaseGenerationService()
        request = TestRequest(instruction="Test login flow", target_url="https://example.com/login")
        scenarios = service.to_scenarios(request)
        self.assertEqual(len(scenarios), 4)
        self.assertTrue(all(s.steps for s in scenarios))
        self.assertTrue(scenarios[0].id.startswith("adv-scn-"))


if __name__ == "__main__":
    unittest.main()
