from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.analysis_job_processor import AnalysisJobProcessor
from backend.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.core.log_context import bound_log_context
from backend.core.logging import get_logger, log_event
from backend.core.metrics import metrics
from backend.db.models import JobStatus
from backend.db.repositories import CreativeRepository, InferenceRepository
from backend.schemas.schemas import PredictRequest
from backend.services.tribe_inference_service import TribeInferenceService

logger = get_logger(__name__)


class PredictionApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.creatives = CreativeRepository(session)
        self.inference = InferenceRepository(session)
        self.tribe_inference = TribeInferenceService()

    async def create_prediction_job(self, payload: PredictRequest):
        with bound_log_context(
            project_id=str(payload.project_id),
            creative_id=str(payload.creative_id),
            creative_version_id=str(payload.creative_version_id),
        ):
            creative = await self.creatives.get_creative(payload.creative_id)
            if creative is None:
                raise NotFoundAppError("Creative not found.")
            if creative.project_id != payload.project_id:
                raise ValidationAppError("Creative does not belong to project.")

            creative_version = await self.creatives.get_creative_version(
                payload.creative_version_id
            )
            if creative_version is None:
                raise NotFoundAppError("Creative version not found.")
            if creative_version.creative_id != payload.creative_id:
                raise ValidationAppError("Creative version does not belong to creative.")

            modality = self.tribe_inference.resolve_modality(creative_version)
            self.tribe_inference.assert_ready_for_inference(
                creative_version=creative_version, modality=modality
            )

            job = await self.inference.create_job(
                project_id=payload.project_id,
                creative_id=payload.creative_id,
                creative_version_id=payload.creative_version_id,
                created_by_user_id=payload.created_by_user_id,
                request_payload={
                    "audience_context": payload.audience_context,
                    "campaign_context": payload.campaign_context,
                },
                runtime_params=payload.runtime_params,
            )
            await self.session.commit()
            hydrated = await self.inference.get_job_status_light(job.id)
            log_event(
                logger,
                "prediction_job_created",
                job_id=str(job.id),
                modality=modality,
                status=job.status.value,
                audience_context_keys=sorted((payload.audience_context or {}).keys()),
                campaign_context_keys=sorted((payload.campaign_context or {}).keys()),
            )
            return hydrated or job

    async def get_job(self, job_id: UUID):
        job = await self.inference.get_job_result_full(job_id)
        if job is None:
            raise NotFoundAppError("Job not found.")
        return job

    async def get_job_status_light(self, job_id: UUID):
        job = await self.inference.get_job_status_light(job_id)
        if job is None:
            raise NotFoundAppError("Job not found.")
        return job

    async def get_analysis_job_status_light_for_user(self, *, job_id: UUID, user_id: UUID):
        job = await self.inference.get_analysis_job_light_for_user(job_id=job_id, user_id=user_id)
        if job is None:
            raise NotFoundAppError("Job not found.")
        return job

    async def get_prediction_result(self, prediction_result_id: UUID):
        prediction = await self.inference.get_prediction_result_full(prediction_result_id)
        if prediction is None:
            raise NotFoundAppError("Prediction result not found.")
        return prediction

    async def process_prediction_job(self, job_id: UUID) -> None:
        await AnalysisJobProcessor(self.session).process(job_id)

    async def process_prediction_scoring_job(self, job_id: UUID) -> None:
        await AnalysisJobProcessor(self.session).process_scoring(job_id)

    async def rerun_job(self, *, job_id: UUID, user_id: UUID):
        """Reset a failed or canceled job to QUEUED so it can be re-dispatched.

        Only FAILED and CANCELED jobs may be rerun.  RUNNING/QUEUED jobs are
        rejected to prevent duplicate workers on the same job.
        """
        job = await self.inference.get_job_status_light(job_id)
        if job is None:
            raise NotFoundAppError("Job not found.")
        if job.created_by_user_id is not None and job.created_by_user_id != user_id:
            raise NotFoundAppError("Job not found.")
        if job.status not in (JobStatus.FAILED, JobStatus.CANCELED):
            raise ConflictAppError(
                f"Only failed or canceled jobs can be rerun. Current status: {job.status.value}."
            )
        await self.inference.reset_job_for_rerun(job)
        log_event(
            logger,
            "prediction_job_rerun_requested",
            job_id=str(job_id),
            user_id=str(user_id),
            status=JobStatus.QUEUED.value,
        )
        return await self.inference.get_job_status_light(job_id)

    async def mark_job_failed(self, job_id: UUID, error_message: str) -> None:
        job = await self.inference.get_job(job_id)
        if job is None:
            return
        await self.inference.mark_job_failed(job, error_message)
        metrics.increment("prediction_jobs_total", labels={"status": "failed"})
