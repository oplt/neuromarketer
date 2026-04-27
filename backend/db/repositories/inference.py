from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, desc, select
from sqlalchemy import func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import (
    AnalysisResultRecord,
    InferenceJob,
    JobMetric,
    JobStatus,
    OptimizationSuggestion,
    PredictionResult,
    PredictionScore,
    PredictionTimelinePoint,
    PredictionVisualization,
    ScoreType,
)
from backend.services.scoring import ScoringBundle
from backend.services.tribe_runtime import TribeRuntimeOutput


@dataclass(slots=True)
class PredictionSnapshot:
    creative_version_id: UUID
    prediction_result_id: UUID
    scores_by_type: dict[str, Decimal]
    created_at: datetime


class InferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(
        self,
        *,
        project_id: UUID,
        creative_id: UUID,
        creative_version_id: UUID,
        created_by_user_id: UUID | None,
        request_payload: dict,
        runtime_params: dict,
    ) -> InferenceJob:
        analysis_surface = runtime_params.get("analysis_surface") if runtime_params else None
        media_type = runtime_params.get("media_type") if runtime_params else None
        phase_payload = (runtime_params or {}).get("analysis_execution_phase")
        execution_phase = None
        execution_phase_updated_at = None
        if isinstance(phase_payload, dict):
            execution_phase = phase_payload.get("phase")
            updated_at_raw = phase_payload.get("updated_at")
            if isinstance(updated_at_raw, str):
                try:
                    parsed = datetime.fromisoformat(updated_at_raw)
                    execution_phase_updated_at = (
                        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
                    )
                except ValueError:
                    execution_phase_updated_at = None

        job = InferenceJob(
            project_id=project_id,
            creative_id=creative_id,
            creative_version_id=creative_version_id,
            created_by_user_id=created_by_user_id,
            request_payload=request_payload,
            runtime_params=runtime_params,
            status=JobStatus.QUEUED,
            analysis_surface=analysis_surface if isinstance(analysis_surface, str) else None,
            media_type=media_type if isinstance(media_type, str) else None,
            execution_phase=execution_phase if isinstance(execution_phase, str) else None,
            execution_phase_updated_at=execution_phase_updated_at,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_job_with_prediction(self, job_id: UUID) -> InferenceJob | None:
        result = await self.session.execute(
            select(InferenceJob)
            .options(
                selectinload(InferenceJob.metrics),
                selectinload(InferenceJob.analysis_result_record),
                selectinload(InferenceJob.llm_evaluations),
                selectinload(InferenceJob.prediction).selectinload(PredictionResult.scores),
                selectinload(InferenceJob.prediction).selectinload(PredictionResult.visualizations),
                selectinload(InferenceJob.prediction).selectinload(
                    PredictionResult.timeline_points
                ),
                selectinload(InferenceJob.prediction).selectinload(PredictionResult.suggestions),
            )
            .where(InferenceJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_job(self, job_id: UUID) -> InferenceJob | None:
        result = await self.session.execute(select(InferenceJob).where(InferenceJob.id == job_id))
        return result.scalar_one_or_none()

    async def list_analysis_jobs_for_user(
        self,
        *,
        project_id: UUID,
        created_by_user_id: UUID,
        media_type: str | None,
        goal_template: str | None = None,
        channel: str | None = None,
        audience_contains: str | None = None,
        limit: int,
    ) -> list[InferenceJob]:
        query = (
            select(InferenceJob)
            .options(selectinload(InferenceJob.analysis_result_record))
            .where(
                InferenceJob.project_id == project_id,
                InferenceJob.created_by_user_id == created_by_user_id,
                InferenceJob.analysis_surface == "analysis_dashboard",
            )
            .order_by(desc(InferenceJob.created_at))
            .limit(limit)
        )
        if media_type is not None:
            query = query.where(InferenceJob.media_type == media_type)
        if goal_template is not None:
            query = query.where(
                InferenceJob.request_payload["campaign_context"]["goal_template"].astext
                == goal_template
            )
        if channel is not None:
            query = query.where(
                InferenceJob.request_payload["campaign_context"]["channel"].astext == channel
            )
        if audience_contains is not None:
            audience_query = audience_contains.strip().lower()
            if audience_query:
                query = query.where(
                    sqlfunc.lower(
                        InferenceJob.request_payload["campaign_context"]["audience_segment"].astext
                    ).contains(audience_query)
                )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_analysis_jobs_by_ids(
        self,
        *,
        job_ids: list[UUID],
    ) -> list[InferenceJob]:
        if not job_ids:
            return []
        result = await self.session.execute(
            select(InferenceJob)
            .options(selectinload(InferenceJob.analysis_result_record))
            .where(InferenceJob.id.in_(job_ids))
        )
        jobs_by_id = {job.id: job for job in result.scalars().all()}
        return [jobs_by_id[job_id] for job_id in job_ids if job_id in jobs_by_id]

    async def list_benchmark_cohort(
        self,
        *,
        project_id: UUID,
        media_type: str | None,
        goal_template: str | None,
        channel: str | None,
        limit: int = 250,
    ) -> list[InferenceJob]:
        filter_combinations = [
            (media_type, goal_template, channel),
            (media_type, goal_template, None),
            (media_type, None, None),
            (None, None, None),
        ]
        for combination in filter_combinations:
            rows = await self.query_analysis_benchmark_candidates(
                project_id=project_id,
                media_type=combination[0],
                goal_template=combination[1],
                channel=combination[2],
                limit=limit,
            )
            if len(rows) >= 5:
                return rows
        return rows if "rows" in locals() else []

    async def query_analysis_benchmark_candidates(
        self,
        *,
        project_id: UUID,
        media_type: str | None = None,
        goal_template: str | None = None,
        channel: str | None = None,
        limit: int = 250,
    ) -> list[InferenceJob]:
        query = (
            select(InferenceJob)
            .options(selectinload(InferenceJob.analysis_result_record))
            .where(
                InferenceJob.project_id == project_id,
                InferenceJob.status == JobStatus.SUCCEEDED,
                InferenceJob.analysis_surface == "analysis_dashboard",
            )
            .order_by(desc(InferenceJob.created_at))
            .limit(limit)
        )
        if media_type is not None:
            query = query.where(InferenceJob.media_type == media_type)
        if goal_template is not None:
            query = query.where(
                InferenceJob.request_payload["campaign_context"]["goal_template"].astext
                == goal_template
            )
        if channel is not None:
            query = query.where(
                InferenceJob.request_payload["campaign_context"]["channel"].astext == channel
            )
        result = await self.session.execute(query)
        return [item for item in result.scalars().all() if item.analysis_result_record is not None]

    async def get_job_for_analysis_evaluation(self, job_id: UUID) -> InferenceJob | None:
        result = await self.session.execute(
            select(InferenceJob)
            .options(
                selectinload(InferenceJob.analysis_result_record),
                selectinload(InferenceJob.creative_version),
                selectinload(InferenceJob.llm_evaluations),
            )
            .where(InferenceJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_prediction_result_full(
        self, prediction_result_id: UUID
    ) -> PredictionResult | None:
        result = await self.session.execute(
            select(PredictionResult)
            .options(
                selectinload(PredictionResult.scores),
                selectinload(PredictionResult.visualizations),
                selectinload(PredictionResult.timeline_points),
                selectinload(PredictionResult.suggestions),
            )
            .where(PredictionResult.id == prediction_result_id)
        )
        return result.scalar_one_or_none()

    async def acquire_job(self, job_id: UUID, *, stale_after_seconds: int) -> InferenceJob | None:
        result = await self.session.execute(
            select(InferenceJob)
            .options(
                selectinload(InferenceJob.prediction),
                selectinload(InferenceJob.analysis_result_record),
            )
            .where(InferenceJob.id == job_id)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None

        if job.status == JobStatus.CANCELED:
            return None

        if job.status == JobStatus.SUCCEEDED and job.prediction is not None:
            return None

        now = datetime.now(UTC)
        is_stale_running_job = (
            job.status == JobStatus.RUNNING
            and job.started_at is not None
            and job.started_at < now - timedelta(seconds=stale_after_seconds)
        )
        if job.status == JobStatus.RUNNING and not is_stale_running_job:
            return None

        job.status = JobStatus.RUNNING
        job.started_at = now
        job.completed_at = None
        job.error_message = None
        runtime_params = dict(job.runtime_params or {})
        runtime_params["analysis_execution_phase"] = {
            "phase": "inference_running",
            "updated_at": now.isoformat(),
        }
        job.runtime_params = runtime_params
        job.execution_phase = "inference_running"
        job.execution_phase_updated_at = now
        await self.session.flush()
        return job

    async def acquire_scoring_job(
        self, job_id: UUID, *, stale_after_seconds: int
    ) -> InferenceJob | None:
        result = await self.session.execute(
            select(InferenceJob)
            .options(
                selectinload(InferenceJob.prediction),
                selectinload(InferenceJob.analysis_result_record),
            )
            .where(InferenceJob.id == job_id)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job is None or job.status in {JobStatus.CANCELED, JobStatus.SUCCEEDED, JobStatus.FAILED}:
            return None

        if job.prediction is None or job.analysis_result_record is not None:
            return None

        phase_name = str(job.execution_phase or "").strip().lower()
        phase_updated_at = job.execution_phase_updated_at

        now = datetime.now(UTC)
        is_stale_running_phase = (
            phase_name == "scoring_running"
            and phase_updated_at is not None
            and phase_updated_at < now - timedelta(seconds=stale_after_seconds)
        )
        if phase_name not in {"scoring_queued", "scoring_running"}:
            return None
        if phase_name == "scoring_running" and not is_stale_running_phase:
            return None

        runtime_params = dict(job.runtime_params or {})
        runtime_params["analysis_execution_phase"] = {
            "phase": "scoring_running",
            "updated_at": now.isoformat(),
        }
        job.runtime_params = runtime_params
        job.execution_phase = "scoring_running"
        job.execution_phase_updated_at = now
        await self.session.flush()
        return job

    async def mark_job_scoring_queued(self, job: InferenceJob) -> None:
        now = datetime.now(UTC)
        runtime_params = dict(job.runtime_params or {})
        runtime_params["analysis_execution_phase"] = {
            "phase": "scoring_queued",
            "updated_at": now.isoformat(),
        }
        job.runtime_params = runtime_params
        job.execution_phase = "scoring_queued"
        job.execution_phase_updated_at = now
        await self.session.flush()

    async def mark_job_failed(
        self,
        job: InferenceJob,
        error_message: str,
        *,
        partial_result_available: bool = False,
    ) -> None:
        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)
        runtime_params = dict(job.runtime_params or {})
        current_progress = dict(runtime_params.get("analysis_progress") or {})
        current_diagnostics = dict(current_progress.get("diagnostics") or {})
        stage_label = (
            current_progress.get("stage_label")
            or "The analysis stopped before results were produced."
        )
        if partial_result_available:
            stage_label = (
                "TRIBE scene extraction completed, but LLM scoring failed. "
                "Showing the saved TRIBE-only result."
            )
        runtime_params["analysis_progress"] = {
            "stage": "failed",
            "stage_label": stage_label,
            "diagnostics": current_diagnostics,
            "is_partial": partial_result_available,
        }
        failed_at = datetime.now(UTC)
        runtime_params["analysis_execution_phase"] = {
            "phase": "failed",
            "updated_at": failed_at.isoformat(),
        }
        job.runtime_params = runtime_params
        job.execution_phase = "failed"
        job.execution_phase_updated_at = failed_at
        await self.session.flush()

    async def mark_job_succeeded(self, job: InferenceJob) -> None:
        job.status = JobStatus.SUCCEEDED
        job.error_message = None
        job.completed_at = datetime.now(UTC)
        runtime_params = dict(job.runtime_params or {})
        runtime_params["analysis_execution_phase"] = {
            "phase": "completed",
            "updated_at": job.completed_at.isoformat(),
        }
        job.runtime_params = runtime_params
        job.execution_phase = "completed"
        job.execution_phase_updated_at = job.completed_at
        await self.session.flush()

    async def reset_job_for_rerun(self, job: InferenceJob) -> None:
        """Reset a FAILED or CANCELED job back to QUEUED so it can be re-dispatched."""
        job.status = JobStatus.QUEUED
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        runtime_params = dict(job.runtime_params or {})
        runtime_params["analysis_progress"] = {
            "stage": "queued",
            "stage_label": (
                "Upload finalized. The analysis job is queued and waiting for worker "
                "capacity."
            ),
            "diagnostics": {},
            "is_partial": False,
        }
        reset_at = datetime.now(UTC)
        runtime_params["analysis_execution_phase"] = {
            "phase": "queued",
            "updated_at": reset_at.isoformat(),
        }
        job.runtime_params = runtime_params
        job.execution_phase = "queued"
        job.execution_phase_updated_at = reset_at
        await self.session.flush()

    async def store_prediction_handoff(
        self,
        *,
        job: InferenceJob,
        runtime_output: TribeRuntimeOutput,
        model_name: str,
    ) -> PredictionResult:
        existing_prediction = await self.get_prediction_result_for_job(job.id)
        if existing_prediction is None:
            prediction = PredictionResult(
                job_id=job.id,
                project_id=job.project_id,
                creative_id=job.creative_id,
                creative_version_id=job.creative_version_id,
                raw_brain_response_uri=runtime_output.raw_brain_response_uri,
                raw_brain_response_summary=runtime_output.raw_brain_response_summary,
                reduced_feature_vector=runtime_output.reduced_feature_vector,
                region_activation_summary=runtime_output.region_activation_summary,
                provenance_json=runtime_output.provenance_json,
            )
            self.session.add(prediction)
            await self.session.flush()
        else:
            prediction = existing_prediction
            prediction.raw_brain_response_uri = runtime_output.raw_brain_response_uri
            prediction.raw_brain_response_summary = runtime_output.raw_brain_response_summary
            prediction.reduced_feature_vector = runtime_output.reduced_feature_vector
            prediction.region_activation_summary = runtime_output.region_activation_summary
            prediction.provenance_json = runtime_output.provenance_json
            await self.session.flush()

        self.session.add(
            JobMetric(
                job_id=job.id,
                metric_name="foundation_model_forward_passes",
                metric_value=Decimal("1"),
                metric_unit="count",
                metadata_json={"model": model_name, "phase": "inference_handoff"},
            )
        )
        await self.session.flush()
        await self.session.refresh(prediction)
        return prediction

    async def replace_prediction_result(
        self,
        *,
        job: InferenceJob,
        runtime_output: TribeRuntimeOutput,
        scoring_bundle: ScoringBundle,
        model_name: str,
    ) -> PredictionResult:
        existing_prediction = await self.get_prediction_result_for_job(job.id)
        if existing_prediction is not None:
            await self.session.delete(existing_prediction)
            await self.session.flush()

        await self.session.execute(delete(JobMetric).where(JobMetric.job_id == job.id))

        prediction = PredictionResult(
            job_id=job.id,
            project_id=job.project_id,
            creative_id=job.creative_id,
            creative_version_id=job.creative_version_id,
            raw_brain_response_uri=runtime_output.raw_brain_response_uri,
            raw_brain_response_summary=runtime_output.raw_brain_response_summary,
            reduced_feature_vector=runtime_output.reduced_feature_vector,
            region_activation_summary=runtime_output.region_activation_summary,
            provenance_json=runtime_output.provenance_json,
        )
        self.session.add(prediction)
        await self.session.flush()

        self.session.add_all(
            [
                PredictionScore(
                    prediction_result_id=prediction.id,
                    score_type=ScoreType(score.score_type),
                    normalized_score=score.normalized_score,
                    raw_value=score.raw_value,
                    confidence=score.confidence,
                    percentile=score.percentile,
                    metadata_json=score.metadata_json,
                )
                for score in scoring_bundle.scores
            ]
        )

        self.session.add_all(
            [
                PredictionVisualization(
                    prediction_result_id=prediction.id,
                    visualization_type=visualization.visualization_type,
                    title=visualization.title,
                    storage_uri=visualization.storage_uri,
                    data_json=visualization.data_json,
                )
                for visualization in scoring_bundle.visualizations
            ]
        )

        self.session.add_all(
            [
                PredictionTimelinePoint(
                    prediction_result_id=prediction.id,
                    timestamp_ms=point.timestamp_ms,
                    attention_score=point.attention_score,
                    emotion_score=point.emotion_score,
                    memory_score=point.memory_score,
                    cognitive_load_score=point.cognitive_load_score,
                    conversion_proxy_score=point.conversion_proxy_score,
                    metadata_json=point.metadata_json,
                )
                for point in scoring_bundle.timeline_points
            ]
        )

        self.session.add_all(
            [
                OptimizationSuggestion(
                    prediction_result_id=prediction.id,
                    suggestion_type=suggestion.suggestion_type,
                    status=suggestion.status,
                    title=suggestion.title,
                    rationale=suggestion.rationale,
                    proposed_change_json=suggestion.proposed_change_json,
                    expected_score_lift_json=suggestion.expected_score_lift_json,
                    confidence=suggestion.confidence,
                )
                for suggestion in scoring_bundle.suggestions
            ]
        )

        self.session.add(
            JobMetric(
                job_id=job.id,
                metric_name="foundation_model_forward_passes",
                metric_value=Decimal("1"),
                metric_unit="count",
                metadata_json={"model": model_name},
            )
        )
        await self.session.flush()
        await self.session.refresh(prediction)
        return prediction

    async def get_prediction_result_for_job(self, job_id: UUID) -> PredictionResult | None:
        result = await self.session.execute(
            select(PredictionResult).where(PredictionResult.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def replace_analysis_result(
        self,
        *,
        job: InferenceJob,
        summary_json: dict,
        metrics_json: list[dict],
        timeline_json: list[dict],
        segments_json: list[dict],
        visualizations_json: dict,
        recommendations_json: list[dict],
    ) -> AnalysisResultRecord:
        existing = await self.get_analysis_result_for_job(job.id)
        if existing is not None:
            await self.session.delete(existing)
            await self.session.flush()

        record = AnalysisResultRecord(
            job_id=job.id,
            summary_json=summary_json,
            metrics_json=metrics_json,
            timeline_json=timeline_json,
            segments_json=segments_json,
            visualizations_json=visualizations_json,
            recommendations_json=recommendations_json,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def get_analysis_result_for_job(self, job_id: UUID) -> AnalysisResultRecord | None:
        result = await self.session.execute(
            select(AnalysisResultRecord).where(AnalysisResultRecord.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_prediction_snapshots(
        self,
        creative_version_ids: list[UUID],
    ) -> dict[UUID, PredictionSnapshot]:
        if not creative_version_ids:
            return {}

        latest_predictions = (
            select(
                PredictionResult.id.label("prediction_id"),
                PredictionResult.creative_version_id.label("creative_version_id"),
                sqlfunc.row_number()
                .over(
                    partition_by=PredictionResult.creative_version_id,
                    order_by=(desc(PredictionResult.created_at), desc(PredictionResult.id)),
                )
                .label("row_num"),
            )
            .where(PredictionResult.creative_version_id.in_(creative_version_ids))
            .cte(name="latest_predictions")
        )
        result = await self.session.execute(
            select(PredictionResult)
            .options(selectinload(PredictionResult.scores))
            .join(
                latest_predictions,
                latest_predictions.c.prediction_id == PredictionResult.id,
            )
            .where(latest_predictions.c.row_num == 1)
        )
        predictions = result.scalars().all()

        return {
            prediction.creative_version_id: PredictionSnapshot(
                creative_version_id=prediction.creative_version_id,
                prediction_result_id=prediction.id,
                created_at=prediction.created_at,
                scores_by_type={
                    score.score_type.value: score.normalized_score for score in prediction.scores
                },
            )
            for prediction in predictions
        }
