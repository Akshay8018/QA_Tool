from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EngineType(str, Enum):
    playwright = "playwright"
    selenium = "selenium"
    api = "api"


class TestRequest(BaseModel):
    instruction: str = Field(..., min_length=5)
    target_url: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    execution_engine: EngineType = EngineType.playwright
    watch_execution: bool = False
    clarification_answers: dict[str, str] = Field(default_factory=dict)
    test_data: dict[str, Any] = Field(default_factory=dict)


class IntakeRequest(BaseModel):
    instruction: str = Field(..., min_length=5)


class IntakeQuestion(BaseModel):
    id: str
    label: str
    placeholder: str | None = None


class IntakeResponse(BaseModel):
    needs_clarification: bool
    normalized_prompt: str
    detected: dict[str, Any]
    questions: list[IntakeQuestion] = Field(default_factory=list)


class Step(BaseModel):
    id: str
    action: str
    target: str | None = None
    value: str | None = None
    assertion: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Scenario(BaseModel):
    id: str
    title: str
    objective: str
    steps: list[Step]


class ExecutionResult(BaseModel):
    step_id: str
    status: str
    details: str
    locator_used: str | None = None
    retries: int = 0
    root_cause: str | None = None


class TestRunResponse(BaseModel):
    run_id: str
    status: str
    started_at: datetime


class TestRunReport(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    finished_at: datetime
    scenarios: list[Scenario]
    results: list[ExecutionResult]
    root_cause_analysis: dict[str, Any]
    recommendations: list[str]


class SessionCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class SessionCreateResponse(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class SessionMessageRequest(BaseModel):
    role: str = Field(..., min_length=1, max_length=20)
    text: str = Field(..., min_length=1)


class SessionMessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: str
    text: str
    created_at: datetime


class ChatContextResponse(BaseModel):
    session_id: str
    message_count: int
    last_user_message: str | None = None
    summary: str
    context_window: list[dict[str, str]] = Field(default_factory=list)


class ChatMessageRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    flow_stage: str | None = Field(
        default=None,
        description="Optional: idle|clarifying|confirm_generate|review_cases|confirm_execute|executing",
    )


class ChatMessageResponse(BaseModel):
    reply: str
    session_id: str
    context_summary: str
    message_count: int
    intake: dict[str, Any] | None = None
    suggested_next: str
