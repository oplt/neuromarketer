from __future__ import annotations

import asyncio
import socket
import threading
import time
from contextvars import copy_context
from urllib.parse import urlparse
from uuid import UUID

from backend.application.services.analysis_evaluations import AnalysisEvaluationApplicationService
from backend.application.services.predictions import PredictionApplicationService
from backend.celery_app import celery_app
from backend.core.exceptions import (
    ConfigurationAppError,
    DependencyAppError,
    NotFoundAppError,
    ValidationAppError,
)
from backend.core.log_context import bound_log_context
from backend.core.logging import duration_ms, get_logger, log_event, log_exception
from backend.core.metrics import metrics
from backend.db.session import AsyncSessionLocal
from backend.schemas.evaluators import EvaluationMode

logger = get_logger(__name__)
_in_process_tasks: set[asyncio.Task[None]] = set()
_in_process_llm_tasks: set[asyncio.Task[None]] = set()


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


async def _run_llm_evaluation_job(job_id: UUID, mode: EvaluationMode) -> None:
    async with AsyncSessionLocal() as db:
        service = AnalysisEvaluationApplicationService(db)
        try:
            await service.process_evaluation(job_id=job_id, mode=mode)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            record = await service.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
            if record is not None:
                await service.evaluations.mark_failed(record=record, error_message=str(exc))
                await db.commit()
            raise


async def _run_prediction_job_in_process(job_id: UUID) -> None:
    start = time.perf_counter()
    try:
        await _run_prediction_job(job_id)
        metrics.observe("prediction_job_duration_seconds", time.perf_counter() - start, labels={"status": "succeeded"})
    except Exception as exc:
        log_exception(
            logger,
            "prediction_job_failed",
            exc,
            job_id=str(job_id),
            status="failed",
            execution_mode="in_process",
            duration_ms=duration_ms(start, time.perf_counter()),
        )
        metrics.observe("prediction_job_duration_seconds", time.perf_counter() - start, labels={"status": "failed"})


def _run_prediction_job_in_process_entrypoint(job_id: UUID) -> None:
    asyncio.run(_run_prediction_job_in_process(job_id))


async def _run_llm_evaluation_job_in_process(job_id: UUID, mode: EvaluationMode) -> None:
    start = time.perf_counter()
    try:
        await _run_llm_evaluation_job(job_id, mode)
        metrics.observe(
            "llm_evaluation_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "succeeded", "mode": mode.value},
        )
    except Exception as exc:
        log_exception(
            logger,
            "llm_evaluation_in_process_failed",
            exc,
            job_id=str(job_id),
            mode=mode.value,
            status="failed",
            execution_mode="in_process",
            duration_ms=duration_ms(start, time.perf_counter()),
        )
        metrics.observe(
            "llm_evaluation_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed", "mode": mode.value},
        )


def _run_llm_evaluation_job_in_process_entrypoint(job_id: UUID, mode: EvaluationMode) -> None:
    asyncio.run(_run_llm_evaluation_job_in_process(job_id, mode))


def _schedule_prediction_job_in_process(job_id: UUID) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        context = copy_context()
        worker = threading.Thread(
            target=context.run,
            args=(_run_prediction_job_in_process_entrypoint, job_id),
            daemon=True,
            name=f"prediction-job-{job_id}",
        )
        worker.start()
        return

    task = loop.create_task(
        _run_prediction_job_in_process(job_id),
        name=f"prediction-job-{job_id}",
    )
    _in_process_tasks.add(task)
    task.add_done_callback(_in_process_tasks.discard)


def _schedule_llm_evaluation_job_in_process(job_id: UUID, mode: EvaluationMode) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        context = copy_context()
        worker = threading.Thread(
            target=context.run,
            args=(_run_llm_evaluation_job_in_process_entrypoint, job_id, mode),
            daemon=True,
            name=f"llm-evaluation-{job_id}-{mode.value}",
        )
        worker.start()
        return

    task = loop.create_task(
        _run_llm_evaluation_job_in_process(job_id, mode),
        name=f"llm-evaluation-{job_id}-{mode.value}",
    )
    _in_process_llm_tasks.add(task)
    task.add_done_callback(_in_process_llm_tasks.discard)


def _get_broker_socket_address(broker_url: str) -> tuple[str, int] | None:
    parsed = urlparse(broker_url)
    if not parsed.hostname:
        return None
    if parsed.port is not None:
        return parsed.hostname, parsed.port

    scheme = parsed.scheme.lower()
    if scheme in {"redis", "rediss"}:
        return parsed.hostname, 6379
    if scheme in {"amqp", "amqps", "pyamqp"}:
        return parsed.hostname, 5672
    return None


def _is_broker_reachable(timeout_seconds: float = 0.25) -> bool:
    address = _get_broker_socket_address(celery_app.conf.broker_url)
    if address is None:
        return False

    try:
        with socket.create_connection(address, timeout=timeout_seconds):
            return True
    except OSError as exc:
        log_exception(
            logger,
            "prediction_job_broker_unreachable",
            exc,
            level="warning",
            broker_url=celery_app.conf.broker_url,
            host=address[0],
            port=address[1],
            status="fallback",
            dispatch_mode="in_process",
        )
        return False


def _has_active_workers(timeout_seconds: float = 0.4) -> bool:
    if not _is_broker_reachable():
        return False

    try:
        responses = celery_app.control.inspect(timeout=timeout_seconds).ping() or {}
    except Exception as exc:
        log_exception(
            logger,
            "prediction_job_worker_probe_failed",
            exc,
            level="warning",
            broker_url=celery_app.conf.broker_url,
            status="fallback",
            dispatch_mode="in_process",
        )
        return False

    if responses:
        return True

    log_event(
        logger,
        "prediction_job_no_workers",
        level="warning",
        broker_url=celery_app.conf.broker_url,
        status="fallback",
        dispatch_mode="in_process",
    )
    return False


async def dispatch_prediction_job(job_id: UUID) -> str:
    with bound_log_context(job_id=str(job_id)):
        if not _has_active_workers():
            _schedule_prediction_job_in_process(job_id)
            log_event(
                logger,
                "prediction_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="in_process",
            )
            return "in_process"

        try:
            process_prediction_job_task.delay(str(job_id))
            log_event(
                logger,
                "prediction_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="celery",
            )
            return "celery"
        except Exception as exc:
            log_exception(
                logger,
                "prediction_job_enqueue_failed",
                exc,
                job_id=str(job_id),
                status="failed",
            )
            _schedule_prediction_job_in_process(job_id)
            log_event(
                logger,
                "prediction_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="in_process",
            )
            return "in_process"


async def dispatch_llm_evaluation_job(job_id: UUID, mode: EvaluationMode) -> str:
    with bound_log_context(job_id=str(job_id), mode=mode.value):
        if not _has_active_workers():
            _schedule_llm_evaluation_job_in_process(job_id, mode)
            return "in_process"

        try:
            process_llm_evaluation_task.delay(str(job_id), mode.value)
            return "celery"
        except Exception as exc:
            log_exception(
                logger,
                "llm_evaluation_fallback_dispatch",
                exc,
                level="warning",
                job_id=str(job_id),
                mode=mode.value,
                status="fallback",
                dispatch_mode="in_process",
            )
            _schedule_llm_evaluation_job_in_process(job_id, mode)
            return "in_process"


@celery_app.task(name="tasks.process_prediction_job", bind=True, max_retries=3, retry_backoff=True, retry_jitter=True)
def process_prediction_job_task(self, job_id: str) -> None:
    start = time.perf_counter()
    try:
        asyncio.run(_run_prediction_job(UUID(job_id)))
        metrics.observe("prediction_job_duration_seconds", time.perf_counter() - start, labels={"status": "succeeded"})
    except (ConfigurationAppError, DependencyAppError, NotFoundAppError, ValidationAppError) as exc:
        log_exception(
            logger,
            "prediction_job_failed",
            exc,
            level="warning",
            job_id=job_id,
            task_id=self.request.id,
            status="failed",
            retryable=False,
            duration_ms=duration_ms(start, time.perf_counter()),
        )
        metrics.observe("prediction_job_duration_seconds", time.perf_counter() - start, labels={"status": "failed"})
        raise
    except Exception as exc:
        log_exception(
            logger,
            "prediction_job_failed",
            exc,
            job_id=job_id,
            task_id=self.request.id,
            status="retrying",
            retryable=True,
            retry_count=self.request.retries + 1,
            duration_ms=duration_ms(start, time.perf_counter()),
        )
        metrics.observe("prediction_job_duration_seconds", time.perf_counter() - start, labels={"status": "retry"})
        raise self.retry(exc=exc)


@celery_app.task(name="tasks.process_llm_evaluation", bind=True, max_retries=0)
def process_llm_evaluation_task(self, job_id: str, mode: str) -> None:
    evaluation_mode = EvaluationMode(mode)
    start = time.perf_counter()
    try:
        asyncio.run(_run_llm_evaluation_job(UUID(job_id), evaluation_mode))
        metrics.observe(
            "llm_evaluation_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "succeeded", "mode": evaluation_mode.value},
        )
    except (ConfigurationAppError, DependencyAppError, NotFoundAppError, ValidationAppError) as exc:
        log_exception(
            logger,
            "llm_evaluation_failed",
            exc,
            level="warning",
            job_id=job_id,
            mode=evaluation_mode.value,
            task_id=self.request.id,
            status="failed",
        )
        metrics.observe(
            "llm_evaluation_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed", "mode": evaluation_mode.value},
        )
        raise
    except Exception as exc:
        log_exception(
            logger,
            "llm_evaluation_unhandled_error",
            exc,
            job_id=job_id,
            mode=evaluation_mode.value,
            task_id=self.request.id,
            status="failed",
            duration_ms=duration_ms(start, time.perf_counter()),
        )
        metrics.observe(
            "llm_evaluation_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed", "mode": evaluation_mode.value},
        )
        raise
