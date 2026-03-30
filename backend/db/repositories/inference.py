from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import (
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
        job = InferenceJob(
            project_id=project_id,
            creative_id=creative_id,
            creative_version_id=creative_version_id,
            created_by_user_id=created_by_user_id,
            request_payload=request_payload,
            runtime_params=runtime_params,
            status=JobStatus.QUEUED,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_job_with_prediction(self, job_id: UUID) -> InferenceJob | None:
        result = await self.session.execute(
            select(InferenceJob)
            .options(
                selectinload(InferenceJob.prediction).selectinload(PredictionResult.scores),
                selectinload(InferenceJob.prediction).selectinload(PredictionResult.visualizations),
                selectinload(InferenceJob.prediction).selectinload(PredictionResult.timeline_points),
                selectinload(InferenceJob.prediction).selectinload(PredictionResult.suggestions),
            )
            .where(InferenceJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_job(self, job_id: UUID) -> InferenceJob | None:
        result = await self.session.execute(select(InferenceJob).where(InferenceJob.id == job_id))
        return result.scalar_one_or_none()

    async def get_prediction_result_full(self, prediction_result_id: UUID) -> PredictionResult | None:
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
            .options(selectinload(InferenceJob.prediction))
            .where(InferenceJob.id == job_id)
            .with_for_update()
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None

        if job.status == JobStatus.CANCELED:
            return None

        if job.status == JobStatus.SUCCEEDED and job.prediction is not None:
            return None

        now = datetime.now(timezone.utc)
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
        await self.session.flush()
        return job

    async def mark_job_failed(self, job: InferenceJob, error_message: str) -> None:
        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def mark_job_succeeded(self, job: InferenceJob) -> None:
        job.status = JobStatus.SUCCEEDED
        job.error_message = None
        job.completed_at = datetime.now(timezone.utc)
        await self.session.flush()

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

        for score in scoring_bundle.scores:
            self.session.add(
                PredictionScore(
                    prediction_result_id=prediction.id,
                    score_type=ScoreType(score.score_type),
                    normalized_score=score.normalized_score,
                    raw_value=score.raw_value,
                    confidence=score.confidence,
                    percentile=score.percentile,
                    metadata_json=score.metadata_json,
                )
            )

        for visualization in scoring_bundle.visualizations:
            self.session.add(
                PredictionVisualization(
                    prediction_result_id=prediction.id,
                    visualization_type=visualization.visualization_type,
                    title=visualization.title,
                    storage_uri=visualization.storage_uri,
                    data_json=visualization.data_json,
                )
            )

        for point in scoring_bundle.timeline_points:
            self.session.add(
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
            )

        for suggestion in scoring_bundle.suggestions:
            self.session.add(
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
        result = await self.session.execute(select(PredictionResult).where(PredictionResult.job_id == job_id))
        return result.scalar_one_or_none()

    async def get_latest_prediction_snapshots(
        self,
        creative_version_ids: list[UUID],
    ) -> dict[UUID, PredictionSnapshot]:
        snapshots: dict[UUID, PredictionSnapshot] = {}

        for creative_version_id in creative_version_ids:
            result = await self.session.execute(
                select(PredictionResult)
                .options(selectinload(PredictionResult.scores))
                .where(PredictionResult.creative_version_id == creative_version_id)
                .order_by(desc(PredictionResult.created_at))
                .limit(1)
            )
            prediction = result.scalar_one_or_none()
            if prediction is None:
                continue

            snapshots[creative_version_id] = PredictionSnapshot(
                creative_version_id=creative_version_id,
                prediction_result_id=prediction.id,
                created_at=prediction.created_at,
                scores_by_type={score.score_type.value: score.normalized_score for score in prediction.scores},
            )

        return snapshots
