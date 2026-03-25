from __future__ import annotations

import asyncio
import logging
import sys
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat_routes import router as chat_router
from app.api.routes import router as test_router
from app.core.config import settings
from app.core.logging import configure_logging, request_id_ctx_var
from app.llm.router import LLMRouter

configure_logging()
logger = logging.getLogger(__name__)

# Playwright requires subprocess support on Windows event loop.
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(test_router)
app.include_router(chat_router)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    token = request_id_ctx_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_ctx_var.reset(token)
    response.headers["x-request-id"] = request_id
    logger.info("request method=%s path=%s status=%s", request.method, request.url.path, response.status_code)
    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/llm")
async def llm_health() -> dict:
    router = LLMRouter()
    providers = router.health()
    configured_count = sum(1 for p in providers if p.get("configured"))
    return {
        "status": "ok" if configured_count > 0 else "degraded",
        "configured_provider_count": configured_count,
        "providers": providers,
    }
