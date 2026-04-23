from __future__ import annotations

import asyncio
import atexit
import socket
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from urllib.parse import urlparse
from uuid import UUID

from celery.app.control import DuplicateNodenameWarning

from backend.application.services.analysis_evaluations import AnalysisEvaluationApplicationService
from backend.application.services.predictions import PredictionApplicationService
from backend.celery_app import celery_app
from backend.core.config import settings
from backend.core.exceptions import (
    ConfigurationAppError,
    DependencyAppError,
    NotFoundAppError,
    ValidationAppError,
)
from backend.core.log_context import bound_log_context
from backend.core.logging import duration_ms, get_logger, log_event, log_exception
from backend.core.metrics import metrics
from backend.db.repositories import CreativeRepository, InferenceRepository
from backend.db.session import AsyncSessionLocal
from backend.schemas.evaluators import EvaluationMode
from backend.services.analysis_goal_taxonomy import (
    normalize_analysis_channel,
    normalize_goal_template,
)
from backend.services.analysis_job_events import publish_analysis_job_event
from backend.services.analysis_postprocessor import AnalysisPostprocessor
from backend.services.tribe_inference_service import TribeInferenceService

logger = get_logger(__name__)
_in_process_tasks: set[asyncio.Task[None]] = set()
_in_process_llm_tasks: set[asyncio.Task[None]] = set()
_in_process_prediction_scoring_tasks: set[asyncio.Task[None]] = set()

# ThreadPoolExecutor for in-process fallback jobs.
# Using a bounded pool (max_workers=4) with wait=True on shutdown so
# SIGTERM does not kill running analysis jobs mid-flight.
_fallback_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="prediction-job")
atexit.register(lambda: _fallback_executor.shutdown(wait=True, cancel_futures=False))


async def _run_prediction_job(job_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        try:
            await PredictionApplicationService(db).process_prediction_job(job_id)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            await PredictionApplicationService(db).mark_job_failed(job_id, str(exc))
            await db.commit()
            await publish_analysis_job_event(
                job_id=job_id,
                event_type="job_failed",
                payload={"status": "failed", "error_message": str(exc)},
            )
            raise


async def _run_prediction_scoring_job(job_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        try:
            await PredictionApplicationService(db).process_prediction_scoring_job(job_id)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            partial_result_available = await _preserve_failed_scoring_result(
                db, job_id=job_id, error_message=str(exc)
            )
            await db.commit()
            repo = InferenceRepository(db)
            job = await repo.get_job(job_id)
            if job is not None:
                await repo.mark_job_failed(
                    job, str(exc), partial_result_available=partial_result_available
                )
                await db.commit()
            await publish_analysis_job_event(
                job_id=job_id,
                event_type="job_failed",
                payload={"status": "failed", "error_message": str(exc)},
            )
            raise


async def _preserve_failed_scoring_result(db, *, job_id: UUID, error_message: str) -> bool:
    repo = InferenceRepository(db)
    creatives = CreativeRepository(db)
    tribe_inference = TribeInferenceService()
    postprocessor = AnalysisPostprocessor()

    job = await repo.get_job_with_prediction(job_id)
    if job is None or job.prediction is None:
        return False

    creative_version = await creatives.get_creative_version(job.creative_version_id)
    if creative_version is None:
        return False

    runtime_output = tribe_inference.runtime_output_from_prediction(job.prediction)
    modality = tribe_inference.resolve_modality(creative_version)
    campaign_context = (job.request_payload or {}).get("campaign_context") or {}
    fallback_payload = postprocessor.build_scene_extraction_payload(
        runtime_output=runtime_output,
        modality=modality,
        objective=str(campaign_context.get("objective") or "").strip() or None,
        goal_template=normalize_goal_template(campaign_context.get("goal_template")),
        channel=normalize_analysis_channel(campaign_context.get("channel")),
        audience_segment=str(campaign_context.get("audience_segment") or "").strip() or None,
        source_label=tribe_inference.resolve_source_label(creative_version=creative_version),
    )
    fallback_payload.summary_json["notes"] = [
        "TRIBE scene extraction completed successfully.",
        "LLM scoring failed, so this saved result includes TRIBE-derived scene extraction only.",
    ]
    metadata = dict(fallback_payload.summary_json.get("metadata") or {})
    metadata["scoring_status"] = "failed"
    metadata["scoring_error_message"] = error_message
    fallback_payload.summary_json["metadata"] = metadata

    await repo.replace_analysis_result(
        job=job,
        summary_json=fallback_payload.summary_json,
        metrics_json=fallback_payload.metrics_json,
        timeline_json=fallback_payload.timeline_json,
        segments_json=fallback_payload.segments_json,
        visualizations_json=fallback_payload.visualizations_json,
        recommendations_json=fallback_payload.recommendations_json,
    )
    log_event(
        logger,
        "prediction_scoring_partial_result_preserved",
        job_id=str(job_id),
        modality=modality,
        status="preserved",
    )
    return True


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
                failure_metadata = getattr(exc, "telemetry", None)
                await service.evaluations.mark_failed(
                    record=record,
                    error_message=str(exc),
                    metadata_json=failure_metadata
                    if isinstance(failure_metadata, dict)
                    else record.metadata_json,
                )
                await db.commit()
            raise


async def _run_prediction_job_in_process(job_id: UUID) -> None:
    start = time.perf_counter()
    try:
        await _run_prediction_job(job_id)
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "succeeded"},
        )
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
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed"},
        )


def _run_prediction_job_in_process_entrypoint(job_id: UUID) -> None:
    asyncio.run(_run_prediction_job_in_process(job_id))


async def _run_prediction_scoring_job_in_process(job_id: UUID) -> None:
    start = time.perf_counter()
    try:
        await _run_prediction_scoring_job(job_id)
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "succeeded", "phase": "scoring"},
        )
    except Exception as exc:
        log_exception(
            logger,
            "prediction_scoring_job_failed",
            exc,
            job_id=str(job_id),
            status="failed",
            execution_mode="in_process",
            duration_ms=duration_ms(start, time.perf_counter()),
        )
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed", "phase": "scoring"},
        )


def _run_prediction_scoring_job_in_process_entrypoint(job_id: UUID) -> None:
    asyncio.run(_run_prediction_scoring_job_in_process(job_id))


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
        # No running event loop — submit to the bounded executor so the thread
        # is tracked and waited for on shutdown (not a fire-and-forget daemon).
        context = copy_context()
        _fallback_executor.submit(context.run, _run_prediction_job_in_process_entrypoint, job_id)
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
        _fallback_executor.submit(
            context.run, _run_llm_evaluation_job_in_process_entrypoint, job_id, mode
        )
        return

    task = loop.create_task(
        _run_llm_evaluation_job_in_process(job_id, mode),
        name=f"llm-evaluation-{job_id}-{mode.value}",
    )
    _in_process_llm_tasks.add(task)
    task.add_done_callback(_in_process_llm_tasks.discard)


def _schedule_prediction_scoring_job_in_process(job_id: UUID) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        context = copy_context()
        _fallback_executor.submit(
            context.run, _run_prediction_scoring_job_in_process_entrypoint, job_id
        )
        return

    task = loop.create_task(
        _run_prediction_scoring_job_in_process(job_id),
        name=f"prediction-scoring-{job_id}",
    )
    _in_process_prediction_scoring_tasks.add(task)
    task.add_done_callback(_in_process_prediction_scoring_tasks.discard)


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


def _has_active_workers(queue_name: str | None = None, timeout_seconds: float = 0.4) -> bool:
    if not _is_broker_reachable():
        return False

    try:
        with warnings.catch_warnings(record=True) as probe_warnings:
            warnings.simplefilter("always", DuplicateNodenameWarning)
            inspector = celery_app.control.inspect(timeout=timeout_seconds)
            responses = inspector.ping() or {}
            active_queues = (inspector.active_queues() or {}) if responses and queue_name else {}
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

    duplicate_node_warning = next(
        (
            str(warning.message)
            for warning in probe_warnings
            if issubclass(warning.category, DuplicateNodenameWarning)
        ),
        None,
    )
    if duplicate_node_warning:
        log_event(
            logger,
            "prediction_job_duplicate_worker_names",
            level="warning",
            broker_url=celery_app.conf.broker_url,
            queue_name=queue_name,
            warning_message=duplicate_node_warning,
            status="degraded",
        )

    if responses:
        if not queue_name:
            return True

        for worker_queues in active_queues.values():
            for queue in worker_queues or []:
                if queue.get("name") == queue_name:
                    return True
        log_event(
            logger,
            "prediction_job_queue_unserved",
            level="warning",
            broker_url=celery_app.conf.broker_url,
            queue_name=queue_name,
            status="fallback",
            dispatch_mode="in_process",
        )
        return False

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
        if not _has_active_workers(settings.celery_inference_queue):
            _schedule_prediction_job_in_process(job_id)
            log_event(
                logger,
                "prediction_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="in_process",
                queue_name=settings.celery_inference_queue,
            )
            return "in_process"

        try:
            process_prediction_job_task.apply_async(
                args=[str(job_id)],
                queue=settings.celery_inference_queue,
            )
            log_event(
                logger,
                "prediction_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="celery",
                queue_name=settings.celery_inference_queue,
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
                queue_name=settings.celery_inference_queue,
            )
            return "in_process"


async def dispatch_llm_evaluation_job(job_id: UUID, mode: EvaluationMode) -> str:
    with bound_log_context(job_id=str(job_id), mode=mode.value):
        if not _has_active_workers(settings.celery_scoring_queue):
            _schedule_llm_evaluation_job_in_process(job_id, mode)
            log_event(
                logger,
                "llm_evaluation_enqueued",
                job_id=str(job_id),
                mode=mode.value,
                status="queued",
                dispatch_mode="in_process",
                queue_name=settings.celery_scoring_queue,
            )
            return "in_process"

        try:
            process_llm_evaluation_task.apply_async(
                args=[str(job_id), mode.value],
                queue=settings.celery_scoring_queue,
            )
            log_event(
                logger,
                "llm_evaluation_enqueued",
                job_id=str(job_id),
                mode=mode.value,
                status="queued",
                dispatch_mode="celery",
                queue_name=settings.celery_scoring_queue,
            )
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
            log_event(
                logger,
                "llm_evaluation_enqueued",
                job_id=str(job_id),
                mode=mode.value,
                status="queued",
                dispatch_mode="in_process",
                queue_name=settings.celery_scoring_queue,
            )
            return "in_process"


async def dispatch_prediction_scoring_job(job_id: UUID) -> str:
    with bound_log_context(job_id=str(job_id)):
        if not _has_active_workers(settings.celery_scoring_queue):
            _schedule_prediction_scoring_job_in_process(job_id)
            log_event(
                logger,
                "prediction_scoring_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="in_process",
                queue_name=settings.celery_scoring_queue,
            )
            return "in_process"

        try:
            process_prediction_scoring_task.apply_async(
                args=[str(job_id)],
                queue=settings.celery_scoring_queue,
            )
            log_event(
                logger,
                "prediction_scoring_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="celery",
                queue_name=settings.celery_scoring_queue,
            )
            return "celery"
        except Exception as exc:
            log_exception(
                logger,
                "prediction_scoring_job_enqueue_failed",
                exc,
                job_id=str(job_id),
                status="failed",
            )
            _schedule_prediction_scoring_job_in_process(job_id)
            log_event(
                logger,
                "prediction_scoring_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="in_process",
                queue_name=settings.celery_scoring_queue,
            )
            return "in_process"


@celery_app.task(
    name="tasks.process_prediction_job",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_jitter=True,
    queue=settings.celery_inference_queue,
)
def process_prediction_job_task(self, job_id: str) -> None:
    start = time.perf_counter()
    try:
        asyncio.run(_run_prediction_job(UUID(job_id)))
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "succeeded"},
        )
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
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed"},
        )
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
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "retry"},
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="tasks.process_llm_evaluation",
    bind=True,
    max_retries=0,
    queue=settings.celery_scoring_queue,
)
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


@celery_app.task(
    name="tasks.process_prediction_scoring",
    bind=True,
    max_retries=0,
    queue=settings.celery_scoring_queue,
)
def process_prediction_scoring_task(self, job_id: str) -> None:
    start = time.perf_counter()
    try:
        asyncio.run(_run_prediction_scoring_job(UUID(job_id)))
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "succeeded", "phase": "scoring"},
        )
    except (ConfigurationAppError, DependencyAppError, NotFoundAppError, ValidationAppError) as exc:
        log_exception(
            logger,
            "prediction_scoring_job_failed",
            exc,
            level="warning",
            job_id=job_id,
            task_id=self.request.id,
            status="failed",
            retryable=False,
            duration_ms=duration_ms(start, time.perf_counter()),
        )
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed", "phase": "scoring"},
        )
        raise
    except Exception as exc:
        log_exception(
            logger,
            "prediction_scoring_job_unhandled_error",
            exc,
            job_id=job_id,
            task_id=self.request.id,
            status="failed",
            duration_ms=duration_ms(start, time.perf_counter()),
        )
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed", "phase": "scoring"},
        )
        raise
