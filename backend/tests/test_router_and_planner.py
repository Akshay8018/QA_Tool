from __future__ import annotations

import unittest

from app.agents.pipeline_agents import PlannerAgent
from app.api.schemas import EngineType, TestRequest
from app.llm.providers import LLMProvider
from app.llm.router import LLMRouter, RoutedModel


class _FakeProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        cost: float,
        latency_ms: int,
        configured: bool,
        should_fail: bool,
        text: str,
    ) -> None:
        self.name = name
        self.est_cost_per_1k = cost
        self.est_latency_ms = latency_ms
        self.model_name = f"{name}-model"
        self._configured = configured
        self._should_fail = should_fail
        self._text = text

    def is_configured(self) -> bool:
        return self._configured

    async def complete(self, prompt: str) -> str:
        if self._should_fail:
            raise RuntimeError(f"{self.name} failed")
        return f"{self._text}:{prompt[:20]}"


class _FakeRouterSuccess:
    async def complete_with_fallback(self, prompt: str, priority: str = "balanced"):
        _ = priority
        return (
            '{"scenarios":[{"id":"scn-10","title":"Checkout","objective":"Verify checkout","risk_level":"high"}]}',
            RoutedModel(provider="fake", model="fake-model"),
        )


class _FakeRouterBadJSON:
    async def complete_with_fallback(self, prompt: str, priority: str = "balanced"):
        _ = prompt
        _ = priority
        return ("not json output", RoutedModel(provider="fake", model="fake-model"))


class RouterFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_unconfigured_and_uses_next_provider(self) -> None:
        router = LLMRouter()
        router.providers = [
            _FakeProvider("first", 0.1, 100, configured=False, should_fail=False, text="unused"),
            _FakeProvider("second", 0.2, 200, configured=True, should_fail=False, text="ok"),
        ]

        text, route = await router.complete_with_fallback("hello", priority="balanced")
        self.assertIn("ok", text)
        self.assertEqual(route.provider, "second")

    async def test_fallback_when_first_configured_provider_fails(self) -> None:
        router = LLMRouter()
        router.providers = [
            _FakeProvider("first", 0.1, 100, configured=True, should_fail=True, text="bad"),
            _FakeProvider("second", 0.2, 200, configured=True, should_fail=False, text="good"),
        ]

        text, route = await router.complete_with_fallback("hello", priority="speed")
        self.assertIn("good", text)
        self.assertEqual(route.provider, "second")


class PlannerContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_planner_parses_json_contract(self) -> None:
        planner = PlannerAgent(_FakeRouterSuccess())  # type: ignore[arg-type]
        request = TestRequest(
            instruction="Test checkout flow",
            target_url="https://example.com",
            execution_engine=EngineType.playwright,
        )
        plan = await planner.run(request)
        self.assertEqual(plan["route"]["provider"], "fake")
        self.assertEqual(len(plan["scenarios"]), 1)
        self.assertEqual(plan["scenarios"][0]["id"], "scn-10")

    async def test_planner_falls_back_on_non_json(self) -> None:
        planner = PlannerAgent(_FakeRouterBadJSON())  # type: ignore[arg-type]
        request = TestRequest(
            instruction="Test login flow",
            target_url="https://example.com",
            execution_engine=EngineType.playwright,
        )
        plan = await planner.run(request)
        self.assertEqual(plan["route"]["provider"], "fake")
        self.assertEqual(plan["scenarios"][0]["id"], "scn-1")
        self.assertEqual(plan["scenarios"][0]["title"], "Core Journey")


if __name__ == "__main__":
    unittest.main()
