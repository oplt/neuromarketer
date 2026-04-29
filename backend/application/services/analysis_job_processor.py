from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import NotFoundAppError
from backend.core.log_context import bound_log_context
from backend.core.logging import duration_ms, get_logger, log_event
from backend.core.metrics import metrics
from backend.db.repositories import CreativeRepository, InferenceRepository
from backend.services.analysis_goal_taxonomy import (
    normalize_analysis_channel,
    normalize_goal_template,
)
from backend.services.analysis_job_events import publish_analysis_job_event
from backend.services.analysis_postprocessor import AnalysisPostprocessor
from backend.services.scoring import NeuroScoringService
from backend.services.tribe_inference_service import TribeInferenceService

logger = get_logger(__name__)
PERSISTED_PROGRESS_STAGES = frozenset(
    {
        "worker_started",
        "scene_extraction_ready",
        "primary_scoring_ready",
        "recommendations_ready",
        "completed",
        "failed",
    }
)


class AnalysisJobProcessor:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.creatives = CreativeRepository(session) if session is not None else None
        self.inference = InferenceRepository(session) if session is not None else None
        self.tribe_inference = TribeInferenceService()
        self.scoring = NeuroScoringService()
        self.postprocessor = AnalysisPostprocessor()

    def _require_session(self) -> AsyncSession:
        if self.session is None:
            raise RuntimeError("AnalysisJobProcessor requires an active database session.")
        return self.session

    async def _store_progress(
        self,
        *,
        job,
        stage: str,
        stage_label: str,
        diagnostics: dict[str, int | None] | None = None,
        partial_result: dict[str, Any] | None = None,
        is_partial: bool | None = None,
        replace_diagnostics: bool = False,
        persist: bool = False,
    ) -> dict[str, Any]:
        runtime_params = dict(job.runtime_params or {})
        current_progress = dict(runtime_params.get("analysis_progress") or {})
        current_diagnostics = (
            {} if replace_diagnostics else dict(current_progress.get("diagnostics") or {})
        )
        merged_diagnostics = {
            **current_diagnostics,
            **{key: value for key, value in (diagnostics or {}).items() if value is not None},
        }
        next_progress = {
            **current_progress,
            "stage": stage,
            "stage_label": stage_label,
            "diagnostics": merged_diagnostics,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if is_partial is not None:
            next_progress["is_partial"] = is_partial
        if persist and partial_result is not None:
            runtime_params["analysis_partial_result"] = partial_result
        elif persist and is_partial is False and stage in {"completed", "failed"}:
            runtime_params.pop("analysis_partial_result", None)
        runtime_params["analysis_progress"] = next_progress
        job.runtime_params = runtime_params
        if persist:
            await self._require_session().flush()
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

    async def _record_progress(
        self,
        *,
        job,
        stage: str,
        stage_label: str,
        diagnostics: dict[str, int | None] | None = None,
        partial_result: dict[str, Any] | None = None,
        is_partial: bool = False,
        replace_diagnostics: bool = False,
    ) -> dict[str, Any]:
        persist = stage in PERSISTED_PROGRESS_STAGES
        progress = await self._store_progress(
            job=job,
            stage=stage,
            stage_label=stage_label,
            diagnostics=diagnostics,
            partial_result=partial_result,
            is_partial=is_partial,
            replace_diagnostics=replace_diagnostics,
            persist=persist,
        )
        if persist:
            await self._require_session().commit()
        await self._publish_progress_event(
            job_id=job.id,
            stage=stage,
            stage_label=stage_label,
            diagnostics=progress["diagnostics"],
            partial_result=partial_result,
            is_partial=is_partial,
        )
        return progress

    def _current_progress_diagnostics(self, job) -> dict[str, int | None]:
        runtime_params = dict(job.runtime_params or {})
        progress = runtime_params.get("analysis_progress")
        progress_payload = progress if isinstance(progress, dict) else {}
        diagnostics = progress_payload.get("diagnostics")
        return diagnostics if isinstance(diagnostics, dict) else {}

    def _elapsed_since_job_started_ms(self, job) -> int | None:
        if job.started_at is None:
            return None
        return max(0, int((datetime.now(UTC) - job.started_at).total_seconds() * 1000))

    def _runtime_output_from_prediction(self, prediction) -> Any:
        return self.tribe_inference.runtime_output_from_prediction(prediction)

    async def process(self, job_id: UUID) -> None:
        session = self._require_session()
        self.creatives = self.creatives or CreativeRepository(session)
        self.inference = self.inference or InferenceRepository(session)
        acquisition_started_at = time.perf_counter()
        job = await self.inference.acquire_job(
            job_id,
            stale_after_seconds=settings.celery_job_stale_after_seconds,
        )
        metrics.observe(
            "prediction_job_acquire_seconds",
            time.perf_counter() - acquisition_started_at,
            labels={"status": "acquired" if job is not None else "skipped"},
        )
        if job is None:
            log_event(logger, "prediction_job_skipped", job_id=str(job_id), status="skipped")
            return
        await session.commit()

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
            await self._record_progress(
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

            await self._record_progress(
                job=job,
                stage="asset_resolved",
                stage_label="Creative metadata is resolved. Preparing the inference payload now.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, time.perf_counter()),
                },
                is_partial=False,
            )

            await self._record_progress(
                job=job,
                stage="inference_started",
                stage_label="Inference has started. The worker is extracting events from the uploaded asset.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, time.perf_counter()),
                },
                is_partial=False,
            )

            # End any open transaction before TRIBE runs for a long time; otherwise the
            # connection stays idle-in-transaction (dirty ORM state from non-persisted
            # progress rows) and Postgres may kill it (idle_in_transaction_session_timeout).
            await session.commit()

            inference_started_at = time.perf_counter()
            execution = await run_in_threadpool(
                self.tribe_inference.run_for_version,
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
            metrics.observe(
                "prediction_job_stage_seconds",
                inference_finished_at - inference_started_at,
                labels={"stage": "tribe_inference", "modality": execution.modality},
            )

            scene_payload = self.postprocessor.build_scene_extraction_payload(
                runtime_output=execution.runtime_output,
                modality=execution.modality,
                objective=str(objective).strip()
                if isinstance(objective, str) and objective.strip()
                else None,
                goal_template=normalize_goal_template(campaign_context.get("goal_template")),
                channel=normalize_analysis_channel(campaign_context.get("channel")),
                audience_segment=str(campaign_context.get("audience_segment") or "").strip()
                or None,
                source_label=execution.source_label,
            )
            scene_extraction_finished_at = time.perf_counter()
            first_result_time_ms = (queue_wait_ms or 0) + duration_ms(
                total_started_at, scene_extraction_finished_at
            )
            scene_extraction_snapshot = self.postprocessor.build_result_payload(
                job_id=job.id,
                dashboard_payload=scene_payload,
            )
            await self._record_progress(
                job=job,
                stage="scene_extraction_ready",
                stage_label="Scene extraction is complete. Scene windows and frame scaffolding are ready while scoring continues.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(
                        total_started_at, scene_extraction_finished_at
                    ),
                    "time_to_first_result_ms": first_result_time_ms,
                },
                partial_result=scene_extraction_snapshot,
                is_partial=True,
            )

            await self.inference.store_prediction_handoff(
                job=job,
                runtime_output=execution.runtime_output,
                model_name=self.tribe_inference.runtime.model_name,
            )
            await self.inference.mark_job_inference_completed(job)
            await self.inference.mark_job_scoring_queued(job)
            await self._record_progress(
                job=job,
                stage="scoring_queued",
                stage_label="TRIBE inference is complete. Primary scoring has been queued on scoring workers.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": duration_ms(total_started_at, time.perf_counter()),
                    "time_to_first_result_ms": first_result_time_ms,
                },
                partial_result=scene_extraction_snapshot,
                is_partial=True,
            )
            await self.session.commit()
            from backend.tasks import dispatch_prediction_scoring_job

            dispatch_mode = await dispatch_prediction_scoring_job(job.id)
            log_event(
                logger,
                "prediction_scoring_queued",
                job_id=str(job.id),
                modality=execution.modality,
                dispatch_mode=dispatch_mode,
                status="queued",
            )
            return

    async def process_scoring(self, job_id: UUID) -> None:
        session = self._require_session()
        self.creatives = self.creatives or CreativeRepository(session)
        self.inference = self.inference or InferenceRepository(session)
        acquisition_started_at = time.perf_counter()
        job = await self.inference.acquire_scoring_job(
            job_id,
            stale_after_seconds=settings.celery_job_stale_after_seconds,
        )
        metrics.observe(
            "prediction_job_acquire_seconds",
            time.perf_counter() - acquisition_started_at,
            labels={"status": "acquired" if job is not None else "skipped", "phase": "scoring"},
        )
        if job is None:
            log_event(
                logger, "prediction_scoring_job_skipped", job_id=str(job_id), status="skipped"
            )
            return
        await session.commit()

        with bound_log_context(
            job_id=str(job.id),
            project_id=str(job.project_id),
            creative_id=str(job.creative_id),
            creative_version_id=str(job.creative_version_id),
        ):
            creative_version = await self.creatives.get_creative_version(job.creative_version_id)
            if creative_version is None:
                raise NotFoundAppError("Creative version not found.")

            prediction = job.prediction
            if prediction is None:
                raise NotFoundAppError("Prediction handoff not found.")

            modality = self.tribe_inference.resolve_modality(creative_version)
            campaign_context = (job.request_payload or {}).get("campaign_context") or {}
            objective = campaign_context.get("objective")
            queue_wait_ms = self._current_progress_diagnostics(job).get("queue_wait_ms")
            first_result_time_ms = self._current_progress_diagnostics(job).get(
                "time_to_first_result_ms"
            )
            runtime_output = self._runtime_output_from_prediction(prediction)
            source_label = self.tribe_inference.resolve_source_label(
                creative_version=creative_version
            )

            await self._record_progress(
                job=job,
                stage="primary_scoring_started",
                stage_label="Primary scoring has started. Core analysis metrics are being evaluated from the TRIBE-derived context.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": self._elapsed_since_job_started_ms(job),
                    "time_to_first_result_ms": first_result_time_ms,
                },
                is_partial=True,
            )

            await session.commit()

            scoring_started_at = time.perf_counter()
            scoring_bundle = await self.scoring.score(
                reduced_feature_vector=runtime_output.reduced_feature_vector,
                region_activation_summary=runtime_output.region_activation_summary,
                context=job.request_payload or {},
                modality=modality,
            )
            scoring_finished_at = time.perf_counter()
            log_event(
                logger,
                "prediction_scoring_finished",
                job_id=str(job.id),
                modality=modality,
                duration_ms=duration_ms(scoring_started_at, scoring_finished_at),
                status="succeeded",
            )
            metrics.observe(
                "prediction_job_stage_seconds",
                scoring_finished_at - scoring_started_at,
                labels={"stage": "llm_scoring", "modality": modality},
            )

            # Commit before CPU-heavy dashboard build so we never hold an implicit txn
            # across LLM scoring + threadpool work (see DATABASE_IDLE_IN_TRANSACTION_*).
            await session.commit()

            preview_started_at = time.perf_counter()
            preview_payload = await run_in_threadpool(
                self.postprocessor.build_dashboard_payload,
                runtime_output=runtime_output,
                scoring_bundle=scoring_bundle,
                modality=modality,
                objective=str(objective).strip()
                if isinstance(objective, str) and objective.strip()
                else None,
                goal_template=normalize_goal_template(campaign_context.get("goal_template")),
                channel=normalize_analysis_channel(campaign_context.get("channel")),
                audience_segment=str(campaign_context.get("audience_segment") or "").strip()
                or None,
                source_label=source_label,
                include_recommendations=False,
            )
            preview_finished_at = time.perf_counter()
            log_event(
                logger,
                "prediction_preview_ready",
                job_id=str(job.id),
                modality=modality,
                time_to_first_result_ms=first_result_time_ms,
                time_to_first_scored_result_ms=(queue_wait_ms or 0)
                + (self._elapsed_since_job_started_ms(job) or 0),
                duration_ms=duration_ms(preview_started_at, preview_finished_at),
                timeline_points=len(preview_payload.timeline_json),
                segment_rows=len(preview_payload.segments_json),
                status="succeeded",
            )
            preview_snapshot = self.postprocessor.build_result_payload(
                job_id=job.id,
                dashboard_payload=preview_payload,
            )
            await self._record_progress(
                job=job,
                stage="primary_scoring_ready",
                stage_label="Primary scoring is complete. Provisional metrics and charts are ready while recommendations are still pending.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": self._elapsed_since_job_started_ms(job),
                    "time_to_first_result_ms": first_result_time_ms,
                },
                partial_result=preview_snapshot,
                is_partial=True,
            )

            await self._record_progress(
                job=job,
                stage="postprocessing_started",
                stage_label="Post-processing has started. The dashboard is composing the scored timeline and recommendations.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": self._elapsed_since_job_started_ms(job),
                    "time_to_first_result_ms": first_result_time_ms,
                },
                partial_result=preview_snapshot,
                is_partial=True,
            )

            await session.commit()

            postprocess_started_at = time.perf_counter()
            dashboard_payload = await run_in_threadpool(
                self.postprocessor.with_recommendations,
                preview_payload,
                scoring_bundle,
            )
            postprocess_finished_at = time.perf_counter()
            await self._record_progress(
                job=job,
                stage="recommendations_ready",
                stage_label="Recommendations are ready. Persisting the final dashboard payload now.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": self._elapsed_since_job_started_ms(job),
                    "time_to_first_result_ms": first_result_time_ms,
                    "postprocess_duration_ms": duration_ms(
                        postprocess_started_at, postprocess_finished_at
                    ),
                },
                partial_result=self.postprocessor.build_result_payload(
                    job_id=job.id,
                    dashboard_payload=dashboard_payload,
                ),
                is_partial=True,
            )

            persistence_started_at = time.perf_counter()
            log_event(
                logger,
                "prediction_persist_started",
                job_id=str(job.id),
                modality=modality,
                status="running",
            )
            prediction_result = await self.inference.replace_prediction_result(
                job=job,
                runtime_output=runtime_output,
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

            log_event(
                logger,
                "prediction_persist_finished",
                prediction_result_id=str(prediction_result.id),
                modality=modality,
                duration_ms=duration_ms(persistence_started_at, persistence_finished_at),
                status="succeeded",
            )
            metrics.observe(
                "prediction_job_stage_seconds",
                persistence_finished_at - persistence_started_at,
                labels={"stage": "persistence", "modality": modality},
            )
            total_processing_duration_ms = self._elapsed_since_job_started_ms(job) or 0
            log_event(
                logger,
                "prediction_job_succeeded",
                prediction_result_id=str(prediction_result.id),
                modality=modality,
                duration_ms=total_processing_duration_ms,
                postprocess_duration_ms=duration_ms(
                    postprocess_started_at, postprocess_finished_at
                ),
                result_delivery_ms=(queue_wait_ms or 0) + total_processing_duration_ms,
                status="succeeded",
            )
            metrics.increment("prediction_jobs_total", labels={"status": "succeeded"})
            await self._record_progress(
                job=job,
                stage="completed",
                stage_label="Results are ready and delivery timings are finalized.",
                diagnostics={
                    "queue_wait_ms": queue_wait_ms,
                    "processing_duration_ms": total_processing_duration_ms,
                    "time_to_first_result_ms": first_result_time_ms,
                    "result_delivery_ms": (queue_wait_ms or 0) + total_processing_duration_ms,
                    "postprocess_duration_ms": duration_ms(
                        postprocess_started_at, postprocess_finished_at
                    ),
                },
                is_partial=False,
            )
            await publish_analysis_job_event(
                job_id=job.id,
                event_type="job_completed",
                payload={
                    "status": "completed",
                    "stage": "completed",
                    "stage_label": "Results are ready and delivery timings are finalized.",
                    "diagnostics": {
                        "queue_wait_ms": queue_wait_ms,
                        "processing_duration_ms": total_processing_duration_ms,
                        "time_to_first_result_ms": first_result_time_ms,
                        "result_delivery_ms": (queue_wait_ms or 0)
                        + total_processing_duration_ms,
                        "postprocess_duration_ms": duration_ms(
                            postprocess_started_at, postprocess_finished_at
                        ),
                    },
                },
            )

    # Compatibility helpers for the lightweight worker module.
    async def acquire_job(self, db: AsyncSession, job_id: UUID):
        self.session = db
        self.creatives = CreativeRepository(db)
        self.inference = InferenceRepository(db)
        return await self.inference.acquire_job(
            job_id,
            stale_after_seconds=settings.celery_job_stale_after_seconds,
        )

    async def run_inference(self, job):
        creative_version = getattr(job, "creative_version", None)
        if creative_version is None:
            raise NotFoundAppError("Creative version not found for analysis job.")

        execution = await run_in_threadpool(
            self.tribe_inference.run_for_version,
            creative_version=creative_version,
            request_payload=job.request_payload or {},
            runtime_params=job.runtime_params or {},
        )
        return execution

    async def persist_inference(self, db: AsyncSession, job_id: UUID, execution):
        self.session = db
        self.inference = InferenceRepository(db)

        job = await self.inference.get_job(job_id)
        if job is None:
            raise NotFoundAppError("Inference job not found.")

        await self.inference.store_prediction_handoff(
            job=job,
            runtime_output=execution.runtime_output,
            model_name=self.tribe_inference.runtime.model_name,
        )
        await self.inference.mark_job_scoring_queued(job)
