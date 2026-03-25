from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    ChatContextResponse,
    IntakeRequest,
    IntakeResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionMessageRequest,
    SessionMessageResponse,
    TestRequest,
    TestRunResponse,
)
from app.services.execution_orchestrator import ExecutionOrchestrator
from app.services.chat_context_service import ChatContextService
from app.services.intake import IntakeService
from app.services.run_history import run_history_store
from app.services.session_store import session_store
from app.services.tasks import run_ai_qa_test

router = APIRouter(prefix="/v1/tests", tags=["tests"])


@router.post("/intake", response_model=IntakeResponse)
async def intake(request: IntakeRequest) -> IntakeResponse:
    service = IntakeService()
    return service.analyze(request.instruction)


@router.post("/run", response_model=TestRunResponse)
async def run_test(request: TestRequest) -> TestRunResponse:
    orchestrator = ExecutionOrchestrator()
    report, human = await orchestrator.run(request)
    run_history_store.save(report.model_dump(mode="json"), human, request.instruction)
    return TestRunResponse(run_id=report.run_id, status=report.status, started_at=report.started_at)


@router.post("/enqueue")
async def enqueue_test(request: TestRequest) -> dict:
    task = run_ai_qa_test.delay(request.model_dump())
    return {"task_id": task.id, "status": "queued"}


@router.get("/task/{task_id}")
async def get_task(task_id: str) -> dict:
    result = run_ai_qa_test.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "state": result.state,
        "result": result.result if result.successful() else None,
    }


@router.post("/run-with-report")
async def run_with_report(request: TestRequest) -> dict:
    orchestrator = ExecutionOrchestrator()
    report, human = await orchestrator.run(request)
    run_history_store.save(report.model_dump(mode="json"), human, request.instruction)
    return {
        "json_report": report.model_dump(mode="json"),
        "human_report": human,
    }


@router.post("/preview-cases")
async def preview_cases(request: TestRequest) -> dict:
    orchestrator = ExecutionOrchestrator()
    scenarios = await orchestrator.preview_cases(request)
    return {
        "scenario_count": len(scenarios),
        "scenarios": [s.model_dump(mode="json") for s in scenarios],
    }


@router.post("/run-stream")
async def run_stream(request: TestRequest) -> StreamingResponse:
    async def stream():
        queue: asyncio.Queue[dict] = asyncio.Queue()
        orchestrator = ExecutionOrchestrator()

        async def sink(event: dict) -> None:
            await queue.put(event)

        task = asyncio.create_task(orchestrator.run(request, event_sink=sink))

        try:
            while True:
                if task.done() and queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                    yield json.dumps({"type": "log", "event": event}) + "\n"
                except asyncio.TimeoutError:
                    continue

            report, human = await task
            run_history_store.save(report.model_dump(mode="json"), human, request.instruction)
            yield json.dumps(
                {
                    "type": "final",
                    "json_report": report.model_dump(mode="json"),
                    "human_report": human,
                }
            ) + "\n"
        except Exception as exc:
            if not task.done():
                task.cancel()
            message = str(exc).strip() or f"{exc.__class__.__name__}: execution failed"
            yield json.dumps({"type": "error", "message": message}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/history")
async def list_history() -> dict:
    return {"runs": run_history_store.list_runs()}


@router.get("/history/{run_id}")
async def get_history(run_id: str) -> dict:
    run = run_history_store.get(run_id)
    if not run:
        return {"error": "run_not_found"}
    return run


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    created = session_store.create_session(request.title)
    return SessionCreateResponse.model_validate(created)


@router.get("/sessions")
async def list_sessions() -> dict:
    return {"sessions": session_store.list_sessions()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return session


@router.post("/sessions/{session_id}/messages", response_model=SessionMessageResponse)
async def add_session_message(session_id: str, request: SessionMessageRequest) -> SessionMessageResponse:
    message = session_store.append_message(session_id=session_id, role=request.role, text=request.text)
    if message is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return SessionMessageResponse.model_validate(message)


@router.get("/sessions/{session_id}/context", response_model=ChatContextResponse)
async def get_session_context(session_id: str) -> ChatContextResponse:
    context_service = ChatContextService(session_repository=session_store)
    context = context_service.build_context(session_id)
    if context is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return ChatContextResponse.model_validate(context)
