from __future__ import annotations

import asyncio
import atexit
import time
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from uuid import UUID

from backend.application.services.analysis import AnalysisApplicationService
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


def _celery_workers_listen_to_queue(queue_name: str, *, timeout: float = 0.75) -> bool:
    """Return True if inspect reports at least one worker consuming ``queue_name``."""
    name = (queue_name or "").strip()
    if not name:
        return False
    try:
        inspector = celery_app.control.inspect(timeout=timeout)
        active = inspector.active_queues()
    except Exception as exc:
        log_event(
            logger,
            "celery_inspect_active_queues_failed",
            level="debug",
            queue=name,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        return False
    if not active or not isinstance(active, dict):
        return False
    for _worker, queues in active.items():
        if not isinstance(queues, list):
            continue
        for entry in queues:
            if isinstance(entry, dict) and entry.get("name") == name:
                return True
    return False


_in_process_tasks: set[asyncio.Task[None]] = set()
_in_process_llm_tasks: set[asyncio.Task[None]] = set()
_in_process_prediction_scoring_tasks: set[asyncio.Task[None]] = set()
_in_process_asset_promotion_tasks: set[asyncio.Task[None]] = set()

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


async def _run_analysis_asset_promotion(
    upload_session_id: UUID,
    asset_id: UUID,
    user_id: UUID,
) -> None:
    async with AsyncSessionLocal() as db:
        await AnalysisApplicationService(db).promote_pending_asset(
            upload_session_id=upload_session_id,
            asset_id=asset_id,
            user_id=user_id,
        )


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
    _run_async(_run_prediction_job_in_process(job_id))


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
    _run_async(_run_prediction_scoring_job_in_process(job_id))


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
    _run_async(_run_llm_evaluation_job_in_process(job_id, mode))


def _run_analysis_asset_promotion_in_process_entrypoint(
    upload_session_id: UUID,
    asset_id: UUID,
    user_id: UUID,
) -> None:
    _run_async(_run_analysis_asset_promotion(upload_session_id, asset_id, user_id))


def _run_async(coro: Coroutine[object, object, object]) -> None:
    asyncio.run(coro)


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


def _schedule_asset_promotion_job_in_process(
    upload_session_id: UUID,
    asset_id: UUID,
    user_id: UUID,
) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        context = copy_context()
        _fallback_executor.submit(
            context.run,
            _run_analysis_asset_promotion_in_process_entrypoint,
            upload_session_id,
            asset_id,
            user_id,
        )
        return

    task = loop.create_task(
        _run_analysis_asset_promotion(upload_session_id, asset_id, user_id),
        name=f"analysis-asset-promotion-{asset_id}",
    )
    _in_process_asset_promotion_tasks.add(task)
    task.add_done_callback(_in_process_asset_promotion_tasks.discard)


async def dispatch_prediction_job(job_id: UUID) -> str:
    with bound_log_context(job_id=str(job_id)):
        allow_in_process = settings.enable_in_process_jobs
        if allow_in_process and not _celery_workers_listen_to_queue(settings.celery_inference_queue):
            _schedule_prediction_job_in_process(job_id)
            log_event(
                logger,
                "prediction_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="in_process",
                queue_name=settings.celery_inference_queue,
                reason="no_celery_workers_for_inference_queue",
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
                dispatch_mode="in_process" if allow_in_process else "celery_only",
            )
            if not allow_in_process:
                raise DependencyAppError(
                    "Prediction job enqueue failed and in-process jobs are disabled."
                ) from exc
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
        allow_in_process = settings.enable_in_process_jobs
        if allow_in_process and not _celery_workers_listen_to_queue(settings.celery_scoring_queue):
            _schedule_llm_evaluation_job_in_process(job_id, mode)
            log_event(
                logger,
                "llm_evaluation_enqueued",
                job_id=str(job_id),
                mode=mode.value,
                status="queued",
                dispatch_mode="in_process",
                queue_name=settings.celery_scoring_queue,
                reason="no_celery_workers_for_scoring_queue",
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
                dispatch_mode="in_process" if allow_in_process else "celery_only",
            )
            if not allow_in_process:
                raise DependencyAppError(
                    "LLM evaluation enqueue failed and in-process jobs are disabled."
                ) from exc
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
        allow_in_process = settings.enable_in_process_jobs
        if allow_in_process and not _celery_workers_listen_to_queue(settings.celery_scoring_queue):
            _schedule_prediction_scoring_job_in_process(job_id)
            log_event(
                logger,
                "prediction_scoring_job_enqueued",
                job_id=str(job_id),
                status="queued",
                dispatch_mode="in_process",
                queue_name=settings.celery_scoring_queue,
                reason="no_celery_workers_for_scoring_queue",
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
                dispatch_mode="in_process" if allow_in_process else "celery_only",
            )
            if not allow_in_process:
                raise DependencyAppError(
                    "Prediction scoring enqueue failed and in-process jobs are disabled."
                ) from exc
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


async def dispatch_analysis_asset_promotion(
    *,
    upload_session_id: UUID,
    asset_id: UUID,
    user_id: UUID,
) -> str:
    _schedule_asset_promotion_job_in_process(upload_session_id, asset_id, user_id)
    log_event(
        logger,
        "analysis_asset_promotion_enqueued",
        upload_session_id=str(upload_session_id),
        asset_id=str(asset_id),
        user_id=str(user_id),
        status="queued",
        dispatch_mode="in_process",
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
        _run_async(_run_prediction_job(UUID(job_id)))
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
        _run_async(_run_llm_evaluation_job(UUID(job_id), evaluation_mode))
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
        _run_async(_run_prediction_scoring_job(UUID(job_id)))
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
