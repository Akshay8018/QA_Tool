from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryStore:
    successful_locators: dict[str, list[str]] = field(default_factory=dict)
    failed_patterns: dict[str, int] = field(default_factory=dict)
    fix_strategies: dict[str, str] = field(default_factory=dict)

    def record_success(self, step_id: str, locator: str) -> None:
        self.successful_locators.setdefault(step_id, []).append(locator)

    def record_failure(self, pattern: str) -> None:
        self.failed_patterns[pattern] = self.failed_patterns.get(pattern, 0) + 1

    def record_fix(self, issue: str, strategy: str) -> None:
        self.fix_strategies[issue] = strategy


memory_store = MemoryStore()
