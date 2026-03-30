from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import NotFoundAppError
from backend.core.logging import get_logger
from backend.core.metrics import metrics
from backend.db.repositories import CreativeRepository, InferenceRepository
from backend.services.analysis_postprocessor import AnalysisPostprocessor
from backend.services.scoring import NeuroScoringService
from backend.services.tribe_inference_service import TribeInferenceService

logger = get_logger(__name__)


class AnalysisJobProcessor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.creatives = CreativeRepository(session)
        self.inference = InferenceRepository(session)
        self.tribe_inference = TribeInferenceService()
        self.scoring = NeuroScoringService()
        self.postprocessor = AnalysisPostprocessor()

    async def process(self, job_id: UUID) -> None:
        job = await self.inference.acquire_job(
            job_id,
            stale_after_seconds=settings.celery_job_stale_after_seconds,
        )
        if job is None:
            logger.info(
                "Analysis job skipped.",
                extra={"event": "analysis_job_skipped", "extra_fields": {"job_id": str(job_id)}},
            )
            return

        creative_version = await self.creatives.get_creative_version(job.creative_version_id)
        if creative_version is None:
            raise NotFoundAppError("Creative version not found.")

        objective = ((job.request_payload or {}).get("campaign_context") or {}).get("objective")
        total_started_at = time.perf_counter()
        logger.info(
            "Analysis job started.",
            extra={
                "event": "analysis_job_started",
                "extra_fields": {
                    "job_id": str(job.id),
                    "creative_version_id": str(creative_version.id),
                },
            },
        )

        execution = self.tribe_inference.run_for_version(
            creative_version=creative_version,
            request_payload=job.request_payload or {},
            runtime_params=job.runtime_params or {},
        )

        scoring_started_at = time.perf_counter()
        scoring_bundle = await self.scoring.score(
            reduced_feature_vector=execution.runtime_output.reduced_feature_vector,
            region_activation_summary=execution.runtime_output.region_activation_summary,
            context=job.request_payload or {},
            modality=execution.modality,
        )
        scoring_duration_seconds = time.perf_counter() - scoring_started_at
        logger.info(
            "Analysis scoring completed.",
            extra={
                "event": "analysis_scoring_finished",
                "extra_fields": {
                    "job_id": str(job.id),
                    "duration_seconds": round(scoring_duration_seconds, 3),
                    "modality": execution.modality,
                },
            },
        )

        postprocess_started_at = time.perf_counter()
        dashboard_payload = self.postprocessor.build_dashboard_payload(
            runtime_output=execution.runtime_output,
            scoring_bundle=scoring_bundle,
            modality=execution.modality,
            objective=str(objective).strip() if isinstance(objective, str) and objective.strip() else None,
            source_label=execution.source_label,
        )
        postprocess_duration_seconds = time.perf_counter() - postprocess_started_at
        logger.info(
            "Analysis postprocessing completed.",
            extra={
                "event": "analysis_postprocess_finished",
                "extra_fields": {
                    "job_id": str(job.id),
                    "duration_seconds": round(postprocess_duration_seconds, 3),
                    "timeline_points": len(dashboard_payload.timeline_json),
                    "segments": len(dashboard_payload.segments_json),
                    "recommendations": len(dashboard_payload.recommendations_json),
                },
            },
        )

        persistence_started_at = time.perf_counter()
        await self.inference.replace_prediction_result(
            job=job,
            runtime_output=execution.runtime_output,
            scoring_bundle=scoring_bundle,
            model_name=self.tribe_inference.runtime.model_name,
        )
        await self.inference.replace_analysis_result(
            job=job,
            summary_json=dashboard_payload.summary_json,
            metrics_json=dashboard_payload.metrics_json,
            timeline_json=dashboard_payload.timeline_json,
            segments_json=dashboard_payload.segments_json,
            visualizations_json=dashboard_payload.visualizations_json,
            recommendations_json=dashboard_payload.recommendations_json,
        )
        await self.inference.mark_job_succeeded(job)
        persistence_duration_seconds = time.perf_counter() - persistence_started_at

        total_duration_seconds = time.perf_counter() - total_started_at
        logger.info(
            "Analysis job persisted.",
            extra={
                "event": "analysis_job_persisted",
                "extra_fields": {
                    "job_id": str(job.id),
                    "modality": execution.modality,
                    "tribe_inference_seconds": round(execution.inference_duration_seconds, 3),
                    "postprocess_seconds": round(postprocess_duration_seconds, 3),
                    "persistence_seconds": round(persistence_duration_seconds, 3),
                    "total_duration_seconds": round(total_duration_seconds, 3),
                },
            },
        )
        metrics.increment("prediction_jobs_total", labels={"status": "succeeded"})
