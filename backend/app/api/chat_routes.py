from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException

from app.api.schemas import ChatMessageRequest, ChatMessageResponse
from app.services.chat_controller import ChatControllerService
from app.services.session_store import session_store

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post("/message", response_model=ChatMessageResponse)
async def post_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    controller = ChatControllerService(session_repository=session_store)
    result = controller.process_message(
        session_id=request.session_id,
        message=request.message,
        flow_stage=request.flow_stage,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return ChatMessageResponse.model_validate(result)
