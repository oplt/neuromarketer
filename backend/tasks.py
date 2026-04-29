from __future__ import annotations

import asyncio
import atexit
import time
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
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
from backend.db.models import JobStatus
from backend.db.repositories import CreativeRepository, InferenceRepository
from backend.db.session import AsyncSessionLocal, safe_rollback
from backend.schemas.evaluators import EvaluationMode
from backend.services.analysis_goal_taxonomy import (
    normalize_analysis_channel,
    normalize_goal_template,
)
from backend.services.analysis_job_events import publish_analysis_job_event
from backend.services.analysis_postprocessor import AnalysisPostprocessor
from backend.services.tribe_inference_service import TribeInferenceService

logger = get_logger(__name__)

def should_use_in_process_jobs() -> bool:
    if not settings.enable_in_process_jobs:
        return False
    app_env = (settings.app_env or "development").strip().lower()
    # Never allow in-process fallback outside dev/test. Even "force"
    # can overwhelm API worker capacity in real environments.
    return app_env in {"development", "test"}


def _is_non_dev_env() -> bool:
    app_env = (settings.app_env or "development").strip().lower()
    return app_env not in {"development", "test"}


# ThreadPoolExecutor for in-process fallback jobs.
# Using a bounded pool (max_workers=4) with wait=True on shutdown so
# SIGTERM does not kill running analysis jobs mid-flight.
_fallback_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="prediction-job")
atexit.register(lambda: _fallback_executor.shutdown(wait=True, cancel_futures=False))


@asynccontextmanager
async def _failure_recovery_session(db):
    if await safe_rollback(db):
        yield db
        return

    async with AsyncSessionLocal() as recovery_db:
        yield recovery_db


async def _run_prediction_job(job_id: UUID) -> None:
    async with AsyncSessionLocal() as db:
        try:
            await PredictionApplicationService(db).process_prediction_job(job_id)
            await db.commit()
        except Exception as exc:
            async with _failure_recovery_session(db) as failure_db:
                repo = InferenceRepository(failure_db)
                job = await repo.get_job(job_id)
                if job is not None and job.status != JobStatus.FAILED:
                    await PredictionApplicationService(failure_db).mark_job_failed(job_id, str(exc))
                    await failure_db.commit()
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
            async with _failure_recovery_session(db) as failure_db:
                await _finalize_failed_scoring_job(
                    failure_db,
                    job_id=job_id,
                    error_message=str(exc),
                )
                await failure_db.commit()
            await publish_analysis_job_event(
                job_id=job_id,
                event_type="job_failed",
                payload={"status": "failed", "error_message": str(exc)},
            )
            raise


async def _finalize_failed_scoring_job(
    db, *, job_id: UUID, error_message: str
) -> None:
    """Persist the scoring failure as one atomic transaction.

    Preserves the TRIBE-only partial result (best-effort, isolated in a
    SAVEPOINT) AND transitions the job to ``FAILED`` against the same
    session so the caller's single ``commit`` either persists both
    writes or neither. This eliminates the previous double-commit race
    where the partial-result write could land while the
    ``mark_job_failed`` commit failed, leaving the database with a
    visible partial row but a non-failed job status.

    Failure modes:

    * ``_preserve_partial_scoring_result`` raises a Python error → we
      log it and proceed; ``partial_result_available`` becomes ``False``
      so the failure metadata reflects reality.
    * ``_preserve_partial_scoring_result`` raises a DB error inside the
      SAVEPOINT → SQLAlchemy rolls back the SAVEPOINT only; the outer
      transaction stays alive, so ``mark_job_failed`` and the caller's
      commit still run.
    * The outer transaction's commit fails → nothing is persisted; the
      caller re-raises and Celery's retry path handles it.
    """

    repo = InferenceRepository(db)
    job = await repo.get_job_with_prediction(job_id)
    if job is None:
        return

    partial_result_available = False
    if job.prediction is not None:
        try:
            async with db.begin_nested():
                partial_result_available = await _preserve_partial_scoring_result(
                    db,
                    repo=repo,
                    job=job,
                    error_message=error_message,
                )
        except Exception as preserve_exc:
            log_exception(
                logger,
                "prediction_scoring_partial_result_preserve_failed",
                preserve_exc,
                job_id=str(job_id),
                level="warning",
                status="degraded",
            )
            partial_result_available = False

    if job.status != JobStatus.FAILED:
        await repo.mark_job_failed(
            job,
            error_message,
            partial_result_available=partial_result_available,
        )


async def _preserve_partial_scoring_result(
    db,
    *,
    repo: InferenceRepository,
    job,
    error_message: str,
) -> bool:
    """Write the TRIBE-only fallback payload for a scoring failure.

    The caller owns the transaction (and any surrounding SAVEPOINT);
    this function only issues writes through ``db``. Returns ``True``
    when an ``analysis_results`` row was upserted with the fallback
    payload, ``False`` when the prerequisites for a fallback are not
    met (e.g. the creative version is gone).
    """

    creatives = CreativeRepository(db)
    tribe_inference = TribeInferenceService()
    postprocessor = AnalysisPostprocessor()

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
        job_id=str(job.id),
        modality=modality,
        status="preserved",
    )
    return True


# Backwards-compat shim: keep the old name resolvable for any internal
# import path that still references it. The implementation now lives in
# ``_finalize_failed_scoring_job`` which always runs in a single
# transaction.
async def _preserve_failed_scoring_result(db, *, job_id: UUID, error_message: str) -> bool:
    repo = InferenceRepository(db)
    job = await repo.get_job_with_prediction(job_id)
    if job is None or job.prediction is None:
        return False
    return await _preserve_partial_scoring_result(
        db, repo=repo, job=job, error_message=error_message
    )


async def _run_llm_evaluation_job(job_id: UUID, mode: EvaluationMode) -> None:
    async with AsyncSessionLocal() as db:
        service = AnalysisEvaluationApplicationService(db)
        try:
            await service.process_evaluation(job_id=job_id, mode=mode)
            await db.commit()
        except Exception as exc:
            async with _failure_recovery_session(db) as failure_db:
                failure_service = (
                    service
                    if failure_db is db
                    else AnalysisEvaluationApplicationService(failure_db)
                )
                record = await failure_service.evaluations.get_for_job_and_mode(
                    job_id=job_id, mode=mode
                )
                if record is not None:
                    failure_metadata = getattr(exc, "telemetry", None)
                    await failure_service.evaluations.mark_failed(
                        record=record,
                        error_message=str(exc),
                        metadata_json=failure_metadata
                        if isinstance(failure_metadata, dict)
                        else record.metadata_json,
                    )
                    await failure_db.commit()
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
        await db.commit()


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


def _submit_in_process(callback, *args) -> None:
    context = copy_context()
    _fallback_executor.submit(context.run, callback, *args)


def _schedule_prediction_job_in_process(job_id: UUID) -> None:
    _submit_in_process(_run_prediction_job_in_process_entrypoint, job_id)


def _schedule_llm_evaluation_job_in_process(job_id: UUID, mode: EvaluationMode) -> None:
    _submit_in_process(_run_llm_evaluation_job_in_process_entrypoint, job_id, mode)


def _schedule_prediction_scoring_job_in_process(job_id: UUID) -> None:
    _submit_in_process(_run_prediction_scoring_job_in_process_entrypoint, job_id)


def _schedule_asset_promotion_job_in_process(
    upload_session_id: UUID,
    asset_id: UUID,
    user_id: UUID,
) -> None:
    _submit_in_process(
        _run_analysis_asset_promotion_in_process_entrypoint,
        upload_session_id,
        asset_id,
        user_id,
    )


async def dispatch_prediction_job(job_id: UUID) -> str:
    with bound_log_context(job_id=str(job_id)):
        allow_in_process = should_use_in_process_jobs()
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
            metrics.increment(
                "prediction_job_dispatch_total",
                labels={"dispatch_mode": "celery", "job_type": "inference"},
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
            if _is_non_dev_env():
                log_event(
                    logger,
                    "in_process_prediction_dispatch_non_dev",
                    level="warning",
                    job_id=str(job_id),
                    queue_name=settings.celery_inference_queue,
                    status="forced_fallback",
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
            metrics.increment(
                "prediction_job_dispatch_total",
                labels={"dispatch_mode": "in_process", "job_type": "inference"},
            )
            return "in_process"


async def dispatch_llm_evaluation_job(job_id: UUID, mode: EvaluationMode) -> str:
    with bound_log_context(job_id=str(job_id), mode=mode.value):
        allow_in_process = should_use_in_process_jobs()
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
            metrics.increment(
                "prediction_job_dispatch_total",
                labels={"dispatch_mode": "celery", "job_type": "llm_evaluation"},
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
            if _is_non_dev_env():
                log_event(
                    logger,
                    "in_process_llm_evaluation_dispatch_non_dev",
                    level="warning",
                    job_id=str(job_id),
                    mode=mode.value,
                    queue_name=settings.celery_scoring_queue,
                    status="forced_fallback",
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
            metrics.increment(
                "prediction_job_dispatch_total",
                labels={"dispatch_mode": "in_process", "job_type": "llm_evaluation"},
            )
            return "in_process"


async def dispatch_prediction_scoring_job(job_id: UUID) -> str:
    with bound_log_context(job_id=str(job_id)):
        allow_in_process = should_use_in_process_jobs()
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
            metrics.increment(
                "prediction_job_dispatch_total",
                labels={"dispatch_mode": "celery", "job_type": "scoring"},
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
            if _is_non_dev_env():
                log_event(
                    logger,
                    "in_process_scoring_dispatch_non_dev",
                    level="warning",
                    job_id=str(job_id),
                    queue_name=settings.celery_scoring_queue,
                    status="forced_fallback",
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
            metrics.increment(
                "prediction_job_dispatch_total",
                labels={"dispatch_mode": "in_process", "job_type": "scoring"},
            )
            return "in_process"


async def dispatch_analysis_asset_promotion(
    *,
    upload_session_id: UUID,
    asset_id: UUID,
    user_id: UUID,
) -> str:
    allow_in_process = should_use_in_process_jobs()
    try:
        process_analysis_asset_promotion_task.apply_async(
            args=[str(upload_session_id), str(asset_id), str(user_id)],
            queue=settings.celery_scoring_queue,
        )
        log_event(
            logger,
            "analysis_asset_promotion_enqueued",
            upload_session_id=str(upload_session_id),
            asset_id=str(asset_id),
            user_id=str(user_id),
            status="queued",
            dispatch_mode="celery",
            queue_name=settings.celery_scoring_queue,
        )
        metrics.increment(
            "prediction_job_dispatch_total",
            labels={"dispatch_mode": "celery", "job_type": "asset_promotion"},
        )
        return "celery"
    except Exception as exc:
        log_exception(
            logger,
            "analysis_asset_promotion_enqueue_failed",
            exc,
            upload_session_id=str(upload_session_id),
            asset_id=str(asset_id),
            user_id=str(user_id),
            status="failed",
            dispatch_mode="in_process" if allow_in_process else "celery_only",
        )
        if not allow_in_process:
            raise DependencyAppError(
                "Asset promotion enqueue failed and in-process jobs are disabled."
            ) from exc
        if _is_non_dev_env():
            log_event(
                logger,
                "in_process_asset_promotion_dispatch_non_dev",
                level="warning",
                upload_session_id=str(upload_session_id),
                asset_id=str(asset_id),
                user_id=str(user_id),
                status="forced_fallback",
            )
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
        metrics.increment(
            "prediction_job_dispatch_total",
            labels={"dispatch_mode": "in_process", "job_type": "asset_promotion"},
        )
        return "in_process"


@celery_app.task(
    name="tasks.process_analysis_asset_promotion",
    bind=True,
    max_retries=0,
    queue=settings.celery_scoring_queue,
)
def process_analysis_asset_promotion_task(
    self,
    upload_session_id: str,
    asset_id: str,
    user_id: str,
) -> None:
    start = time.perf_counter()
    try:
        _run_async(_run_analysis_asset_promotion(UUID(upload_session_id), UUID(asset_id), UUID(user_id)))
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "succeeded", "phase": "asset_promotion"},
        )
    except (ConfigurationAppError, DependencyAppError, NotFoundAppError, ValidationAppError) as exc:
        log_exception(
            logger,
            "analysis_asset_promotion_failed",
            exc,
            level="warning",
            upload_session_id=upload_session_id,
            asset_id=asset_id,
            user_id=user_id,
            task_id=self.request.id,
            status="failed",
        )
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed", "phase": "asset_promotion"},
        )
        raise
    except Exception as exc:
        log_exception(
            logger,
            "analysis_asset_promotion_unhandled_error",
            exc,
            upload_session_id=upload_session_id,
            asset_id=asset_id,
            user_id=user_id,
            task_id=self.request.id,
            status="failed",
            duration_ms=duration_ms(start, time.perf_counter()),
        )
        metrics.observe(
            "prediction_job_duration_seconds",
            time.perf_counter() - start,
            labels={"status": "failed", "phase": "asset_promotion"},
        )
        raise


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
