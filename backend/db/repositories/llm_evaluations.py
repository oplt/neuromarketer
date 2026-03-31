from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LLMEvaluationRecord
from backend.schemas.evaluators import EvaluationMode, EvaluationStatus


def _mode_value(mode: EvaluationMode | str) -> str:
    return mode.value if isinstance(mode, EvaluationMode) else str(mode)


class LLMEvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_job(self, job_id: UUID) -> list[LLMEvaluationRecord]:
        result = await self.session.execute(
            select(LLMEvaluationRecord)
            .where(LLMEvaluationRecord.job_id == job_id)
            .order_by(LLMEvaluationRecord.created_at.asc(), LLMEvaluationRecord.mode.asc())
        )
        return list(result.scalars())

    async def get_for_job_and_mode(
        self,
        *,
        job_id: UUID,
        mode: EvaluationMode | str,
    ) -> LLMEvaluationRecord | None:
        result = await self.session.execute(
            select(LLMEvaluationRecord).where(
                LLMEvaluationRecord.job_id == job_id,
                LLMEvaluationRecord.mode == _mode_value(mode),
            )
        )
        return result.scalar_one_or_none()

    async def queue_evaluation(
        self,
        *,
        existing: LLMEvaluationRecord | None,
        job_id: UUID,
        user_id: UUID,
        mode: EvaluationMode | str,
        model_provider: str,
        model_name: str,
        prompt_version: str,
        input_snapshot_json: dict,
    ) -> LLMEvaluationRecord:
        if existing is None:
            record = LLMEvaluationRecord(
                job_id=job_id,
                user_id=user_id,
                mode=_mode_value(mode),
                model_provider=model_provider,
                model_name=model_name,
                prompt_version=prompt_version,
                input_snapshot_json=input_snapshot_json,
                status=EvaluationStatus.QUEUED.value,
                error_message=None,
            )
            self.session.add(record)
            await self.session.flush()
            await self.session.refresh(record)
            return record

        existing.user_id = user_id
        existing.model_provider = model_provider
        existing.model_name = model_name
        existing.prompt_version = prompt_version
        existing.input_snapshot_json = input_snapshot_json
        existing.status = EvaluationStatus.QUEUED.value
        existing.error_message = None
        await self.session.flush()
        await self.session.refresh(existing)
        return existing

    async def acquire_for_processing(
        self,
        *,
        job_id: UUID,
        mode: EvaluationMode | str,
        stale_after_seconds: int,
    ) -> LLMEvaluationRecord | None:
        result = await self.session.execute(
            select(LLMEvaluationRecord)
            .where(
                LLMEvaluationRecord.job_id == job_id,
                LLMEvaluationRecord.mode == _mode_value(mode),
            )
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None

        now = datetime.now(timezone.utc)
        is_stale_processing = (
            record.status == EvaluationStatus.PROCESSING.value
            and record.updated_at < now - timedelta(seconds=stale_after_seconds)
        )
        if record.status not in {EvaluationStatus.QUEUED.value, EvaluationStatus.PROCESSING.value}:
            return None
        if record.status == EvaluationStatus.PROCESSING.value and not is_stale_processing:
            return None

        record.status = EvaluationStatus.PROCESSING.value
        record.error_message = None
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def mark_completed(
        self,
        *,
        record: LLMEvaluationRecord,
        evaluation_json: dict,
        model_provider: str,
        model_name: str,
        prompt_version: str,
    ) -> None:
        record.status = EvaluationStatus.COMPLETED.value
        record.error_message = None
        record.model_provider = model_provider
        record.model_name = model_name
        record.prompt_version = prompt_version
        record.evaluation_json = evaluation_json
        await self.session.flush()

    async def mark_failed(self, *, record: LLMEvaluationRecord, error_message: str) -> None:
        record.status = EvaluationStatus.FAILED.value
        record.error_message = error_message
        await self.session.flush()
