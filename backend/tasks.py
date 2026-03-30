from __future__ import annotations

import asyncio
import time
from uuid import UUID

from backend.application.services.predictions import PredictionApplicationService
from backend.celery_app import celery_app
from backend.core.exceptions import (
    ConfigurationAppError,
    DependencyAppError,
    NotFoundAppError,
    ValidationAppError,
)
from backend.core.logging import get_logger
from backend.core.metrics import metrics
from backend.db.session import AsyncSessionLocal

logger = get_logger(__name__)


async def _run_prediction_job(job_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        try:
            await PredictionApplicationService(db).process_prediction_job(job_id)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            await PredictionApplicationService(db).mark_job_failed(job_id, str(exc))
            await db.commit()
            raise


@celery_app.task(name="tasks.process_prediction_job", bind=True, max_retries=3, retry_backoff=True, retry_jitter=True)
def process_prediction_job_task(self, job_id: str) -> None:
    start = time.perf_counter()
    try:
        asyncio.run(_run_prediction_job(UUID(job_id)))
        metrics.observe("prediction_job_duration_seconds", time.perf_counter() - start, labels={"status": "succeeded"})
    except (ConfigurationAppError, DependencyAppError, NotFoundAppError, ValidationAppError) as exc:
        logger.warning(
            "Prediction job failed permanently.",
            extra={"event": "prediction_job_failed", "extra_fields": {"job_id": job_id, "error": str(exc)}},
        )
        metrics.observe("prediction_job_duration_seconds", time.perf_counter() - start, labels={"status": "failed"})
        raise
    except Exception as exc:
        logger.exception(
            "Prediction job failed with retryable error.",
            extra={"event": "prediction_job_retry", "extra_fields": {"job_id": job_id, "error": str(exc)}},
        )
        metrics.observe("prediction_job_duration_seconds", time.perf_counter() - start, labels={"status": "retry"})
        raise self.retry(exc=exc)
