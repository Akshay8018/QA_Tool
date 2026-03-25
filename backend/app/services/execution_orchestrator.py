from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.api.schemas import Scenario, TestRequest, TestRunReport
from app.core.config import settings
from app.services.orchestrator import TestOrchestrator
from app.services.qa_memory_repository import QAMemoryRepository, qa_memory_repository
from app.services.testcase_generation_service import TestCaseGenerationService
from app.services.web_rag import WebRAGService

logger = logging.getLogger(__name__)

EventSink = Callable[[dict], Awaitable[None]]


class ExecutionPlanValidator:
    def validate(self, scenarios: list[Scenario]) -> None:
        if not scenarios:
            raise ValueError("No scenarios generated for execution")
        seen_ids: set[str] = set()
        for scenario in scenarios:
            if not scenario.id.strip():
                raise ValueError("Scenario id cannot be empty")
            if scenario.id in seen_ids:
                raise ValueError(f"Duplicate scenario id found: {scenario.id}")
            seen_ids.add(scenario.id)
            if not scenario.steps:
                raise ValueError(f"Scenario has no steps: {scenario.id}")


class ExecutionOrchestrator:
    """Safe wrapper around existing TestOrchestrator.

    This class adds validation and guarded retry policy while delegating
    execution to the existing orchestration/execution engine path.
    """

    def __init__(
        self,
        delegate: TestOrchestrator | None = None,
        validator: ExecutionPlanValidator | None = None,
        max_run_retries: int = 1,
        memory_repo: QAMemoryRepository | None = None,
        web_rag_service: WebRAGService | None = None,
        web_rag_enabled: bool | None = None,
        testcase_service: TestCaseGenerationService | None = None,
        advanced_testcase_generation_enabled: bool | None = None,
    ) -> None:
        self.delegate = delegate or TestOrchestrator()
        self.validator = validator or ExecutionPlanValidator()
        self.max_run_retries = max_run_retries
        self.memory_repo = memory_repo or qa_memory_repository
        self.web_rag_service = web_rag_service or WebRAGService()
        self.web_rag_enabled = settings.web_rag_enabled if web_rag_enabled is None else web_rag_enabled
        self.testcase_service = testcase_service or TestCaseGenerationService()
        self.advanced_testcase_generation_enabled = (
            settings.advanced_testcase_generation_enabled
            if advanced_testcase_generation_enabled is None
            else advanced_testcase_generation_enabled
        )

    def _safe_memory_call(self, fn_name: str, *args: Any, **kwargs: Any) -> Any | None:
        try:
            fn = getattr(self.memory_repo, fn_name)
            return fn(*args, **kwargs)
        except Exception as exc:
            # Never block execution path for persistence issues.
            logger.warning("ExecutionOrchestrator memory write skipped fn=%s error=%s", fn_name, exc)
            return None

    async def _enrich_with_rag(self, request: TestRequest) -> TestRequest:
        if not self.web_rag_enabled:
            return request
        rag_payload = await self.web_rag_service.retrieve(request.instruction, top_k=5)
        merged_test_data = {
            **request.test_data,
            "rag_context": rag_payload.get("chunks", []),
            "rag_sources": rag_payload.get("sources", []),
        }
        return request.model_copy(update={"test_data": merged_test_data})

    async def preview_cases(self, request: TestRequest, apply_rag: bool = True) -> list[Scenario]:
        if apply_rag:
            request = await self._enrich_with_rag(request)
        if self.advanced_testcase_generation_enabled:
            scenarios = self.testcase_service.to_scenarios(request)
            self.validator.validate(scenarios)
            return scenarios
        scenarios = await self.delegate.preview_scenarios(request)
        self.validator.validate(scenarios)
        return scenarios

    async def run(self, request: TestRequest, event_sink: EventSink | None = None) -> tuple[TestRunReport, dict]:
        request = await self._enrich_with_rag(request)
        # Validate plan structure before execution to fail safely.
        scenarios = await self.preview_cases(request, apply_rag=False)
        logger.info("ExecutionOrchestrator validated scenarios count=%s", len(scenarios))
        prompt_id = self._safe_memory_call(
            "create_prompt",
            request.instruction,
            {"target_url": request.target_url, "test_data": request.test_data},
        )
        test_case_id: str | None = None
        if isinstance(prompt_id, str):
            test_case_id = self._safe_memory_call(
                "save_test_cases",
                prompt_id,
                {"scenarios": [s.model_dump(mode="json") for s in scenarios]},
                "generated",
            )

        last_error: Exception | None = None
        for attempt in range(self.max_run_retries + 1):
            try:
                if attempt > 0:
                    logger.warning("ExecutionOrchestrator retrying run attempt=%s", attempt + 1)
                report, human = await self.delegate.run(request, event_sink=event_sink)
                if isinstance(test_case_id, str):
                    for result in report.results:
                        self._safe_memory_call(
                            "save_execution_result",
                            test_case_id,
                            result.status,
                            result.details if result.status == "failed" else None,
                            None,
                            {
                                "step_id": result.step_id,
                                "locator_used": result.locator_used,
                                "retries": result.retries,
                                "root_cause": result.root_cause,
                            },
                        )
                        if result.status == "failed":
                            self._safe_memory_call(
                                "record_fix_strategy",
                                result.root_cause or "unknown_error",
                                {
                                    "step_id": result.step_id,
                                    "locator_used": result.locator_used,
                                    "details": result.details,
                                },
                                False,
                            )
                return report, human
            except Exception as exc:
                last_error = exc
                logger.exception("ExecutionOrchestrator run failed attempt=%s error=%s", attempt + 1, exc)
                if attempt >= self.max_run_retries:
                    raise
        raise RuntimeError(f"Execution failed unexpectedly: {last_error}")
