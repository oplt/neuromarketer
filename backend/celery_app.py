from __future__ import annotations

import logging

from celery import Celery
from celery.signals import (
    after_setup_logger,
    after_setup_task_logger,
    before_task_publish,
    setup_logging,
    task_postrun,
    task_prerun,
    worker_process_init,
)
from kombu import Exchange, Queue

from backend.core.config import settings
from backend.core.log_context import (
    bind_celery_task_context,
    build_celery_task_headers,
    clear_log_context,
)
from backend.core.logging import configure_logging, get_logger, log_event
from backend.services.tribe_runtime import get_shared_tribe_runtime

configure_logging()
logger = get_logger(__name__)


def _worker_role() -> str:
    return (settings.celery_worker_role or "default").strip().lower()


def _is_inference_worker_role() -> bool:
    return _worker_role() in {"inference", "inference-cpu", "analysis-inference"}


def _worker_prefetch_multiplier() -> int:
    if _is_inference_worker_role():
        return max(1, settings.celery_inference_worker_prefetch_multiplier)
    return max(1, settings.celery_scoring_worker_prefetch_multiplier)


celery_app = Celery(
    "neuromarketing",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.tasks"],
)

# Default Celery `-A backend.celery_app` looks for `app` first.
app = celery_app

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
    worker_hijack_root_logger=False,
    task_default_queue=settings.celery_inference_queue,
    task_queues=(
        Queue(
            settings.celery_inference_queue,
            Exchange(settings.celery_inference_queue, type="direct"),
            routing_key=settings.celery_inference_queue,
        ),
        Queue(
            settings.celery_scoring_queue,
            Exchange(settings.celery_scoring_queue, type="direct"),
            routing_key=settings.celery_scoring_queue,
        ),
    ),
    task_routes={
        "tasks.process_prediction_job": {"queue": settings.celery_inference_queue},
        "tasks.process_prediction_scoring": {
            "queue": settings.celery_scoring_queue,
            "routing_key": settings.celery_scoring_queue,
        },
        "tasks.process_llm_evaluation": {
            "queue": settings.celery_scoring_queue,
            "routing_key": settings.celery_scoring_queue,
        },
    },
)


@setup_logging.connect
def configure_celery_logging(**_: object) -> None:
    configure_logging(force=True)


@after_setup_logger.connect
def propagate_celery_loggers(logger: logging.Logger, **_: object) -> None:
    logger.handlers.clear()
    logger.propagate = True


@after_setup_task_logger.connect
def propagate_celery_task_loggers(logger: logging.Logger, **_: object) -> None:
    logger.handlers.clear()
    logger.propagate = True


@before_task_publish.connect
def inject_publish_context(headers: dict | None = None, **_: object) -> None:
    if headers is None:
        return
    headers.update(build_celery_task_headers())


@task_prerun.connect
def bind_task_logging_context(
    task_id: str | None = None,
    task=None,
    args: tuple | None = None,
    kwargs: dict | None = None,
    **_: object,
) -> None:
    job_id = None
    if args:
        job_id = args[0]
    elif kwargs and "job_id" in kwargs:
        job_id = kwargs["job_id"]
    bind_celery_task_context(
        task.request if task is not None else None,
        task_id=task_id,
        task_name=task.name if task is not None else None,
        job_id=str(job_id) if job_id is not None else None,
    )


@task_postrun.connect
def clear_task_logging_context(**_: object) -> None:
    clear_log_context()


@worker_process_init.connect
def preload_tribe_runtime(**_: object) -> None:
    if not _is_inference_worker_role():
        log_event(
            logger,
            "celery_worker_initialized",
            worker_role=settings.celery_worker_role,
            inference_queue=settings.celery_inference_queue,
            scoring_queue=settings.celery_scoring_queue,
            tribe_preloaded=False,
            status="ready",
        )
        return

    runtime = get_shared_tribe_runtime()
    requested_device = runtime.get_requested_device()
    log_event(
        logger,
        "celery_worker_initialized",
        worker_role=settings.celery_worker_role,
        inference_queue=settings.celery_inference_queue,
        scoring_queue=settings.celery_scoring_queue,
        tribe_requested_device=requested_device,
        tribe_cache_folder=str(runtime.cache_folder),
        tribe_runtime_output_cache_enabled=settings.tribe_runtime_output_cache_enabled,
        tribe_runtime_output_cache_folder=settings.tribe_runtime_output_cache_folder,
        tribe_preload_on_worker_startup=settings.tribe_preload_on_worker_startup,
        status="ready",
    )
    if not settings.tribe_preload_on_worker_startup:
        return

    runtime.load()
    log_event(
        logger,
        "celery_worker_runtime_preloaded",
        worker_role=settings.celery_worker_role,
        tribe_requested_device=requested_device,
        tribe_resolved_device=runtime.get_resolved_device(),
        status="loaded",
    )


import backend.tasks  # noqa: E402, F401 — register Celery tasks when worker loads only this app
