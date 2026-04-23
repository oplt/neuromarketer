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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **NeuroMarketer** (3919 symbols, 14739 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/NeuroMarketer/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/NeuroMarketer/context` | Codebase overview, check index freshness |
| `gitnexus://repo/NeuroMarketer/clusters` | All functional areas |
| `gitnexus://repo/NeuroMarketer/processes` | All execution flows |
| `gitnexus://repo/NeuroMarketer/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
