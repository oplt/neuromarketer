from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from backend.core.config import settings
from backend.core.exceptions import ConflictAppError, NotFoundAppError
from backend.core.log_context import bound_log_context
from backend.core.logging import get_logger, log_event, log_exception
from backend.db.models import InferenceJob, JobStatus, LLMEvaluationRecord
from backend.db.repositories import InferenceRepository, LLMEvaluationRepository
from backend.llm.context_builder import EvaluationContextBuilder
from backend.llm.evaluation_service import EvaluationRequest, EvaluationService
from backend.llm.llm_evaluators.registry import get_evaluator
from backend.schemas.evaluators import (
    EvaluationDispatchRequest,
    EvaluationListResponse,
    EvaluationMode,
    EvaluationRecordRead,
    EvaluationResult,
    EvaluationStatus,
)

logger = get_logger(__name__)


class AnalysisEvaluationApplicationService:
    def __init__(self, session) -> None:
        self.session = session
        self.inference = InferenceRepository(session)
        self.evaluations = LLMEvaluationRepository(session)
        self.context_builder = EvaluationContextBuilder()
        self._engine: EvaluationService | None = None

    def _get_engine(self) -> EvaluationService:
        if self._engine is None:
            self._engine = EvaluationService.from_settings()
        return self._engine

    async def request_evaluations(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
        payload: EvaluationDispatchRequest,
    ) -> EvaluationListResponse:
        with bound_log_context(job_id=str(job_id)):
            job = await self._get_owned_completed_job(user_id=user_id, job_id=job_id)
            analysis_result = self._get_loaded_analysis_result(job)
            snapshot: dict | None = None
            dispatched_modes: list[EvaluationMode] = []
            records: list[LLMEvaluationRecord] = []

            for mode in payload.modes:
                existing = await self.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
                if existing is not None:
                    existing = await self._expire_stale_processing_record(existing)

                if existing is not None and not payload.force_refresh and existing.status != EvaluationStatus.FAILED.value:
                    records.append(existing)
                    continue

                if snapshot is None:
                    if analysis_result is None:
                        raise ConflictAppError("Analysis must be completed before LLM evaluation can run.")
                    snapshot = self.context_builder.build(
                        job=job,
                        analysis_result=analysis_result,
                        creative_version=self._get_loaded_creative_version(job),
                    )
                evaluator = get_evaluator(mode)
                record = await self.evaluations.queue_evaluation(
                    existing=existing,
                    job_id=job.id,
                    user_id=user_id,
                    mode=mode,
                    model_provider=settings.llm_provider,
                    model_name=settings.llm_model,
                    prompt_version=evaluator.prompt_version,
                    input_snapshot_json=snapshot,
                )
                records.append(record)
                dispatched_modes.append(mode)

            await self.session.commit()

            if dispatched_modes:
                from backend.tasks import dispatch_llm_evaluation_job

                for mode in dispatched_modes:
                    await dispatch_llm_evaluation_job(job_id=job_id, mode=mode)

            refreshed_records = await self._get_requested_records(job_id=job_id, modes=payload.modes)
            return EvaluationListResponse(items=[self._to_read(record) for record in refreshed_records])

    async def list_evaluations(self, *, user_id: UUID, job_id: UUID) -> EvaluationListResponse:
        with bound_log_context(job_id=str(job_id)):
            await self._get_owned_job(user_id=user_id, job_id=job_id)
            records = await self.evaluations.list_for_job(job_id)
            records = await self._expire_stale_processing_records(records)
            return EvaluationListResponse(items=[self._to_read(record) for record in records])

    async def get_evaluation(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
        mode: EvaluationMode,
    ) -> EvaluationRecordRead:
        with bound_log_context(job_id=str(job_id)):
            await self._get_owned_job(user_id=user_id, job_id=job_id)
            record = await self.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
            if record is None:
                raise NotFoundAppError("LLM evaluation not found.")
            record = await self._expire_stale_processing_record(record)
            return self._to_read(record)

    async def process_evaluation(self, *, job_id: UUID, mode: EvaluationMode) -> EvaluationRecordRead | None:
        with bound_log_context(job_id=str(job_id)):
            job = await self.inference.get_job_for_analysis_evaluation(job_id)
            if job is None:
                log_event(
                    logger,
                    "llm_evaluation_job_missing",
                    level="warning",
                    job_id=str(job_id),
                    mode=mode.value,
                    status="skipped",
                )
                return None

            analysis_result = self._get_loaded_analysis_result(job)
            if analysis_result is None or job.status != JobStatus.SUCCEEDED:
                log_event(
                    logger,
                    "llm_evaluation_analysis_incomplete",
                    level="warning",
                    job_id=str(job_id),
                    mode=mode.value,
                    status=job.status.value,
                )
                return None

            record = await self.evaluations.acquire_for_processing(
                job_id=job_id,
                mode=mode,
                stale_after_seconds=settings.llm_processing_stale_after_seconds,
            )
            if record is None:
                return None

            context = record.input_snapshot_json or self.context_builder.build(
                job=job,
                analysis_result=analysis_result,
                creative_version=self._get_loaded_creative_version(job),
            )
            await self.session.commit()

            try:
                response = await self._get_engine().evaluate(EvaluationRequest(mode=mode, context=context))
                refreshed_record = await self.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
                if refreshed_record is None:
                    return None
                await self.evaluations.mark_completed(
                    record=refreshed_record,
                    evaluation_json=response.result.model_dump(mode="json"),
                    model_provider=response.provider,
                    model_name=response.model,
                    prompt_version=response.prompt_version,
                )
                await self.session.commit()
                completed_record = await self.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
                if completed_record is None:
                    return None
                return self._to_read(completed_record)
            except Exception as exc:
                log_exception(
                    logger,
                    "llm_evaluation_processing_failed",
                    exc,
                    job_id=str(job_id),
                    mode=mode.value,
                    status="failed",
                )
                await self.session.rollback()
                refreshed_record = await self.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
                if refreshed_record is not None:
                    await self.evaluations.mark_failed(record=refreshed_record, error_message=str(exc))
                    await self.session.commit()
                    failed_record = await self.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
                    if failed_record is None:
                        return None
                    return self._to_read(failed_record)
                return None

    async def _get_owned_job(self, *, user_id: UUID, job_id: UUID) -> InferenceJob:
        job = await self.inference.get_job_for_analysis_evaluation(job_id)
        if job is None or job.created_by_user_id != user_id:
            raise NotFoundAppError("Analysis job not found.")
        return job

    async def _get_owned_completed_job(self, *, user_id: UUID, job_id: UUID) -> InferenceJob:
        job = await self._get_owned_job(user_id=user_id, job_id=job_id)
        if job.status != JobStatus.SUCCEEDED or self._get_loaded_analysis_result(job) is None:
            raise ConflictAppError("Analysis must be completed before LLM evaluation can run.")
        return job

    def _get_loaded_analysis_result(self, job: InferenceJob):
        return job.__dict__.get("analysis_result_record")

    def _get_loaded_creative_version(self, job: InferenceJob):
        return job.__dict__.get("creative_version")

    async def _get_requested_records(
        self,
        *,
        job_id: UUID,
        modes: list[EvaluationMode],
    ) -> list[LLMEvaluationRecord]:
        all_records = await self.evaluations.list_for_job(job_id)
        record_by_mode = {record.mode: record for record in all_records}
        return [
            record_by_mode[mode.value]
            for mode in modes
            if mode.value in record_by_mode
        ]

    def _to_read(self, record: LLMEvaluationRecord) -> EvaluationRecordRead:
        evaluation_json = None
        if record.evaluation_json:
            try:
                evaluation_json = EvaluationResult.model_validate(record.evaluation_json)
            except Exception:
                log_event(
                    logger,
                    "llm_evaluation_cached_json_invalid",
                    level="warning",
                    job_id=str(record.job_id),
                    record_id=str(record.id),
                    mode=record.mode,
                    status="invalid",
                )
        return EvaluationRecordRead(
            id=record.id,
            job_id=record.job_id,
            user_id=record.user_id,
            mode=EvaluationMode(record.mode),
            status=record.status,
            model_provider=record.model_provider,
            model_name=record.model_name,
            prompt_version=record.prompt_version,
            evaluation_json=evaluation_json,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _is_stale_processing_record(self, record: LLMEvaluationRecord) -> bool:
        if record.status != EvaluationStatus.PROCESSING.value:
            return False
        return record.updated_at < datetime.now(timezone.utc) - timedelta(
            seconds=settings.llm_processing_stale_after_seconds
        )

    async def _expire_stale_processing_record(self, record: LLMEvaluationRecord) -> LLMEvaluationRecord:
        if not self._is_stale_processing_record(record):
            return record

        await self.evaluations.mark_failed(
            record=record,
            error_message="Evaluation processing timed out. Retry the evaluation.",
        )
        await self.session.commit()
        refreshed_record = await self.evaluations.get_for_job_and_mode(job_id=record.job_id, mode=record.mode)
        return refreshed_record or record

    async def _expire_stale_processing_records(
        self,
        records: list[LLMEvaluationRecord],
    ) -> list[LLMEvaluationRecord]:
        stale_records = [record for record in records if self._is_stale_processing_record(record)]
        if not stale_records:
            return records

        for record in stale_records:
            await self.evaluations.mark_failed(
                record=record,
                error_message="Evaluation processing timed out. Retry the evaluation.",
            )

        await self.session.commit()
        if not records:
            return records
        return await self.evaluations.list_for_job(records[0].job_id)
