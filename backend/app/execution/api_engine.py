from __future__ import annotations

import asyncio

from app.api.schemas import ExecutionResult, Step
from app.execution.base import BaseExecutionEngine


class APIExecutionEngine(BaseExecutionEngine):
    async def execute_step(self, step: Step) -> ExecutionResult:
        await asyncio.sleep(0.05)
        return ExecutionResult(step_id=step.id, status="passed", details="API step executed", locator_used=step.target)
