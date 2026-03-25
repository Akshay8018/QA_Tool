from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from app.llm.providers import AnthropicProvider, LLMProvider, OllamaProvider, OpenAIProvider

logger = logging.getLogger(__name__)


@dataclass
class RoutedModel:
    provider: str
    model: str


@dataclass
class ProviderAttempt:
    provider: str
    status: str
    latency_ms: int
    error: str | None = None


class LLMRouter:
    def __init__(self) -> None:
        self.providers: list[LLMProvider] = [OpenAIProvider(), AnthropicProvider(), OllamaProvider()]

    def pick_best(self, priority: str = "balanced") -> LLMProvider:
        # Score lower-is-better: combines cost and latency in a tunable way.
        if priority == "cost":
            key = lambda p: p.est_cost_per_1k * 100
        elif priority == "speed":
            key = lambda p: p.est_latency_ms
        else:
            key = lambda p: (p.est_cost_per_1k * 40) + (p.est_latency_ms / 100)
        return sorted(self.providers, key=key)[0]

    def health(self) -> list[dict[str, object]]:
        return [
            {
                "provider": p.name,
                "model": p.model_name,
                "configured": p.is_configured(),
                "est_cost_per_1k": p.est_cost_per_1k,
                "est_latency_ms": p.est_latency_ms,
            }
            for p in self.providers
        ]

    async def complete_with_fallback(self, prompt: str, priority: str = "balanced") -> tuple[str, RoutedModel]:
        ordered = sorted(
            self.providers,
            key=lambda p: (p.est_cost_per_1k * 40) + (p.est_latency_ms / 100),
        )
        if priority == "speed":
            ordered = sorted(self.providers, key=lambda p: p.est_latency_ms)
        elif priority == "cost":
            ordered = sorted(self.providers, key=lambda p: p.est_cost_per_1k)

        attempts: list[ProviderAttempt] = []
        last_error: Exception | None = None
        available = [p for p in ordered if p.is_configured()]
        if not available:
            available = ordered
        for provider in ordered:
            if provider not in available:
                attempts.append(
                    ProviderAttempt(provider=provider.name, status="skipped_unconfigured", latency_ms=0, error=None)
                )
                continue
            try:
                started = perf_counter()
                text = await provider.complete(prompt)
                latency_ms = int((perf_counter() - started) * 1000)
                attempts.append(ProviderAttempt(provider=provider.name, status="success", latency_ms=latency_ms, error=None))
                logger.info(
                    "LLM route selected provider=%s model=%s latency_ms=%s attempts=%s",
                    provider.name,
                    provider.model_name,
                    latency_ms,
                    len(attempts),
                )
                return text, RoutedModel(provider=provider.name, model=provider.model_name)
            except Exception as exc:  # pragma: no cover
                last_error = exc
                latency_ms = int((perf_counter() - started) * 1000)
                attempts.append(
                    ProviderAttempt(provider=provider.name, status="failed", latency_ms=latency_ms, error=str(exc))
                )
                logger.warning("Provider failed provider=%s latency_ms=%s error=%s", provider.name, latency_ms, exc)
        logger.error("All LLM providers failed attempts=%s", [a.__dict__ for a in attempts])
        raise RuntimeError(f"All LLM providers failed: {last_error}")
