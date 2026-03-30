from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.services.tribe_runtime import get_shared_tribe_runtime

celery_app = Celery(
    "neuromarketing",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=settings.celery_soft_time_limit_seconds,
    task_time_limit=settings.celery_time_limit_seconds,
)

logger = get_logger(__name__)


@worker_process_init.connect
def preload_tribe_runtime(**_: object) -> None:
    if not settings.tribe_preload_on_worker_startup:
        return

    runtime = get_shared_tribe_runtime()
    runtime.load()
    logger.info(
        "TRIBE runtime preloaded for worker process.",
        extra={
            "event": "tribe_runtime_preloaded",
            "extra_fields": {"model_repo_id": runtime.model_repo_id, "device": runtime._get_resolved_device()},
        },
    )
