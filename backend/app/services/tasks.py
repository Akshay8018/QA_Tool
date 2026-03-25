from __future__ import annotations

import asyncio

from app.api.schemas import TestRequest
from app.services.orchestrator import TestOrchestrator
from app.services.queue import celery_app


@celery_app.task(name="run_ai_qa_test")
def run_ai_qa_test(payload: dict):
    request = TestRequest(**payload)
    orchestrator = TestOrchestrator()
    report, human = asyncio.run(orchestrator.run(request))
    return {
        "json_report": report.model_dump(mode="json"),
        "human_report": human,
    }
