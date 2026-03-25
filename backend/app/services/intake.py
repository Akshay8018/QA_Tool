from __future__ import annotations

from app.api.schemas import IntakeQuestion, IntakeResponse
from app.services.prompt_parser import PromptParser


class IntakeService:
    def __init__(self) -> None:
        self.parser = PromptParser()

    def analyze(self, instruction: str) -> IntakeResponse:
        parsed = self.parser.parse(instruction)
        questions: list[IntakeQuestion] = []

        if not parsed.target_url:
            questions.append(
                IntakeQuestion(
                    id="target_url",
                    label="What is the exact URL to test?",
                    placeholder="https://example.com/login",
                )
            )

        if not parsed.test_data.get("business_goal"):
            questions.append(
                IntakeQuestion(
                    id="business_goal",
                    label="What is the business goal of this flow?",
                    placeholder="For example: user logs in and sees dashboard",
                )
            )

        if not parsed.test_data.get("flow_steps"):
            questions.append(
                IntakeQuestion(
                    id="flow_steps",
                    label="List the exact steps to execute (comma-separated).",
                    placeholder="open login page, enter username, enter password, click sign in, verify dashboard",
                )
            )

        if not parsed.test_data.get("expected_result"):
            questions.append(
                IntakeQuestion(
                    id="expected_result",
                    label="What should be validated at the end?",
                    placeholder="Dashboard visible and welcome message shown",
                )
            )

        return IntakeResponse(
            needs_clarification=len(questions) > 0,
            normalized_prompt=instruction.strip(),
            detected={
                "target_url": parsed.target_url,
                "test_data": parsed.test_data,
            },
            questions=questions,
        )
