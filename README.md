# NeuroMarketer

NeuroMarketer is a multimodal creative analysis workspace for teams that want faster pre-launch feedback on campaign assets. The project combines direct uploads, asynchronous model inference, structured dashboards, version comparison, and optimization suggestions so creative review can happen in one system instead of across disconnected tools.

## What The Project Does

- Upload video, audio, and text assets into object storage from the app.
- Run asynchronous TRIBE v2-backed analysis jobs through FastAPI and Celery workers.
- Surface attention, emotion, memory, cognitive-load, and conversion-proxy signals in a dashboard-oriented format.
- Show timelines, segment summaries, high/low attention intervals, heatmap-style visualizations, and ranked recommendations.
- Promote stored artifacts into creative versions, compare variants, and generate optimization suggestions.
- Optionally request structured LLM evaluations using domain-specific review modes such as marketing, social media, educational, and defence.

## Stack

- Frontend: React 19, TypeScript, Vite, Material UI
- Backend: FastAPI, SQLAlchemy, Alembic, Celery
- Infra: PostgreSQL, Redis, MinIO locally; S3/R2-compatible storage in deployment
- Model layer: `facebookresearch/tribev2` plus optional Ollama or OpenAI-compatible LLM providers for qualitative evaluations

## Repository Layout

- `frontend/` contains the React dashboard and analysis workflow UI.
- `backend/` contains the API, workers, database models, application services, TRIBE runtime integration, and LLM evaluation pipeline.
- `docker-compose.yml` starts the local infrastructure, API, and worker services.
- `cache/` stores model/runtime artifacts used by TRIBE during local development.

## Typical Workflow

1. Sign up or sign in to create a workspace and default project.
2. Upload a video, audio, or text asset.
3. Queue an analysis job and inspect the returned dashboard payload.
4. Compare promoted creative versions and review optimization suggestions.
5. Trigger optional LLM evaluations when you want qualitative review on top of the model outputs.

## Local Development

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ and npm
- Enough disk space and startup time for model dependencies and caches
- Optional: an Ollama or OpenAI-compatible endpoint if you want to use the LLM evaluation features

### Start The Backend Stack

```bash
docker compose up --build
```

This starts:

- API on `http://localhost:8000`
- API docs on `http://localhost:8000/docs`
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`
- MinIO API on `http://localhost:9000`
- MinIO console on `http://localhost:9001`

Notes:

- The first worker startup can take longer because TRIBE dependencies and model assets may need to initialize.
- The checked-in Compose file currently reads `backend/.env.example`. For real credentials or private settings, point `docker-compose.yml` at a private env file before committing changes.

### Start The Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

During local development, Vite proxies `/api/*` requests to `http://127.0.0.1:8000`. If you deploy the frontend separately, you can also set `VITE_API_BASE_URL`.

## Configuration Notes

- Core backend settings live in `backend/.env.example`.
- Local object storage is configured through MinIO, but the storage layer also supports S3/R2-style endpoints.
- LLM evaluation is optional. Core upload, analysis, comparison, and optimization flows do not require it.

## Running Tests

Backend:

```bash
docker compose exec api python -m unittest discover backend/tests
```

Frontend:

```bash
cd frontend
npm test
```

## Why This Repo Exists

NeuroMarketer is built around a practical product question: how do you review creative quality before launch without forcing teams to stitch together storage, model inference, qualitative critique, and optimization by hand? This repository is the working answer: a single codebase for uploading assets, scoring them, reviewing the evidence, and turning the output into the next version.
