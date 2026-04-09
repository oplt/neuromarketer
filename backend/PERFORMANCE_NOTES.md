# Backend Performance Notes

Focus areas validated in this pass:

- Authenticated request setup:
  - `backend/api/dependencies.py`
  - `backend/db/repositories/crud.py`
  - Goal: reduce per-request database round trips in the auth context path.

- Analysis history retrieval:
  - `backend/db/repositories/inference.py`
  - `backend/application/services/analysis.py`
  - `backend/db/repositories/uploads.py`
  - Goal: keep filtering in SQL and avoid N+1 artifact lookups when rendering recent analysis history.

- Admin invite reads:
  - `backend/application/services/auth_service.py`
  - Goal: batch related user lookups instead of resolving invite actors one row at a time.

- Analysis execution flow:
  - `backend/application/services/analysis_job_processor.py`
  - `backend/tasks.py`
  - `backend/celery_app.py`
  - `backend/api/router/analysis.py`
  - `backend/services/tribe_inference_service.py`
  - `backend/services/tribe_runtime.py`
  - Goal: split inference/scoring queues, reduce progress-write churn, cache deterministic TRIBE runtime output, and emit timing data that makes the hot stage obvious.

Recommended profiling checkpoints:

- Measure `GET /api/v1/analysis/jobs` with 12, 24, and 50 rows.
- Measure authenticated `GET /api/v1/analysis/config` or `GET /api/v1/analysis/assets` to confirm auth-context query count.
- Measure account overview pages with multiple invites to confirm batched invite-user hydration.
- Compare end-to-end analysis runs with and without `TRIBE_RUNTIME_OUTPUT_CACHE_ENABLED` for reruns of the same creative version.
- Compare worker logs for `prediction_job_stage_seconds{stage="tribe_inference"}` vs `prediction_job_stage_seconds{stage="llm_scoring"}` to identify whether GPU or LLM is dominant.
- Verify SSE event streams no longer force a full job snapshot load on every non-terminal progress event.

Expected query-shape improvements from this pass:

- Auth context: fewer read queries before handler execution.
- Analysis history: SQL-side JSON filtering plus batched artifact hydration.
- Invite listing: one user batch lookup instead of one lookup per invite actor.
- Analysis progress: only milestone stages persist to the database; transient stages still flow through Redis/SSE.
- Analysis streaming: progress events reuse the last known snapshot and only refresh from the database periodically or on terminal transitions.

Recommended worker layout:

- Single GPU:
  - Inference worker: `celery -A backend.celery_app worker -Q analysis-inference --concurrency=1`
  - Scoring worker: `celery -A backend.celery_app worker -Q analysis-scoring --concurrency=1`
- Multi-GPU:
  - Run one inference worker process per GPU with `CUDA_VISIBLE_DEVICES` pinned per worker.
  - Keep scoring workers separate so a slow local LLM does not starve inference slots.
