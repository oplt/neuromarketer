# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (Docker-based)

```bash
# Start full backend stack (API on :8000, Postgres :5432, Redis :6379, MinIO :9000/:9001)
docker compose up --build

# Run API locally without Docker (requires Postgres/Redis/MinIO running)
uvicorn backend.api.main:app --reload --port 8000

# Run Celery worker locally
celery -A backend.celery_app.celery_app worker --loglevel=INFO

# Database migrations
alembic -c backend/alembic.ini revision --autogenerate -m "description"
alembic -c backend/alembic.ini upgrade head
alembic -c backend/alembic.ini downgrade base

# Lint and format
ruff check --fix . && ruff format .

# Run backend tests
docker compose exec api python -m unittest discover backend/tests
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # dev server on :5173
npm test         # run tests
```

## Architecture

### Request → Job → Result Flow

1. **API layer** (`backend/api/router/`) receives HTTP requests. Auth uses JWT via `backend/api/dependencies.py`. Routers: `auth`, `account`, `uploads`, `analysis`, `predict`, `creative_versions`, `settings`.
2. **Application services** (`backend/application/services/`) contain business logic — thin orchestration between DB repositories and domain services. Each service corresponds roughly to a router.
3. **Tasks** (`backend/tasks.py`) dispatches async work. `dispatch_prediction_job` and `dispatch_llm_evaluation_job` will use Celery if a broker/worker is reachable, otherwise fall back to in-process threading automatically.
4. **Celery workers** (`backend/workers/`) and **services** (`backend/services/`) handle the actual model inference pipeline:
   - `tribe_inference_service.py` / `tribe_runtime.py` — wraps TRIBE v2 model execution
   - `analysis_job_events.py` — publishes SSE/Redis events during job lifecycle
   - `scoring.py`, `preprocess.py`, `video_preprocess.py`, `text_preprocess.py` — asset preparation and scoring

### LLM Evaluation Pipeline

`backend/llm/` is an independent sub-system:
- `llm_evaluators/` — domain-specific evaluators (`marketing`, `socialmedia`, `educational`, `defence`), each extending `base.py` and registered in `registry.py`
- `llm_client.py` — HTTP client for Ollama / OpenAI-compatible endpoints
- `router.py` — routes evaluation requests to configured LLM providers with fallback
- `evaluation_service.py` — orchestrates evaluator → router → schema validation → `EvaluationResponse`

LLM evaluation is optional. Core analysis flows do not depend on it.

### Database

SQLAlchemy async with PostgreSQL. Models in `backend/db/models.py`. Migrations in `backend/alembic/versions/`. Repositories live in `backend/db/repositories/`.

Key entities: `User`, `Organisation`, `Project`, `Upload`, `PredictionJob`, `AnalysisResult`, `CreativeVersion`, `LLMEvaluation`.

### Frontend

React 19 + TypeScript + Vite + Material UI. Pages in `frontend/src/pages/`. Shared components in `frontend/src/components/`. Vite proxies `/api/*` to `http://127.0.0.1:8000` during dev.

### Configuration

Backend settings come from `backend/.env.example` (used by Docker Compose). `backend/core/config.py` exposes a `settings` singleton. LLM provider settings are managed via the `workspace_settings` application service and stored in DB, not just env vars.

### Task Dispatch Strategy

`dispatch_prediction_job` in `backend/tasks.py` probes the broker socket and pings Celery workers before deciding whether to use Celery or fall back to in-process async threads. This means the API works without a running worker, which is useful in development.
