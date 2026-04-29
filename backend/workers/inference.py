from __future__ import annotations

from uuid import UUID

from backend.application.services.analysis_job_processor import AnalysisJobProcessor
from backend.db.session import session_scope


async def process_prediction_job(job_id: UUID) -> None:
    processor = AnalysisJobProcessor()

    async with session_scope() as db:
        job = await processor.acquire_job(db, job_id)

    if job is None:
        return

    result = await processor.run_inference(job)

    async with session_scope() as db:
        await processor.persist_inference(db, job_id, result)
