from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.agents.pipeline_agents import (
    ObserverAgent,
    PlannerAgent,
    ReflectionAgent,
    ScenarioDecomposerAgent,
    StepGeneratorAgent,
)
from app.api.schemas import EngineType, ExecutionResult, TestRequest, TestRunReport
from app.core.config import settings
from app.execution.api_engine import APIExecutionEngine
from app.execution.playwright_engine import PlaywrightExecutionEngine
from app.execution.selenium_engine import SeleniumExecutionEngine
from app.llm.router import LLMRouter
from app.memory.store import memory_store
from app.reports.generator import ReportGenerator
from app.services.prompt_parser import PromptParser

logger = logging.getLogger(__name__)


EventSink = Callable[[dict], Awaitable[None]]


class TestOrchestrator:
    def __init__(self) -> None:
        router = LLMRouter()
        self.planner = PlannerAgent(router)
        self.decomposer = ScenarioDecomposerAgent()
        self.step_generator = StepGeneratorAgent()
        self.observer = ObserverAgent()
        self.reflection = ReflectionAgent()
        self.report_generator = ReportGenerator()
        self.prompt_parser = PromptParser()

    def _engine_for(self, request: TestRequest):
        engine = request.execution_engine
        if engine == EngineType.playwright:
            return PlaywrightExecutionEngine(
                max_heal_attempts=settings.max_heal_attempts,
                watch_execution=request.watch_execution,
            )
        if engine == EngineType.selenium:
            return SeleniumExecutionEngine()
        return APIExecutionEngine()

    async def _emit(self, event_sink: EventSink | None, event: dict) -> None:
        if event_sink is not None:
            await event_sink(event)

    def _normalize_request(self, request: TestRequest) -> TestRequest:
        parsed = self.prompt_parser.parse(request.instruction)
        clarification = {k: v for k, v in request.clarification_answers.items() if v}
        target_url = request.target_url or clarification.get("target_url") or parsed.target_url
        combined_test_data = {**parsed.test_data, **clarification, **request.test_data}
        return request.model_copy(update={"target_url": target_url, "test_data": combined_test_data})

    async def preview_scenarios(self, request: TestRequest) -> list:
        request = self._normalize_request(request)
        plan = await self.planner.run(request)
        decomposed = await self.decomposer.run(plan)
        return await self.step_generator.run(request, decomposed)

    async def run(self, request: TestRequest, event_sink: EventSink | None = None) -> tuple[TestRunReport, dict]:
        request = self._normalize_request(request)

        run_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        await self._emit(
            event_sink,
            {
                "type": "run_started",
                "run_id": run_id,
                "started_at": started_at.isoformat(),
                "target_url": request.target_url,
                "engine": request.execution_engine.value,
            },
        )

        if not request.target_url:
            fail_result = ExecutionResult(
                step_id="input-validation",
                status="failed",
                details="No URL detected in prompt. Include a URL like https://example.com in your instruction.",
                root_cause="Missing target URL in instruction",
            )
            finished_at = datetime.now(timezone.utc)
            report = TestRunReport(
                run_id=run_id,
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                scenarios=[],
                results=[fail_result],
                root_cause_analysis={"failed_steps": {"input-validation": "Invalid test prompt input"}},
                recommendations=[
                    "Add target URL directly in prompt text.",
                    "Example: 'Open https://example.com and login using {\"email\":\"qa@example.com\"}'.",
                ],
            )
            human = self.report_generator.generate(report)
            await self._emit(
                event_sink,
                {
                    "type": "run_finished",
                    "run_id": report.run_id,
                    "status": report.status,
                    "finished_at": finished_at.isoformat(),
                },
            )
            return report, human

        plan = await self.planner.run(request)
        await self._emit(
            event_sink,
            {
                "type": "planner_completed",
                "run_id": run_id,
                "route": plan.get("route", {}),
                "scenario_blueprints": len(plan.get("scenarios", [])),
            },
        )
        decomposed = await self.decomposer.run(plan)
        await self._emit(event_sink, {"type": "decomposer_completed", "run_id": run_id})
        scenarios = await self.step_generator.run(request, decomposed)
        await self._emit(
            event_sink,
            {
                "type": "scenario_generated",
                "run_id": run_id,
                "scenario_count": len(scenarios),
                "step_count": sum(len(s.steps) for s in scenarios),
                "scenarios": [s.title for s in scenarios],
            },
        )

        engine = self._engine_for(request)
        results: list[ExecutionResult] = []
        if isinstance(engine, PlaywrightExecutionEngine):
            await engine.start_session()

        for scenario in scenarios:
            await self._emit(
                event_sink,
                {
                    "type": "scenario_started",
                    "run_id": run_id,
                    "scenario_id": scenario.id,
                    "scenario_title": scenario.title,
                },
            )
            for step in scenario.steps:
                await self._emit(
                    event_sink,
                    {
                        "type": "step_started",
                        "run_id": run_id,
                        "scenario_id": scenario.id,
                        "step_id": step.id,
                        "action": step.action,
                        "target": step.target,
                    },
                )
                result = await engine.execute_step(step)
                _ = await self.observer.run(step, result)

                if result.status == "passed" and result.locator_used:
                    memory_store.record_success(step.id, result.locator_used)
                else:
                    memory_store.record_failure(result.details)
                    reflection = await self.reflection.run(result)
                    memory_store.record_fix(result.step_id, reflection["reasoning"])
                    await self._emit(
                        event_sink,
                        {
                            "type": "self_heal_analysis",
                            "run_id": run_id,
                            "step_id": result.step_id,
                            "reasoning": reflection["reasoning"],
                            "alternate_locators": reflection["alternate_locators"],
                        },
                    )

                # Keep system resilient by continuing execution and collecting failures.
                results.append(result)
                await self._emit(
                    event_sink,
                    {
                        "type": "step_finished",
                        "run_id": run_id,
                        "scenario_id": scenario.id,
                        "step_id": result.step_id,
                        "status": result.status,
                        "details": result.details,
                        "locator_used": result.locator_used,
                        "retries": result.retries,
                        "root_cause": result.root_cause,
                    },
                )

        try:
            finished_at = datetime.now(timezone.utc)
            root_causes = {}
            for r in results:
                if r.status == "failed":
                    root_causes[r.step_id] = self.report_generator.classify_failure(r)

            report = TestRunReport(
                run_id=run_id,
                status="passed" if all(r.status == "passed" for r in results) else "failed",
                started_at=started_at,
                finished_at=finished_at,
                scenarios=scenarios,
                results=results,
                root_cause_analysis={
                    "failed_steps": root_causes,
                    "memory_snapshot": {
                        "successful_locators": memory_store.successful_locators,
                        "failed_patterns": memory_store.failed_patterns,
                    },
                },
                recommendations=[
                    "Stabilize data-test-id attributes for critical actions.",
                    "Add API-level health assertions before UI actions.",
                    "Use environment-specific adaptive waits for heavy dashboards.",
                ],
            )
            human = self.report_generator.generate(report)
            logger.info("Run completed run_id=%s status=%s", report.run_id, report.status)
            await self._emit(
                event_sink,
                {
                    "type": "run_finished",
                    "run_id": report.run_id,
                    "status": report.status,
                    "finished_at": finished_at.isoformat(),
                },
            )
            return report, human
        finally:
            if isinstance(engine, PlaywrightExecutionEngine):
                await engine.close_session()
