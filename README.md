# AI QA Platform

Production-grade, web-based AI QA automation platform with engine-agnostic LLM routing, pluggable multi-agent orchestration, self-healing execution, memory learning, and rich reporting.

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:3000  
Backend docs: http://localhost:8000/docs

## Architecture

- FastAPI async backend with modular services
- Multi-agent pipeline using structured JSON contracts
- LLM router with provider fallback and cost/latency scoring
- Execution engine abstraction: Playwright (primary), Selenium/API stubs
- Self-healing with adaptive retries and alternative locator strategies
- Memory store for locator success/failure patterns
- Rich reports (JSON + human-readable summary + root cause analysis)
