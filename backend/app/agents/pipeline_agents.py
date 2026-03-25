from __future__ import annotations

import json
import logging
from typing import Any

from app.api.schemas import ExecutionResult, Scenario, Step, TestRequest
from app.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class PlannerAgent:
    def __init__(self, router: LLMRouter) -> None:
        self.router = router

    def _fallback_plan(self, request: TestRequest, raw_plan: str, route: dict[str, Any]) -> dict[str, Any]:
        return {
            "route": route,
            "scenarios": [
                {
                    "id": "scn-1",
                    "title": "Core Journey",
                    "objective": request.instruction,
                    "risk_level": "medium",
                    "raw_plan": raw_plan,
                }
            ],
        }

    def _extract_json_payload(self, text: str) -> dict[str, Any] | None:
        candidate = text.strip()
        if "```json" in candidate:
            candidate = candidate.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in candidate:
            candidate = candidate.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except Exception:
            return None
        return None

    async def run(self, request: TestRequest) -> dict[str, Any]:
        prompt = (
            "You are a QA planning agent. Produce STRICT JSON only.\n"
            "Schema:\n"
            '{ "scenarios": [ { "id": "scn-1", "title": "string", "objective": "string", "risk_level": "low|medium|high" } ] }\n'
            f"Instruction: {request.instruction}\n"
            f"Target URL: {request.target_url or 'target URL from instruction'}\n"
            "Output JSON only. No markdown."
        )
        llm_text, route = await self.router.complete_with_fallback(prompt)
        route_data = route.__dict__
        parsed = self._extract_json_payload(llm_text)
        if not parsed:
            logger.warning("Planner returned non-JSON output; falling back to deterministic plan")
            return self._fallback_plan(request, llm_text, route_data)

        raw_scenarios = parsed.get("scenarios", [])
        if not isinstance(raw_scenarios, list) or not raw_scenarios:
            logger.warning("Planner JSON missing scenarios; falling back to deterministic plan")
            return self._fallback_plan(request, llm_text, route_data)

        scenarios: list[dict[str, Any]] = []
        for idx, item in enumerate(raw_scenarios, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or f"Scenario {idx}")
            objective = str(item.get("objective") or request.instruction)
            scenarios.append(
                {
                    "id": str(item.get("id") or f"scn-{idx}"),
                    "title": title,
                    "objective": objective,
                    "risk_level": str(item.get("risk_level") or "medium"),
                    "raw_plan": llm_text,
                }
            )
        if not scenarios:
            return self._fallback_plan(request, llm_text, route_data)
        return {"route": route_data, "scenarios": scenarios}


class ScenarioDecomposerAgent:
    async def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        decomposed = []
        for scenario in plan["scenarios"]:
            decomposed.append({**scenario, "step_groups": ["setup", "actions", "assertions"]})
        return {"scenarios": decomposed, "route": plan.get("route", {})}


class StepGeneratorAgent:
    def _steps_from_flow(self, target_url: str, flow_steps: list[str], expected_result: str) -> list[Step]:
        steps: list[Step] = [Step(id="flow-s1", action="goto", target=target_url)]
        idx = 2
        for raw in flow_steps:
            text = raw.strip()
            lowered = text.lower()
            if not text:
                continue

            if any(k in lowered for k in ("open ", "go to", "navigate")):
                continue
            if any(k in lowered for k in ("enter", "type", "input")):
                if "password" in lowered:
                    steps.append(Step(id=f"flow-s{idx}", action="type", target="input[type='password']", value="password123"))
                elif "user" in lowered or "email" in lowered:
                    steps.append(
                        Step(
                            id=f"flow-s{idx}",
                            action="type",
                            target="input[type='email'], input[name='username'], input[id*='user']",
                            value="qa@example.com",
                        )
                    )
                else:
                    steps.append(Step(id=f"flow-s{idx}", action="type", target="input, textarea", value="test-data"))
                idx += 1
                continue
            if any(k in lowered for k in ("click", "submit", "sign in", "login", "log in")):
                steps.append(
                    Step(
                        id=f"flow-s{idx}",
                        action="click",
                        target="button[type='submit'], button:has-text('Login'), button:has-text('Sign in')",
                    )
                )
                idx += 1
                continue
            if any(k in lowered for k in ("verify", "validate", "check", "assert")):
                phrase = text.split(" ", 1)[1] if " " in text else text
                steps.append(Step(id=f"flow-s{idx}", action="assert_text", target="body", assertion=phrase))
                idx += 1

        steps.append(Step(id=f"flow-s{idx}", action="assert_text", target="body", assertion=expected_result))
        return steps

    def _login_steps(self, prefix: str, target_url: str, user_value: str, password: str, expected_text: str) -> list[Step]:
        return [
            Step(id=f"{prefix}-s1", action="goto", target=target_url),
            Step(id=f"{prefix}-s2", action="type", target="input[type='email'], input[name='username'], input[id*='user']", value=user_value),
            Step(id=f"{prefix}-s3", action="type", target="input[type='password']", value=password),
            Step(id=f"{prefix}-s4", action="click", target="button[type='submit'], button:has-text('Login'), button:has-text('Sign in')"),
            Step(id=f"{prefix}-s5", action="assert_text", target="body", assertion=expected_text),
        ]

    async def run(self, request: TestRequest, decomposed: dict[str, Any]) -> list[Scenario]:
        generated: list[Scenario] = []
        target_url = request.target_url or "about:blank"
        username = request.test_data.get("username") or request.test_data.get("email") or "qa@example.com"
        password = request.test_data.get("password", "password123")
        expected_text = request.test_data.get("expected_text", "dashboard")
        flow_steps_raw = request.test_data.get("flow_steps")
        expected_result = request.test_data.get("expected_result", expected_text)

        if isinstance(flow_steps_raw, str):
            flow_steps = [s.strip() for s in flow_steps_raw.split(",") if s.strip()]
        elif isinstance(flow_steps_raw, list):
            flow_steps = [str(s).strip() for s in flow_steps_raw if str(s).strip()]
        else:
            flow_steps = []

        if flow_steps:
            generated.append(
                Scenario(
                    id="scn-custom-flow",
                    title="User-defined flow execution",
                    objective=request.test_data.get("business_goal", request.instruction),
                    steps=self._steps_from_flow(target_url, flow_steps, expected_result),
                )
            )
            return generated

        if request.test_data.get("login_case_matrix"):
            generated.append(
                Scenario(
                    id="scn-valid-login",
                    title="Login with valid credentials",
                    objective="Verify successful login with valid credentials",
                    steps=self._login_steps("valid", target_url, username, password, expected_text),
                )
            )
            generated.append(
                Scenario(
                    id="scn-invalid-password",
                    title="Login with invalid password",
                    objective="Verify login fails for invalid password",
                    steps=self._login_steps("invalid-pwd", target_url, username, f"{password}_invalid", "invalid"),
                )
            )
            generated.append(
                Scenario(
                    id="scn-invalid-username",
                    title="Login with invalid username",
                    objective="Verify login fails for unknown username",
                    steps=self._login_steps("invalid-user", target_url, f"{username}_invalid", password, "invalid"),
                )
            )
            generated.append(
                Scenario(
                    id="scn-empty-credentials",
                    title="Login with empty credentials",
                    objective="Verify validation message for blank credentials",
                    steps=self._login_steps("blank", target_url, "", "", "required"),
                )
            )
            return generated

        for raw in decomposed["scenarios"]:
            steps = self._login_steps("core", target_url, username, password, expected_text)
            generated.append(
                Scenario(
                    id=raw["id"],
                    title=raw["title"],
                    objective=raw["objective"],
                    steps=steps,
                )
            )
        return generated


class ObserverAgent:
    async def run(self, step: Step, result: ExecutionResult) -> dict[str, Any]:
        logger.info("Observed step=%s status=%s details=%s", step.id, result.status, result.details)
        return {
            "step_id": step.id,
            "status": result.status,
            "details": result.details,
            "locator_used": result.locator_used,
        }


class ReflectionAgent:
    async def run(self, failure: ExecutionResult) -> dict[str, Any]:
        return {
            "retry_recommended": True,
            "alternate_locators": [
                failure.locator_used,
                "text=Sign in",
                "xpath=//button[contains(., 'Sign in') or contains(., 'Login')]",
                "css=button:has-text('Sign in')",
            ],
            "adaptive_wait_ms": 2000,
            "reasoning": f"Initial locator unstable. Attempt fallback chain for step {failure.step_id}.",
        }
