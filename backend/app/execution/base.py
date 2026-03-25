from __future__ import annotations

from abc import ABC, abstractmethod

from app.api.schemas import ExecutionResult, Step


class BaseExecutionEngine(ABC):
    @abstractmethod
    async def execute_step(self, step: Step) -> ExecutionResult:
        raise NotImplementedError
