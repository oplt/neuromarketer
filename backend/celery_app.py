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

from backend.core.config import settings
from backend.core.log_context import bind_celery_task_context, build_celery_task_headers, clear_log_context
from backend.core.logging import configure_logging
from backend.services.tribe_runtime import get_shared_tribe_runtime

configure_logging()

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
    worker_hijack_root_logger=False,
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
    if not settings.tribe_preload_on_worker_startup:
        return

    runtime = get_shared_tribe_runtime()
    runtime.load()
