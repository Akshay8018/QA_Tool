from __future__ import annotations

from dataclasses import dataclass

from app.services.session_store import SessionRepository


@dataclass
class ChatContextService:
    session_repository: SessionRepository
    max_context_messages: int = 12

    def build_context(self, session_id: str) -> dict | None:
        session = self.session_repository.get_session(session_id)
        if session is None:
            return None

        messages = session.get("messages", [])
        tail = messages[-self.max_context_messages :]
        context_window = [{"role": str(m.get("role", "")), "text": str(m.get("text", ""))} for m in tail]

        user_messages = [m for m in messages if str(m.get("role", "")).lower() == "user"]
        last_user_message = str(user_messages[-1].get("text")) if user_messages else None

        summary = self._build_summary(messages)
        return {
            "session_id": session_id,
            "message_count": len(messages),
            "last_user_message": last_user_message,
            "summary": summary,
            "context_window": context_window,
        }

    def _build_summary(self, messages: list[dict]) -> str:
        if not messages:
            return "No conversation yet."

        user_count = sum(1 for m in messages if str(m.get("role", "")).lower() == "user")
        assistant_count = sum(1 for m in messages if str(m.get("role", "")).lower() == "assistant")
        system_count = sum(1 for m in messages if str(m.get("role", "")).lower() == "system")

        recent_texts = [str(m.get("text", "")).strip() for m in messages[-3:] if str(m.get("text", "")).strip()]
        recent_snippet = " | ".join(t[:120] for t in recent_texts)
        if not recent_snippet:
            recent_snippet = "No recent content."

        return (
            f"Session has {len(messages)} messages "
            f"(user={user_count}, assistant={assistant_count}, system={system_count}). "
            f"Recent: {recent_snippet}"
        )
