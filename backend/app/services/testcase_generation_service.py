from __future__ import annotations

from dataclasses import dataclass

from app.api.schemas import Scenario, Step, TestRequest


@dataclass
class GeneratedTestCase:
    title: str
    steps: list[Step]
    expected_result: str
    priority: str
    case_type: str


class TestCaseGenerationService:
    """Advanced testcase generator (safe extension, fallback-compatible)."""

    def generate(self, request: TestRequest) -> list[GeneratedTestCase]:
        target_url = request.target_url or "about:blank"
        expected = request.test_data.get("expected_text", "dashboard is visible")
        username = request.test_data.get("username") or request.test_data.get("email") or "qa@example.com"
        password = request.test_data.get("password", "password123")

        functional_steps = [
            Step(id="adv-fn-s1", action="goto", target=target_url),
            Step(
                id="adv-fn-s2",
                action="type",
                target="input[type='email'], input[name='username'], input[id*='user']",
                value=username,
            ),
            Step(id="adv-fn-s3", action="type", target="input[type='password']", value=password),
            Step(id="adv-fn-s4", action="click", target="button[type='submit'], button:has-text('Login'), button:has-text('Sign in')"),
            Step(id="adv-fn-s5", action="assert_text", target="body", assertion=expected),
        ]
        negative_steps = [
            Step(id="adv-neg-s1", action="goto", target=target_url),
            Step(
                id="adv-neg-s2",
                action="type",
                target="input[type='email'], input[name='username'], input[id*='user']",
                value=username,
            ),
            Step(id="adv-neg-s3", action="type", target="input[type='password']", value=f"{password}_invalid"),
            Step(id="adv-neg-s4", action="click", target="button[type='submit'], button:has-text('Login'), button:has-text('Sign in')"),
            Step(id="adv-neg-s5", action="assert_text", target="body", assertion="invalid"),
        ]
        # Boundary/partition-inspired edge checks
        edge_steps = [
            Step(id="adv-edge-s1", action="goto", target=target_url),
            Step(id="adv-edge-s2", action="type", target="input[type='email'], input[name='username'], input[id*='user']", value=""),
            Step(id="adv-edge-s3", action="type", target="input[type='password']", value=""),
            Step(id="adv-edge-s4", action="click", target="button[type='submit'], button:has-text('Login'), button:has-text('Sign in')"),
            Step(id="adv-edge-s5", action="assert_text", target="body", assertion="required"),
        ]
        # Basic error-guessing security case
        security_steps = [
            Step(id="adv-sec-s1", action="goto", target=target_url),
            Step(
                id="adv-sec-s2",
                action="type",
                target="input[type='email'], input[name='username'], input[id*='user']",
                value="' OR '1'='1",
            ),
            Step(id="adv-sec-s3", action="type", target="input[type='password']", value="' OR '1'='1"),
            Step(id="adv-sec-s4", action="click", target="button[type='submit'], button:has-text('Login'), button:has-text('Sign in')"),
            Step(id="adv-sec-s5", action="assert_text", target="body", assertion="invalid"),
        ]

        return [
            GeneratedTestCase(
                title="Functional: valid authentication flow",
                steps=functional_steps,
                expected_result=expected,
                priority="P1",
                case_type="functional",
            ),
            GeneratedTestCase(
                title="Negative: invalid password rejection",
                steps=negative_steps,
                expected_result="User should see invalid credentials error",
                priority="P1",
                case_type="negative",
            ),
            GeneratedTestCase(
                title="Edge: empty credentials validation",
                steps=edge_steps,
                expected_result="Required field validation should be shown",
                priority="P2",
                case_type="edge",
            ),
            GeneratedTestCase(
                title="Security: injection-like input rejection",
                steps=security_steps,
                expected_result="System should reject malicious credential patterns",
                priority="P1",
                case_type="security",
            ),
        ]

    def to_scenarios(self, request: TestRequest) -> list[Scenario]:
        scenarios: list[Scenario] = []
        for idx, case in enumerate(self.generate(request), start=1):
            scenarios.append(
                Scenario(
                    id=f"adv-scn-{idx}",
                    title=case.title,
                    objective=f"[{case.case_type.upper()}][{case.priority}] {case.expected_result}",
                    steps=case.steps,
                )
            )
        return scenarios
