from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.log_context import bound_log_context
from backend.core.exceptions import NotFoundAppError
from backend.core.logging import duration_ms, get_logger, log_event
from backend.core.metrics import metrics
from backend.db.repositories import CreativeRepository, InferenceRepository
from backend.services.analysis_job_events import publish_analysis_job_event
from backend.services.analysis_goal_taxonomy import normalize_analysis_channel, normalize_goal_template
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

    async def _store_progress(
        self,
        *,
        job,
        stage: str,
        stage_label: str,
        diagnostics: dict[str, int | None] | None = None,
        is_partial: bool | None = None,
        replace_diagnostics: bool = False,
    ) -> dict[str, Any]:
        runtime_params = dict(job.runtime_params or {})
        current_progress = dict(runtime_params.get("analysis_progress") or {})
        current_diagnostics = {} if replace_diagnostics else dict(current_progress.get("diagnostics") or {})
        merged_diagnostics = {
            **current_diagnostics,
            **{key: value for key, value in (diagnostics or {}).items() if value is not None},
        }
        next_progress = {
            **current_progress,
            "stage": stage,
            "stage_label": stage_label,
            "diagnostics": merged_diagnostics,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if is_partial is not None:
            next_progress["is_partial"] = is_partial
        runtime_params["analysis_progress"] = next_progress
        job.runtime_params = runtime_params
        await self.session.flush()
        return next_progress

    async def _publish_progress_event(
        self,
        *,
        job_id: UUID,
        stage: str,
        stage_label: str,
        diagnostics: dict[str, Any],
        partial_result: dict[str, Any] | None = None,
        is_partial: bool = False,
    ) -> None:
        await publish_analysis_job_event(
            job_id=job_id,
            event_type="job_progress",
            payload={
                "status": "processing",
                "stage": stage,
                "stage_label": stage_label,
                "diagnostics": diagnostics,
                "partial_result": partial_result,
                "is_partial": is_partial,
            },
        )

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
            campaign_context = (job.request_payload or {}).get("campaign_context") or {}
            objective = campaign_context.get("objective")
            total_started_at = time.perf_counter()
            queue_wait_ms = (
                max(0, int((job.started_at - job.created_at).total_seconds() * 1000))
                if job.started_at is not None
                else None
            )
            log_event(
                logger,
                "prediction_job_started",
                job_id=str(job.id),
                creative_version_id=str(creative_version.id),
                modality=modality,
                queue_wait_ms=queue_wait_ms,
                status="running",
            )
            worker_started_progress = await self._store_progress(
                job=job,
                stage="worker_started",
                stage_label="Worker acquired the job and is loading creative inputs.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": 0,
                },
                is_partial=False,
                replace_diagnostics=True,
            )
            await self.session.commit()
            await self._publish_progress_event(
                job_id=job.id,
                stage="worker_started",
                stage_label="Worker acquired the job and is loading creative inputs.",
                diagnostics=worker_started_progress["diagnostics"],
                is_partial=False,
            )

            asset_resolved_progress = await self._store_progress(
                job=job,
                stage="asset_resolved",
                stage_label="Creative metadata is resolved. Preparing the inference payload now.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, time.perf_counter()),
                },
            )
            await self.session.commit()
            await self._publish_progress_event(
                job_id=job.id,
                stage="asset_resolved",
                stage_label="Creative metadata is resolved. Preparing the inference payload now.",
                diagnostics=asset_resolved_progress["diagnostics"],
                is_partial=False,
            )

            inference_started_progress = await self._store_progress(
                job=job,
                stage="inference_started",
                stage_label="Inference has started. The worker is extracting events from the uploaded asset.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, time.perf_counter()),
                },
            )
            await self.session.commit()
            await self._publish_progress_event(
                job_id=job.id,
                stage="inference_started",
                stage_label="Inference has started. The worker is extracting events from the uploaded asset.",
                diagnostics=inference_started_progress["diagnostics"],
                is_partial=False,
            )

            inference_started_at = time.perf_counter()
            execution = self.tribe_inference.run_for_version(
                creative_version=creative_version,
                request_payload=job.request_payload or {},
                runtime_params=job.runtime_params or {},
            )
            inference_finished_at = time.perf_counter()
            log_event(
                logger,
                "prediction_inference_finished",
                job_id=str(job.id),
                modality=execution.modality,
                duration_ms=duration_ms(inference_started_at, inference_finished_at),
                status="succeeded",
            )

            scene_payload = self.postprocessor.build_scene_extraction_payload(
                runtime_output=execution.runtime_output,
                modality=execution.modality,
                objective=str(objective).strip() if isinstance(objective, str) and objective.strip() else None,
                goal_template=normalize_goal_template(campaign_context.get("goal_template")),
                channel=normalize_analysis_channel(campaign_context.get("channel")),
                audience_segment=str(campaign_context.get("audience_segment") or "").strip() or None,
                source_label=execution.source_label,
            )
            scene_extraction_finished_at = time.perf_counter()
            first_result_time_ms = (queue_wait_ms or 0) + duration_ms(total_started_at, scene_extraction_finished_at)
            scene_extraction_snapshot = self.postprocessor.build_result_payload(
                job_id=job.id,
                dashboard_payload=scene_payload,
            )
            scene_extraction_ready_progress = await self._store_progress(
                job=job,
                stage="scene_extraction_ready",
                stage_label="Scene extraction is complete. Scene windows and frame scaffolding are ready while scoring continues.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, scene_extraction_finished_at),
                    "time_to_first_result_ms": first_result_time_ms,
                },
                is_partial=True,
            )
            await self.session.commit()
            await self._publish_progress_event(
                job_id=job.id,
                stage="scene_extraction_ready",
                stage_label="Scene extraction is complete. Scene windows and frame scaffolding are ready while scoring continues.",
                diagnostics=scene_extraction_ready_progress["diagnostics"],
                partial_result=scene_extraction_snapshot,
                is_partial=True,
            )

            primary_scoring_started_progress = await self._store_progress(
                job=job,
                stage="primary_scoring_started",
                stage_label="Primary scoring has started. Attention, memory, and load metrics are being computed.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, time.perf_counter()),
                    "time_to_first_result_ms": first_result_time_ms,
                },
                is_partial=True,
            )
            await self.session.commit()
            await self._publish_progress_event(
                job_id=job.id,
                stage="primary_scoring_started",
                stage_label="Primary scoring has started. Attention, memory, and load metrics are being computed.",
                diagnostics=primary_scoring_started_progress["diagnostics"],
                partial_result=scene_extraction_snapshot,
                is_partial=True,
            )

            scoring_started_at = time.perf_counter()
            scoring_bundle = await self.scoring.score(
                reduced_feature_vector=execution.runtime_output.reduced_feature_vector,
                region_activation_summary=execution.runtime_output.region_activation_summary,
                context=job.request_payload or {},
                modality=execution.modality,
            )
            scoring_finished_at = time.perf_counter()
            log_event(
                logger,
                "prediction_scoring_finished",
                job_id=str(job.id),
                modality=execution.modality,
                duration_ms=duration_ms(scoring_started_at, scoring_finished_at),
                status="succeeded",
            )

            preview_started_at = time.perf_counter()
            preview_payload = self.postprocessor.build_dashboard_payload(
                runtime_output=execution.runtime_output,
                scoring_bundle=scoring_bundle,
                modality=execution.modality,
                objective=str(objective).strip() if isinstance(objective, str) and objective.strip() else None,
                goal_template=normalize_goal_template(campaign_context.get("goal_template")),
                channel=normalize_analysis_channel(campaign_context.get("channel")),
                audience_segment=str(campaign_context.get("audience_segment") or "").strip() or None,
                source_label=execution.source_label,
                include_recommendations=False,
            )
            preview_finished_at = time.perf_counter()
            log_event(
                logger,
                "prediction_preview_ready",
                job_id=str(job.id),
                modality=execution.modality,
                time_to_first_result_ms=first_result_time_ms,
                time_to_first_scored_result_ms=(queue_wait_ms or 0) + duration_ms(total_started_at, preview_finished_at),
                duration_ms=duration_ms(preview_started_at, preview_finished_at),
                timeline_points=len(preview_payload.timeline_json),
                segment_rows=len(preview_payload.segments_json),
                status="succeeded",
            )
            preview_snapshot = self.postprocessor.build_result_payload(
                job_id=job.id,
                dashboard_payload=preview_payload,
            )
            primary_scoring_ready_progress = await self._store_progress(
                job=job,
                stage="primary_scoring_ready",
                stage_label="Primary scoring is complete. Provisional metrics and charts are ready while recommendations are still pending.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, preview_finished_at),
                    "time_to_first_result_ms": first_result_time_ms,
                },
                is_partial=True,
            )
            await self.session.commit()
            await self._publish_progress_event(
                job_id=job.id,
                stage="primary_scoring_ready",
                stage_label="Primary scoring is complete. Provisional metrics and charts are ready while recommendations are still pending.",
                diagnostics=primary_scoring_ready_progress["diagnostics"],
                partial_result=preview_snapshot,
                is_partial=True,
            )

            postprocessing_started_progress = await self._store_progress(
                job=job,
                stage="postprocessing_started",
                stage_label="Post-processing has started. The dashboard is composing intervals and recommendations from the scored signals.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, preview_finished_at),
                    "time_to_first_result_ms": first_result_time_ms,
                },
                is_partial=True,
            )
            await self.session.commit()
            await self._publish_progress_event(
                job_id=job.id,
                stage="postprocessing_started",
                stage_label="Post-processing has started. The dashboard is composing intervals and recommendations from the scored signals.",
                diagnostics=postprocessing_started_progress["diagnostics"],
                partial_result=preview_snapshot,
                is_partial=True,
            )

            postprocess_started_at = time.perf_counter()
            dashboard_payload = self.postprocessor.build_dashboard_payload(
                runtime_output=execution.runtime_output,
                scoring_bundle=scoring_bundle,
                modality=execution.modality,
                objective=str(objective).strip() if isinstance(objective, str) and objective.strip() else None,
                goal_template=normalize_goal_template(campaign_context.get("goal_template")),
                channel=normalize_analysis_channel(campaign_context.get("channel")),
                audience_segment=str(campaign_context.get("audience_segment") or "").strip() or None,
                source_label=execution.source_label,
            )
            postprocess_finished_at = time.perf_counter()
            recommendations_ready_progress = await self._store_progress(
                job=job,
                stage="recommendations_ready",
                stage_label="Recommendations are ready. Persisting the final dashboard payload now.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, postprocess_finished_at),
                    "time_to_first_result_ms": first_result_time_ms,
                    "postprocess_duration_ms": duration_ms(postprocess_started_at, postprocess_finished_at),
                },
                is_partial=True,
            )
            await self.session.commit()
            final_preview_snapshot = self.postprocessor.build_result_payload(
                job_id=job.id,
                dashboard_payload=dashboard_payload,
            )
            await self._publish_progress_event(
                job_id=job.id,
                stage="recommendations_ready",
                stage_label="Recommendations are ready. Persisting the final dashboard payload now.",
                diagnostics=recommendations_ready_progress["diagnostics"],
                partial_result=final_preview_snapshot,
                is_partial=True,
            )

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
                result_delivery_ms=(queue_wait_ms or 0) + duration_ms(total_started_at, total_finished_at),
                status="succeeded",
            )
            metrics.increment("prediction_jobs_total", labels={"status": "succeeded"})
            await self._store_progress(
                job=job,
                stage="completed",
                stage_label="Results are ready and delivery timings are finalized.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, total_finished_at),
                    "time_to_first_result_ms": first_result_time_ms,
                    "result_delivery_ms": (queue_wait_ms or 0) + duration_ms(total_started_at, total_finished_at),
                    "postprocess_duration_ms": duration_ms(postprocess_started_at, postprocess_finished_at),
                },
                is_partial=False,
            )
            await self.session.commit()
            await publish_analysis_job_event(
                job_id=job.id,
                event_type="job_completed",
                payload={
                    "status": "completed",
                    "stage": "completed",
                    "stage_label": "Results are ready and delivery timings are finalized.",
                    "diagnostics": {
                        "queue_wait_ms": queue_wait_ms,
                        "processing_duration_ms": duration_ms(total_started_at, total_finished_at),
                        "time_to_first_result_ms": first_result_time_ms,
                        "result_delivery_ms": (queue_wait_ms or 0) + duration_ms(total_started_at, total_finished_at),
                        "postprocess_duration_ms": duration_ms(postprocess_started_at, postprocess_finished_at),
                    },
                },
            )
