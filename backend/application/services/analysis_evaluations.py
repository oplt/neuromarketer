from __future__ import annotations

from uuid import UUID

from backend.core.config import settings
from backend.core.exceptions import ConflictAppError, NotFoundAppError
from backend.core.logging import get_logger
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
        job = await self._get_owned_completed_job(user_id=user_id, job_id=job_id)
        snapshot: dict | None = None
        dispatched_modes: list[EvaluationMode] = []
        records: list[LLMEvaluationRecord] = []

        for mode in payload.modes:
            existing = await self.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
            if existing is not None and not payload.force_refresh:
                records.append(existing)
                continue

            if snapshot is None:
                snapshot = self.context_builder.build(job=job, analysis_result=job.analysis_result_record)
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
        await self._get_owned_job(user_id=user_id, job_id=job_id)
        records = await self.evaluations.list_for_job(job_id)
        return EvaluationListResponse(items=[self._to_read(record) for record in records])

    async def get_evaluation(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
        mode: EvaluationMode,
    ) -> EvaluationRecordRead:
        await self._get_owned_job(user_id=user_id, job_id=job_id)
        record = await self.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
        if record is None:
            raise NotFoundAppError("LLM evaluation not found.")
        return self._to_read(record)

    async def process_evaluation(self, *, job_id: UUID, mode: EvaluationMode) -> EvaluationRecordRead | None:
        job = await self.inference.get_job_for_analysis_evaluation(job_id)
        if job is None:
            logger.warning(
                "Skipping missing LLM evaluation job.",
                extra={"event": "llm_evaluation_job_missing", "extra_fields": {"job_id": str(job_id)}},
            )
            return None
        if job.analysis_result_record is None or job.status != JobStatus.SUCCEEDED:
            logger.warning(
                "Skipping LLM evaluation because analysis is incomplete.",
                extra={
                    "event": "llm_evaluation_analysis_incomplete",
                    "extra_fields": {"job_id": str(job_id), "mode": mode.value, "status": job.status.value},
                },
            )
            return None

        record = await self.evaluations.acquire_for_processing(
            job_id=job_id,
            mode=mode,
            stale_after_seconds=settings.llm_processing_stale_after_seconds,
        )
        if record is None:
            return None

        await self.session.commit()

        try:
            context = record.input_snapshot_json or self.context_builder.build(
                job=job,
                analysis_result=job.analysis_result_record,
            )
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
            return self._to_read(refreshed_record)
        except Exception as exc:
            logger.exception(
                "LLM evaluation processing failed.",
                extra={
                    "event": "llm_evaluation_processing_failed",
                    "extra_fields": {"job_id": str(job_id), "mode": mode.value, "error": str(exc)},
                },
            )
            await self.session.rollback()
            refreshed_record = await self.evaluations.get_for_job_and_mode(job_id=job_id, mode=mode)
            if refreshed_record is not None:
                await self.evaluations.mark_failed(record=refreshed_record, error_message=str(exc))
                await self.session.commit()
                return self._to_read(refreshed_record)
            return None

    async def _get_owned_job(self, *, user_id: UUID, job_id: UUID) -> InferenceJob:
        job = await self.inference.get_job_for_analysis_evaluation(job_id)
        if job is None or job.created_by_user_id != user_id:
            raise NotFoundAppError("Analysis job not found.")
        return job

    async def _get_owned_completed_job(self, *, user_id: UUID, job_id: UUID) -> InferenceJob:
        job = await self._get_owned_job(user_id=user_id, job_id=job_id)
        if job.status != JobStatus.SUCCEEDED or job.analysis_result_record is None:
            raise ConflictAppError("Analysis must be completed before LLM evaluation can run.")
        return job

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
                logger.warning(
                    "Stored evaluation JSON failed validation during serialization.",
                    extra={
                        "event": "llm_evaluation_cached_json_invalid",
                        "extra_fields": {"record_id": str(record.id), "mode": record.mode},
                    },
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
