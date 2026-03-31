from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.log_context import bound_log_context
from backend.core.exceptions import NotFoundAppError
from backend.core.logging import duration_ms, get_logger, log_event
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
            log_event(logger, "prediction_job_skipped", job_id=str(job_id), status="skipped")
            return

        with bound_log_context(
            job_id=str(job.id),
            project_id=str(job.project_id),
            creative_id=str(job.creative_id),
            creative_version_id=str(job.creative_version_id),
        ):
            creative_version = await self.creatives.get_creative_version(job.creative_version_id)
            if creative_version is None:
                raise NotFoundAppError("Creative version not found.")

            modality = self.tribe_inference.resolve_modality(creative_version)
            objective = ((job.request_payload or {}).get("campaign_context") or {}).get("objective")
            total_started_at = time.perf_counter()
            log_event(
                logger,
                "prediction_job_started",
                job_id=str(job.id),
                creative_version_id=str(creative_version.id),
                modality=modality,
                status="running",
            )

            execution = self.tribe_inference.run_for_version(
                creative_version=creative_version,
                request_payload=job.request_payload or {},
                runtime_params=job.runtime_params or {},
            )

            scoring_bundle = await self.scoring.score(
                reduced_feature_vector=execution.runtime_output.reduced_feature_vector,
                region_activation_summary=execution.runtime_output.region_activation_summary,
                context=job.request_payload or {},
                modality=execution.modality,
            )

            postprocess_started_at = time.perf_counter()
            dashboard_payload = self.postprocessor.build_dashboard_payload(
                runtime_output=execution.runtime_output,
                scoring_bundle=scoring_bundle,
                modality=execution.modality,
                objective=str(objective).strip() if isinstance(objective, str) and objective.strip() else None,
                source_label=execution.source_label,
            )
            postprocess_finished_at = time.perf_counter()

            persistence_started_at = time.perf_counter()
            log_event(
                logger,
                "prediction_persist_started",
                job_id=str(job.id),
                modality=execution.modality,
                status="running",
            )
            prediction_result = await self.inference.replace_prediction_result(
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
            persistence_finished_at = time.perf_counter()

            total_finished_at = time.perf_counter()
            log_event(
                logger,
                "prediction_persist_finished",
                prediction_result_id=str(prediction_result.id),
                modality=execution.modality,
                duration_ms=duration_ms(persistence_started_at, persistence_finished_at),
                status="succeeded",
            )
            log_event(
                logger,
                "prediction_job_succeeded",
                prediction_result_id=str(prediction_result.id),
                modality=execution.modality,
                duration_ms=duration_ms(total_started_at, total_finished_at),
                postprocess_duration_ms=duration_ms(postprocess_started_at, postprocess_finished_at),
                status="succeeded",
            )
            metrics.increment("prediction_jobs_total", labels={"status": "succeeded"})
