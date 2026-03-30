from __future__ import annotations

from uuid import UUID

from backend.application.services.predictions import PredictionApplicationService
from backend.db.session import session_scope


async def process_prediction_job(job_id: UUID) -> None:
    async with session_scope() as db:
        await PredictionApplicationService(db).process_prediction_job(job_id)
