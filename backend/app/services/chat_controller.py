from __future__ import annotations

from typing import Any

from app.api.schemas import IntakeResponse
from app.core.config import settings
from app.services.chat_context_service import ChatContextService
from app.services.intake import IntakeService
from app.services.web_rag import WebRAGService
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
        web_rag_service: WebRAGService | None = None,
        web_rag_enabled: bool | None = None,
    ) -> None:
        self._sessions = session_repository
        self._intake = intake_service or IntakeService()
        self._context = ChatContextService(session_repository=session_repository)
        self._web_rag = web_rag_service or WebRAGService()
        self._web_rag_enabled = settings.web_rag_enabled if web_rag_enabled is None else web_rag_enabled

    async def _build_web_insights(self, query: str) -> str:
        if not self._web_rag_enabled:
            return ""
        try:
            rag_payload = await self._web_rag.retrieve(query, top_k=settings.web_rag_search_max_results)
            sources = rag_payload.get("sources", []) or []
            chunks = rag_payload.get("chunks", []) or []

            source_lines: list[str] = []
            for s in sources[:2]:
                if not isinstance(s, dict):
                    continue
                url = str(s.get("url", "")).strip()
                title = str(s.get("title", "")).strip()
                if url:
                    source_lines.append(f"- {title or url} ({url})")

            key_lines: list[str] = []
            for c in chunks[:3]:
                if not isinstance(c, dict):
                    continue
                text = str(c.get("text", "")).strip().replace("\n", " ")
                if text:
                    key_lines.append(f"- {text[:180]}...")

            if not source_lines and not key_lines:
                # Fail-open fallback: provide best-practice QA guidance even if retrieval returns nothing.
                return (
                    "\n\nWeb QA insights (fallback – offline best practices):\n"
                    "- Define the target URL and required auth state (logged-in vs public pages).\n"
                    "- Generate functional + negative + edge + basic security cases.\n"
                    "- Validate UI outcomes (visible text/state) and key client-side errors (400/401/422).\n"
                    "- For login flows, also include invalid credential + empty-field + rate/lockout scenarios.\n"
                )

            parts: list[str] = []
            parts.append("Web QA insights (from knowledge sources):")
            if source_lines:
                parts.append("Sources:\n" + "\n".join(source_lines))
            if key_lines:
                parts.append("Key points:\n" + "\n".join(key_lines))
            return "\n\n" + "\n".join(parts)
        except Exception:
            # Fail-open: still return a normal chat flow with deterministic guidance.
            return (
                "\n\nWeb QA insights (fallback – offline best practices):\n"
                "- Identify test data inputs (valid/invalid/empty).\n"
                "- Cover functional journey + negative validations.\n"
                "- Add edge cases around timing, retries, and partial failures.\n"
                "- Include basic security checks for injection-like input patterns.\n"
            )

    async def process_message(
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
                    question = intake_result.questions[0].label
                    suggested_next = "clarify"
                    if self._web_rag_enabled:
                        query = str(intake_result.normalized_prompt) or message
                        web_block = await self._build_web_insights(query)
                        if web_block:
                            reply = web_block + "\n\n" + question
                        else:
                            reply = question
                    else:
                        reply = question
                else:
                    reply = "I have enough context."
                    if self._web_rag_enabled:
                        query = str(intake_result.normalized_prompt) or message
                        web_block = await self._build_web_insights(query)
                        reply += web_block
                    reply += " Should I generate all relevant functional and non-functional test cases now? Reply yes/no."
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
