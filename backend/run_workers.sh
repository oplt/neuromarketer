#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

worker_role="${CELERY_WORKER_ROLE:-default}"
inference_queue="${CELERY_INFERENCE_QUEUE:-analysis-inference}"
scoring_queue="${CELERY_SCORING_QUEUE:-analysis-scoring}"

queue_spec="${CELERY_WORKER_QUEUES:-}"
worker_name="${CELERY_WORKER_NAME:-}"
pool_type="${CELERY_WORKER_POOL:-threads}"  # Default to threads
concurrency="${CELERY_WORKER_CONCURRENCY:-4}"  # Default to 4 threads
prefetch_multiplier="${CELERY_WORKER_PREFETCH_MULTIPLIER:-1}"

case "${worker_role}" in
  inference|inference-cpu|analysis-inference)
    queue_spec="${queue_spec:-${inference_queue}}"
    worker_name="${worker_name:-inference@%h}"
    pool_type="${CELERY_WORKER_POOL:-prefork}"
    concurrency="${CELERY_WORKER_CONCURRENCY:-${CELERY_INFERENCE_WORKER_CONCURRENCY:-1}}"
    prefetch_multiplier="${CELERY_WORKER_PREFETCH_MULTIPLIER:-${CELERY_INFERENCE_WORKER_PREFETCH_MULTIPLIER:-1}}"
    ;;
  scoring|scoring-cpu|analysis-scoring)
    queue_spec="${queue_spec:-${scoring_queue}}"
    worker_name="${worker_name:-scoring@%h}"
    pool_type="${CELERY_WORKER_POOL:-prefork}"
    concurrency="${CELERY_WORKER_CONCURRENCY:-${CELERY_SCORING_WORKER_CONCURRENCY:-4}}"
    prefetch_multiplier="${CELERY_WORKER_PREFETCH_MULTIPLIER:-${CELERY_SCORING_WORKER_PREFETCH_MULTIPLIER:-4}}"
    ;;
  *)
    queue_spec="${queue_spec:-${inference_queue},${scoring_queue}}"
    worker_name="${worker_name:-worker@%h}"
    pool_type="${CELERY_WORKER_POOL:-prefork}"
    concurrency="${CELERY_WORKER_CONCURRENCY:-4}"
    prefetch_multiplier="${CELERY_WORKER_PREFETCH_MULTIPLIER:-1}"
    ;;
esac

celery_cmd=(
  worker
  --loglevel=INFO
  -Q "${queue_spec}"
  -n "${worker_name}"
  --pool="${pool_type}"
  --concurrency="${concurrency}"
  --prefetch-multiplier="${prefetch_multiplier}"
)

# Add inference worker safety optimizations
if [[ "${worker_role}" == "inference"* ]] || [[ "${worker_role}" == "analysis-inference" ]]; then
  celery_cmd+=(
    --without-gossip
    --without-mingle
    --without-heartbeat
  )
fi

echo "Starting Celery worker with:"
echo "  Role: ${worker_role}"
echo "  Queue: ${queue_spec}"
echo "  Pool: ${pool_type}"
echo "  Concurrency: ${concurrency}"
echo "  Prefetch multiplier: ${prefetch_multiplier}"

if [[ -x "${SCRIPT_DIR}/.venv/bin/celery" ]]; then
  exec "${SCRIPT_DIR}/.venv/bin/celery" -A backend.celery_app.celery_app "${celery_cmd[@]}"
fi

exec celery -A backend.celery_app.celery_app "${celery_cmd[@]}"