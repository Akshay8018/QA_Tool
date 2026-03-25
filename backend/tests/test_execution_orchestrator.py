from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.api.schemas import ExecutionResult, Scenario, Step, TestRequest, TestRunReport
from app.services.execution_orchestrator import ExecutionOrchestrator


class _DelegateOK:
    async def preview_scenarios(self, request: TestRequest) -> list[Scenario]:
        _ = request
        return [
            Scenario(
                id="scn-1",
                title="Smoke",
                objective="basic",
                steps=[Step(id="s1", action="goto", target="https://example.com")],
            )
        ]

    async def run(self, request: TestRequest, event_sink=None) -> tuple[TestRunReport, dict]:
        _ = request
        _ = event_sink
        now = datetime.now(timezone.utc)
        report = TestRunReport(
            run_id="run-1",
            status="passed",
            started_at=now,
            finished_at=now,
            scenarios=[],
            results=[ExecutionResult(step_id="s1", status="passed", details="ok")],
            root_cause_analysis={},
            recommendations=[],
        )
        return report, {"summary": "ok"}


class _DelegateRetry:
    def __init__(self) -> None:
        self.calls = 0

    async def preview_scenarios(self, request: TestRequest) -> list[Scenario]:
        _ = request
        return [
            Scenario(
                id="scn-1",
                title="Smoke",
                objective="basic",
                steps=[Step(id="s1", action="goto", target="https://example.com")],
            )
        ]

    async def run(self, request: TestRequest, event_sink=None) -> tuple[TestRunReport, dict]:
        _ = request
        _ = event_sink
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient")
        now = datetime.now(timezone.utc)
        report = TestRunReport(
            run_id="run-2",
            status="passed",
            started_at=now,
            finished_at=now,
            scenarios=[],
            results=[ExecutionResult(step_id="s1", status="passed", details="ok")],
            root_cause_analysis={},
            recommendations=[],
        )
        return report, {"summary": "ok"}


class _DelegateInvalidPreview:
    async def preview_scenarios(self, request: TestRequest) -> list[Scenario]:
        _ = request
        return []

    async def run(self, request: TestRequest, event_sink=None):
        raise AssertionError("run should not be called when validation fails")


class _DelegateCaptureRequest(_DelegateOK):
    def __init__(self) -> None:
        self.seen_request: TestRequest | None = None

    async def preview_scenarios(self, request: TestRequest) -> list[Scenario]:
        self.seen_request = request
        return await super().preview_scenarios(request)


class _RAGServiceStub:
    async def retrieve(self, query: str, top_k: int = 5):
        _ = query
        _ = top_k
        return {
            "sources": [{"title": "qa-doc", "url": "https://example.com/qa", "snippet": "qa"}],
            "chunks": [{"source_url": "https://example.com/qa", "text": "boundary value analysis", "score": 0.9}],
        }


class _MemoryRepoSpy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_prompt(self, user_input, normalized_input):
        _ = user_input
        _ = normalized_input
        self.calls.append("create_prompt")
        return "p1"

    def save_test_cases(self, prompt_id, test_cases_json, test_type):
        _ = prompt_id
        _ = test_cases_json
        _ = test_type
        self.calls.append("save_test_cases")
        return "tc1"

    def save_execution_result(self, test_case_id, status, error_message, screenshot_path, logs):
        _ = test_case_id
        _ = status
        _ = error_message
        _ = screenshot_path
        _ = logs
        self.calls.append("save_execution_result")
        return "er1"

    def record_fix_strategy(self, error_type, fix_strategy, success):
        _ = error_type
        _ = fix_strategy
        _ = success
        self.calls.append("record_fix_strategy")

    def list_fix_memory(self):
        return []


class _MemoryRepoAlwaysFail:
    def __getattr__(self, name):
        def _raise(*args, **kwargs):
            _ = name
            _ = args
            _ = kwargs
            raise RuntimeError("memory down")

        return _raise


class _TestcaseServiceStub:
    def to_scenarios(self, request: TestRequest) -> list[Scenario]:
        _ = request
        return [
            Scenario(
                id="adv-scn-1",
                title="Advanced generated",
                objective="functional",
                steps=[Step(id="adv-s1", action="goto", target="https://example.com")],
            )
        ]


class ExecutionOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_validation_rejects_empty_scenarios(self) -> None:
        orchestrator = ExecutionOrchestrator(delegate=_DelegateInvalidPreview())
        request = TestRequest(instruction="test login flow")
        with self.assertRaises(ValueError):
            await orchestrator.preview_cases(request)

    async def test_run_success_with_valid_delegate(self) -> None:
        orchestrator = ExecutionOrchestrator(delegate=_DelegateOK())
        request = TestRequest(instruction="test login flow")
        report, human = await orchestrator.run(request)
        self.assertEqual(report.status, "passed")
        self.assertEqual(human["summary"], "ok")

    async def test_run_retries_once_on_failure(self) -> None:
        delegate = _DelegateRetry()
        orchestrator = ExecutionOrchestrator(delegate=delegate, max_run_retries=1)
        request = TestRequest(instruction="test login flow")
        report, _ = await orchestrator.run(request)
        self.assertEqual(report.status, "passed")
        self.assertEqual(delegate.calls, 2)

    async def test_run_writes_through_to_memory_repository(self) -> None:
        repo = _MemoryRepoSpy()
        orchestrator = ExecutionOrchestrator(delegate=_DelegateOK(), memory_repo=repo)
        request = TestRequest(instruction="test login flow")
        report, _ = await orchestrator.run(request)
        self.assertEqual(report.status, "passed")
        self.assertIn("create_prompt", repo.calls)
        self.assertIn("save_test_cases", repo.calls)
        self.assertIn("save_execution_result", repo.calls)

    async def test_run_is_fail_open_when_memory_repository_fails(self) -> None:
        orchestrator = ExecutionOrchestrator(delegate=_DelegateOK(), memory_repo=_MemoryRepoAlwaysFail())
        request = TestRequest(instruction="test login flow")
        report, human = await orchestrator.run(request)
        self.assertEqual(report.status, "passed")
        self.assertEqual(human["summary"], "ok")

    async def test_preview_enriches_request_with_rag_when_enabled(self) -> None:
        delegate = _DelegateCaptureRequest()
        orchestrator = ExecutionOrchestrator(delegate=delegate, web_rag_service=_RAGServiceStub(), web_rag_enabled=True)
        request = TestRequest(instruction="test login flow", target_url="https://example.com")
        await orchestrator.preview_cases(request)
        assert delegate.seen_request is not None
        self.assertIn("rag_context", delegate.seen_request.test_data)
        self.assertIn("rag_sources", delegate.seen_request.test_data)

    async def test_preview_uses_advanced_testcase_service_when_enabled(self) -> None:
        delegate = _DelegateInvalidPreview()
        orchestrator = ExecutionOrchestrator(
            delegate=delegate,
            testcase_service=_TestcaseServiceStub(),
            advanced_testcase_generation_enabled=True,
        )
        request = TestRequest(instruction="test login flow")
        scenarios = await orchestrator.preview_cases(request)
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0].id, "adv-scn-1")


if __name__ == "__main__":
    unittest.main()
