#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

if [[ -x "${SCRIPT_DIR}/.venv/bin/celery" ]]; then
  exec "${SCRIPT_DIR}/.venv/bin/celery" -A backend.celery_app.celery_app worker --loglevel=INFO
fi

exec celery -A backend.celery_app.celery_app worker --loglevel=INFO
