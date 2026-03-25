from __future__ import annotations

from typing import Any

from app.api.schemas import IntakeResponse
from app.services.chat_context_service import ChatContextService
from app.services.intake import IntakeService
from app.services.session_store import SessionRepository


def _is_yes(text: str) -> bool:
    t = text.strip().lower()
    return t in {"yes", "y", "ok", "okay", "proceed", "confirm", "approved"}


def _is_no(text: str) -> bool:
    t = text.strip().lower()
    return t in {"no", "n", "stop", "cancel", "reject"}


class ChatControllerService:
    """Minimal chat orchestration: session persistence + intake + flow hints.

    Does not replace the frontend state machine; provides a server-side path
    and suggested_next for clients that call POST /v1/chat/message.
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        intake_service: IntakeService | None = None,
    ) -> None:
        self._sessions = session_repository
        self._intake = intake_service or IntakeService()
        self._context = ChatContextService(session_repository=session_repository)

    def process_message(
        self,
        session_id: str,
        message: str,
        flow_stage: str | None = None,
    ) -> dict[str, Any] | None:
        saved = self._sessions.append_message(session_id, "user", message)
        if saved is None:
            return None

        ctx = self._context.build_context(session_id)
        if ctx is None:
            return None

        stage = (flow_stage or "idle").strip().lower()
        intake_result: IntakeResponse | None = None
        suggested_next = "none"
        reply = ""

        if stage in ("idle", "initial", "clarifying"):
            if len(message.strip()) < 5:
                reply = "Please provide more detail about what you want to test (at least 5 characters)."
                suggested_next = "user_input"
            else:
                intake_result = self._intake.analyze(message)
                if intake_result.needs_clarification and intake_result.questions:
                    reply = intake_result.questions[0].label
                    suggested_next = "clarify"
                else:
                    reply = (
                        "I have enough context. Should I generate all relevant functional and "
                        "non-functional test cases now? Reply yes/no."
                    )
                    suggested_next = "confirm_generate"
        elif stage == "confirm_generate":
            if _is_yes(message):
                reply = (
                    "Call POST /v1/tests/preview-cases with your instruction, clarification_answers, "
                    "execution_engine, and watch_execution to retrieve generated scenarios."
                )
                suggested_next = "preview_cases"
            elif _is_no(message):
                reply = "Please provide the missing or corrected details in your next message."
                suggested_next = "clarify"
            else:
                reply = "Reply yes to generate test cases, or no to adjust your requirements."
                suggested_next = "confirm_generate"
        elif stage == "review_cases":
            if _is_yes(message):
                reply = (
                    "Final confirmation: approve starting test execution? Reply yes/no. "
                    "If yes, call POST /v1/tests/run-stream with the same payload you used for preview."
                )
                suggested_next = "confirm_execute"
            elif _is_no(message):
                reply = "Please describe corrections; you can regenerate preview after updating context."
                suggested_next = "clarify"
            else:
                reply = "Are the generated test cases correct? Reply yes/no and optionally add corrections."
                suggested_next = "review_cases"
        elif stage == "confirm_execute":
            if _is_yes(message):
                reply = "Call POST /v1/tests/run-stream to execute tests and stream progress."
                suggested_next = "run_stream"
            elif _is_no(message):
                reply = "Execution cancelled. You can continue refining the conversation."
                suggested_next = "idle"
            else:
                reply = "Do you approve starting test execution now? Reply yes/no."
                suggested_next = "confirm_execute"
        elif stage == "executing":
            reply = "A run may be in progress. Check stream output or history when complete."
            suggested_next = "none"
        else:
            if len(message.strip()) >= 5:
                intake_result = self._intake.analyze(message)
                if intake_result.needs_clarification and intake_result.questions:
                    reply = intake_result.questions[0].label
                    suggested_next = "clarify"
                else:
                    reply = (
                        "I have enough context. Should I generate all relevant functional and "
                        "non-functional test cases now? Reply yes/no."
                    )
                    suggested_next = "confirm_generate"
            else:
                reply = "Please provide more detail about what you want to test."
                suggested_next = "user_input"

        self._sessions.append_message(session_id, "assistant", reply)

        ctx_final = self._context.build_context(session_id)
        summary = ctx_final["summary"] if ctx_final else ctx["summary"]
        count = ctx_final["message_count"] if ctx_final else ctx["message_count"]

        return {
            "reply": reply,
            "session_id": session_id,
            "context_summary": summary,
            "message_count": count,
            "intake": intake_result.model_dump(mode="json") if intake_result else None,
            "suggested_next": suggested_next,
        }
