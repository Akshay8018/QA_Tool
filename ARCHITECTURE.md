# Production Architecture

## Core Flow
1. User submits natural-language instruction and optional test data.
2. LLM Router selects provider by speed/cost/balanced policy and falls back on failure.
3. Planner -> Decomposer -> Step Generator produce executable JSON scenarios.
4. Pluggable execution engine runs steps (Playwright primary, Selenium/API fallbacks).
5. Observer captures detailed telemetry per step.
6. Reflection agent triggers self-healing retries and alternate locator strategy.
7. Memory store persists stable locators, failure signatures, and fix heuristics.
8. Report generator emits machine JSON plus human RCA report.

## Resilience
- Provider fallback across OpenAI/Anthropic/Ollama implementations.
- Self-healing locator chain: CSS -> Text -> XPath -> AI-generated alternatives.
- Non-blocking failure handling keeps run progressing for complete RCA.
- Queue-ready async processing via Celery+Redis.

## Extensibility
- Add new LLM provider by implementing `LLMProvider` interface.
- Add engine by implementing `BaseExecutionEngine`.
- Add new agent by introducing JSON contract stage in `TestOrchestrator`.
