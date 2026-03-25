from __future__ import annotations

from abc import ABC, abstractmethod
import json

import httpx

from app.core.config import settings


class LLMProvider(ABC):
    name: str
    est_cost_per_1k: float
    est_latency_ms: int
    model_name: str = "auto"

    def is_configured(self) -> bool:
        return True

    @abstractmethod
    async def complete(self, prompt: str) -> str:
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    name = "openai"
    est_cost_per_1k = 0.3
    est_latency_ms = 900
    model_name = settings.openai_model

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    async def complete(self, prompt: str) -> str:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API key not configured")
        payload = {
            "model": settings.openai_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(f"{settings.openai_base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    est_cost_per_1k = 0.4
    est_latency_ms = 1000
    model_name = settings.anthropic_model

    def is_configured(self) -> bool:
        return bool(settings.anthropic_api_key)

    async def complete(self, prompt: str) -> str:
        if not settings.anthropic_api_key:
            raise RuntimeError("Anthropic API key not configured")
        payload = {
            "model": settings.anthropic_model,
            "max_tokens": 800,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(f"{settings.anthropic_base_url}/messages", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            content = data.get("content", [])
            if content and isinstance(content, list):
                first = content[0]
                if isinstance(first, dict):
                    return str(first.get("text", ""))
            return json.dumps(data)


class OllamaProvider(LLMProvider):
    name = "ollama"
    est_cost_per_1k = 0.05
    est_latency_ms = 1800
    model_name = settings.ollama_model

    async def complete(self, prompt: str) -> str:
        payload = {"model": settings.ollama_model, "prompt": prompt, "stream": False}
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            return str(data.get("response", ""))
