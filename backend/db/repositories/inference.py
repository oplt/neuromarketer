from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import and_, case, delete, desc, select, true
from sqlalchemy import func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.application.services.analysis_pipeline_state import (
    can_acquire_inference,
    can_acquire_scoring,
    transition_to_completed,
    transition_to_failed,
    transition_to_inference_completed,
    transition_to_inference_running,
    transition_to_queued,
    transition_to_scoring_queued,
    transition_to_scoring_running,
)
from backend.core.config import settings
from backend.core.logging import get_logger, log_exception
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
from backend.services.storage import ObjectStorageService
from backend.services.tribe_runtime import TribeRuntimeOutput

logger = get_logger(__name__)


def _coerce_short_text(value: object, max_length: int) -> str | None:
    """Normalize a payload-derived string for indexed columns.

    Returns ``None`` for anything that is not a non-empty trimmed
    string. Truncates to ``max_length`` so the value always fits the
    column type and never raises a SQL-level length error in the hot
    write path.
    """

    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed[:max_length]


def _benchmark_tier_condition(
    *,
    media_type: str | None,
    goal_template: str | None,
    channel: str | None,
):
    clauses = []
    if media_type is not None:
        clauses.append(InferenceJob.media_type == media_type)
    if goal_template is not None:
        clauses.append(InferenceJob.goal_template == goal_template)
    if channel is not None:
        clauses.append(InferenceJob.channel == channel)
    if not clauses:
        return true()
    return and_(*clauses)


@dataclass(slots=True)
class PredictionSnapshot:
    creative_version_id: UUID
    prediction_result_id: UUID
    scores_by_type: dict[str, Decimal]
    created_at: datetime


class InferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._storage_service: ObjectStorageService | None = None

    def _storage(self) -> ObjectStorageService:
        if self._storage_service is None:
            self._storage_service = ObjectStorageService()
        return self._storage_service

    def _maybe_summarize_payload(self, payload: Any, *, max_preview_items: int = 20) -> Any:
        if isinstance(payload, dict):
            keys = list(payload.keys())
            return {
                "_payload_summary": True,
                "key_count": len(keys),
                "keys_preview": keys[:max_preview_items],
            }
        if isinstance(payload, list):
            return {
                "_payload_summary": True,
                "item_count": len(payload),
                "preview": payload[:max_preview_items],
            }
        return payload

    def _payload_size_bytes(self, payload: Any) -> int:
        try:
            encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except Exception:
            return 0
        return len(encoded)

    async def _offload_large_json_payload(
        self,
        *,
        job_id: UUID,
        payload_name: str,
        payload: dict | list,
    ) -> tuple[dict | list, str | None]:
        if not settings.analysis_offload_large_payloads:
            return payload, None
        payload_size = self._payload_size_bytes(payload)
        if payload_size < max(1, int(settings.analysis_offload_payload_threshold_bytes)):
            return payload, None
        storage_key = f"analysis/jobs/{job_id}/{payload_name}.json"
        try:
            uploaded = await run_in_threadpool(
                self._storage().put_json_object,
                bucket_name=self._storage().bucket_name,
                storage_key=storage_key,
                payload=payload,
            )
        except Exception as exc:
            log_exception(
                logger,
                "analysis_payload_offload_failed",
                exc,
                job_id=str(job_id),
                payload_name=payload_name,
                payload_size_bytes=payload_size,
                level="warning",
                status="failed",
            )
            return payload, None

        summary = self._maybe_summarize_payload(payload)
        if isinstance(summary, dict):
            summary = {
                **summary,
                "_payload_offloaded": True,
                "_payload_uri": uploaded.storage_uri,
                "_payload_size_bytes": payload_size,
            }
        return summary, uploaded.storage_uri

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
        if not isinstance(execution_phase, str) or not execution_phase.strip():
            execution_phase = "queued"
        if execution_phase_updated_at is None:
            execution_phase_updated_at = datetime.now(UTC)

        # Denormalise the hot filter keys onto first-class columns so
        # dashboard and benchmark queries hit btree indexes instead of
        # JSONB paths. The JSONB blob remains the source of truth.
        campaign_context = (request_payload or {}).get("campaign_context") or {}
        goal_template = _coerce_short_text(campaign_context.get("goal_template"), 64)
        channel = _coerce_short_text(campaign_context.get("channel"), 64)
        audience_segment = _coerce_short_text(campaign_context.get("audience_segment"), 255)

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
            goal_template=goal_template,
            channel=channel,
            audience_segment=audience_segment,
            execution_phase=execution_phase if isinstance(execution_phase, str) else None,
            execution_phase_updated_at=execution_phase_updated_at,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_job_result_full(self, job_id: UUID) -> InferenceJob | None:
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

    async def get_job_with_prediction(self, job_id: UUID) -> InferenceJob | None:
        return await self.get_job_result_full(job_id)

    async def get_job_status_light(self, job_id: UUID) -> InferenceJob | None:
        result = await self.session.execute(
            select(InferenceJob)
            .options(selectinload(InferenceJob.analysis_result_record))
            .where(InferenceJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_analysis_job_light_for_user(
        self,
        *,
        job_id: UUID,
        user_id: UUID,
    ) -> InferenceJob | None:
        result = await self.session.execute(
            select(InferenceJob)
            .options(selectinload(InferenceJob.analysis_result_record))
            .where(
                InferenceJob.id == job_id,
                InferenceJob.created_by_user_id == user_id,
                InferenceJob.analysis_surface == "analysis_dashboard",
            )
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
        # All optional filters target denormalized indexed columns
        # (see ``backend/db/models.py`` and the corresponding Alembic
        # migration). Dashboards stay snappy even at high job volume.
        if media_type is not None:
            query = query.where(InferenceJob.media_type == media_type)
        if goal_template is not None:
            query = query.where(InferenceJob.goal_template == goal_template)
        if channel is not None:
            query = query.where(InferenceJob.channel == channel)
        if audience_contains is not None:
            audience_query = audience_contains.strip().lower()
            if audience_query:
                query = query.where(
                    sqlfunc.lower(InferenceJob.audience_segment).contains(audience_query)
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

    async def delete_analysis_jobs_by_ids(
        self,
        *,
        job_ids: list[UUID],
        project_id: UUID,
        created_by_user_id: UUID,
    ) -> int:
        if not job_ids:
            return 0
        result = await self.session.execute(
            select(InferenceJob.id).where(
                InferenceJob.id.in_(job_ids),
                InferenceJob.project_id == project_id,
                InferenceJob.created_by_user_id == created_by_user_id,
                InferenceJob.analysis_surface == "analysis_dashboard",
            )
        )
        deletable_ids = [row[0] for row in result.all()]
        if not deletable_ids:
            return 0
        await self.session.execute(
            delete(InferenceJob).where(InferenceJob.id.in_(deletable_ids))
        )
        await self.session.flush()
        return len(deletable_ids)

    async def list_benchmark_cohort(
        self,
        *,
        project_id: UUID,
        media_type: str | None,
        goal_template: str | None,
        channel: str | None,
        limit: int = 250,
    ) -> list[InferenceJob]:
        # Single weighted query: rank by closest cohort match, then recency.
        # This replaces the previous 4-step fallback sequence, cutting
        # roundtrips under load while preserving preference order.
        return await self.query_analysis_benchmark_candidates(
            project_id=project_id,
            media_type=media_type,
            goal_template=goal_template,
            channel=channel,
            limit=limit,
        )

    async def query_analysis_benchmark_candidates(
        self,
        *,
        project_id: UUID,
        media_type: str | None = None,
        goal_template: str | None = None,
        channel: str | None = None,
        limit: int = 250,
    ) -> list[InferenceJob]:
        filter_combinations = [
            (media_type, goal_template, channel),
            (media_type, goal_template, None),
            (media_type, None, None),
            (None, None, None),
        ]
        unique_filter_combinations: list[tuple[str | None, str | None, str | None]] = []
        seen_filter_combinations: set[tuple[str | None, str | None, str | None]] = set()
        for combo in filter_combinations:
            if combo in seen_filter_combinations:
                continue
            seen_filter_combinations.add(combo)
            unique_filter_combinations.append(combo)

        ranked_tiers = [
            (
                _benchmark_tier_condition(
                    media_type=combo_media_type,
                    goal_template=combo_goal_template,
                    channel=combo_channel,
                ),
                tier_rank,
            )
            for tier_rank, (
                combo_media_type,
                combo_goal_template,
                combo_channel,
            ) in enumerate(unique_filter_combinations)
        ]
        tier_rank_expr = case(*ranked_tiers, else_=len(unique_filter_combinations))

        query = (
            select(InferenceJob, tier_rank_expr.label("tier_rank"))
            .options(selectinload(InferenceJob.analysis_result_record))
            .where(
                InferenceJob.project_id == project_id,
                InferenceJob.status == JobStatus.SUCCEEDED,
                InferenceJob.analysis_surface == "analysis_dashboard",
                InferenceJob.analysis_result_record.has(),
            )
            .order_by(tier_rank_expr, desc(InferenceJob.created_at))
            .limit(limit)
        )
        result = await self.session.execute(query)
        return [item for item, _ in result.all()]

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
                selectinload(InferenceJob.creative_version),
            )
            .where(InferenceJob.id == job_id)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None

        if not can_acquire_inference(job, stale_after_seconds=stale_after_seconds):
            return None

        transition_to_inference_running(job)
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
        if job is None:
            return None

        if not can_acquire_scoring(job, stale_after_seconds=stale_after_seconds):
            return None

        transition_to_scoring_running(job)
        await self.session.flush()
        return job

    async def mark_job_scoring_queued(self, job: InferenceJob) -> None:
        transition_to_scoring_queued(job)
        await self.session.flush()

    async def mark_job_inference_completed(self, job: InferenceJob) -> None:
        transition_to_inference_completed(job)
        await self.session.flush()

    async def mark_job_failed(
        self,
        job: InferenceJob,
        error_message: str,
        *,
        partial_result_available: bool = False,
    ) -> None:
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
        job.runtime_params = runtime_params
        transition_to_failed(job, error_message=error_message)
        await self.session.flush()

    async def mark_job_succeeded(self, job: InferenceJob) -> None:
        transition_to_completed(job)
        await self.session.flush()

    async def reset_job_for_rerun(self, job: InferenceJob) -> None:
        """Reset a FAILED or CANCELED job back to QUEUED so it can be re-dispatched."""
        transition_to_queued(job)
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
        job.runtime_params = runtime_params
        await self.session.flush()

    async def store_prediction_handoff(
        self,
        *,
        job: InferenceJob,
        runtime_output: TribeRuntimeOutput,
        model_name: str,
    ) -> PredictionResult:
        """Persist the TRIBE handoff for a job idempotently.

        Re-running this method (e.g. after a Celery retry of
        ``process_prediction_job``) MUST NOT change the
        ``PredictionResult.id`` and MUST NOT create duplicate
        ``JobMetric`` rows. Everything happens inside the caller's
        transaction so a partial run rolls back cleanly.
        """

        existing_prediction = await self.get_prediction_result_for_job(job.id)
        if existing_prediction is None:
            # TODO(infra): offload large runtime JSON blobs to object storage when
            # prediction payloads grow beyond DB-healthy thresholds.
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

        await self._upsert_job_metric(
            job_id=job.id,
            metric_name="foundation_model_forward_passes",
            metric_value=Decimal("1"),
            metric_unit="count",
            metadata_json={"model": model_name, "phase": "inference_handoff"},
            phase="inference_handoff",
        )
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
        """Idempotently persist the scored prediction for ``job``.

        Safe to call multiple times for the same job (Celery retry,
        worker-lost requeue, manual rerun): the parent
        ``PredictionResult`` row is updated in place so its primary key
        and ``created_at`` stay stable; child collections (scores,
        visualizations, timeline points, suggestions) are atomically
        replaced inside the caller's transaction; the
        ``foundation_model_forward_passes`` metric is upserted by name
        instead of accumulating duplicates.
        """

        prediction = await self._upsert_prediction_parent(
            job=job, runtime_output=runtime_output
        )
        await self._replace_prediction_children(
            prediction_id=prediction.id, scoring_bundle=scoring_bundle
        )
        await self._upsert_job_metric(
            job_id=job.id,
            metric_name="foundation_model_forward_passes",
            metric_value=Decimal("1"),
            metric_unit="count",
            metadata_json={"model": model_name, "phase": "scoring"},
            phase="scoring",
        )
        await self.session.refresh(prediction)
        return prediction

    async def _upsert_prediction_parent(
        self,
        *,
        job: InferenceJob,
        runtime_output: TribeRuntimeOutput,
    ) -> PredictionResult:
        """Insert-or-update the ``PredictionResult`` row keyed by ``job_id``.

        Preserves the existing row's ``id`` and ``created_at`` so any
        downstream artifact that already references this prediction
        keeps working after a retry.
        """

        runtime_payload = {
            "raw_brain_response_summary": runtime_output.raw_brain_response_summary,
            "reduced_feature_vector": runtime_output.reduced_feature_vector,
            "region_activation_summary": runtime_output.region_activation_summary,
            "provenance_json": runtime_output.provenance_json,
        }
        summarized_runtime_payload, offloaded_runtime_uri = await self._offload_large_json_payload(
            job_id=job.id,
            payload_name="runtime-output",
            payload=runtime_payload,
        )
        if offloaded_runtime_uri is not None:
            raw_summary = summarized_runtime_payload.get("raw_brain_response_summary", {})
            reduced_vector = summarized_runtime_payload.get("reduced_feature_vector", {})
            region_summary = summarized_runtime_payload.get("region_activation_summary", {})
            provenance = summarized_runtime_payload.get("provenance_json", {})
        else:
            raw_summary = runtime_output.raw_brain_response_summary
            reduced_vector = runtime_output.reduced_feature_vector
            region_summary = runtime_output.region_activation_summary
            provenance = runtime_output.provenance_json

        existing = await self.get_prediction_result_for_job(job.id)
        if existing is not None:
            existing.project_id = job.project_id
            existing.creative_id = job.creative_id
            existing.creative_version_id = job.creative_version_id
            existing.raw_brain_response_uri = (
                runtime_output.raw_brain_response_uri or offloaded_runtime_uri
            )
            existing.raw_brain_response_summary = raw_summary
            existing.reduced_feature_vector = reduced_vector
            existing.region_activation_summary = region_summary
            existing.provenance_json = provenance
            await self.session.flush()
            return existing

        prediction = PredictionResult(
            job_id=job.id,
            project_id=job.project_id,
            creative_id=job.creative_id,
            creative_version_id=job.creative_version_id,
            raw_brain_response_uri=runtime_output.raw_brain_response_uri or offloaded_runtime_uri,
            raw_brain_response_summary=raw_summary,
            reduced_feature_vector=reduced_vector,
            region_activation_summary=region_summary,
            provenance_json=provenance,
        )
        self.session.add(prediction)
        await self.session.flush()
        return prediction

    async def _replace_prediction_children(
        self,
        *,
        prediction_id: UUID,
        scoring_bundle: ScoringBundle,
    ) -> None:
        """Atomically replace the child collections for a prediction.

        Scoped strictly to ``prediction_id`` so other rows (e.g. another
        version of the same job) cannot be touched. The delete + insert
        pair runs inside the caller's transaction; if anything raises
        the whole pair rolls back, leaving the previous children
        intact.
        """

        await self.session.execute(
            delete(PredictionScore).where(
                PredictionScore.prediction_result_id == prediction_id
            )
        )
        await self.session.execute(
            delete(PredictionVisualization).where(
                PredictionVisualization.prediction_result_id == prediction_id
            )
        )
        await self.session.execute(
            delete(PredictionTimelinePoint).where(
                PredictionTimelinePoint.prediction_result_id == prediction_id
            )
        )
        await self.session.execute(
            delete(OptimizationSuggestion).where(
                OptimizationSuggestion.prediction_result_id == prediction_id
            )
        )
        await self.session.flush()

        if scoring_bundle.scores:
            self.session.add_all(
                [
                    PredictionScore(
                        prediction_result_id=prediction_id,
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

        if scoring_bundle.visualizations:
            visualization_rows: list[PredictionVisualization] = []
            for idx, visualization in enumerate(scoring_bundle.visualizations):
                summarized_data, offloaded_uri = await self._offload_large_json_payload(
                    job_id=prediction_id,
                    payload_name=f"visualization-{idx}-{visualization.visualization_type.value}",
                    payload=visualization.data_json,
                )
                visualization_rows.append(
                    PredictionVisualization(
                        prediction_result_id=prediction_id,
                        visualization_type=visualization.visualization_type,
                        title=visualization.title,
                        storage_uri=offloaded_uri or visualization.storage_uri,
                        data_json=summarized_data if isinstance(summarized_data, dict) else {},
                    )
                )
            self.session.add_all(visualization_rows)

        if scoring_bundle.timeline_points:
            self.session.add_all(
                [
                    PredictionTimelinePoint(
                        prediction_result_id=prediction_id,
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

        if scoring_bundle.suggestions:
            self.session.add_all(
                [
                    OptimizationSuggestion(
                        prediction_result_id=prediction_id,
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

        await self.session.flush()

    async def _upsert_job_metric(
        self,
        *,
        job_id: UUID,
        metric_name: str,
        metric_value: Decimal,
        metric_unit: str | None,
        metadata_json: dict,
        phase: str,
    ) -> None:
        """Replace any prior ``JobMetric`` row for ``(job_id, metric_name, phase)``.

        ``job_metrics`` has no unique constraint on the natural key, so
        we emulate ``ON CONFLICT DO UPDATE`` by deleting any prior row
        for the same ``(job_id, metric_name, phase)`` triple and
        inserting the new value. Because both statements run in the
        caller's transaction, retries cannot create duplicate metric
        rows.
        """

        await self.session.execute(
            delete(JobMetric).where(
                JobMetric.job_id == job_id,
                JobMetric.metric_name == metric_name,
                JobMetric.metadata_json["phase"].astext == phase,
            )
        )
        self.session.add(
            JobMetric(
                job_id=job_id,
                metric_name=metric_name,
                metric_value=metric_value,
                metric_unit=metric_unit,
                metadata_json=metadata_json,
            )
        )
        await self.session.flush()

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
        """Idempotently persist the analysis dashboard payload for ``job``.

        The previous implementation deleted and re-inserted the row, so
        every Celery retry produced a brand-new ``AnalysisResultRecord.id``
        and ``created_at`` even when the inputs had not changed. We now
        update in place when a row already exists, keeping primary keys
        stable so cached references and event payloads stay consistent.
        """

        analysis_payload = {
            "timeline_json": timeline_json,
            "segments_json": segments_json,
            "visualizations_json": visualizations_json,
            "recommendations_json": recommendations_json,
        }
        (
            summarized_analysis_payload,
            offloaded_analysis_uri,
        ) = await self._offload_large_json_payload(
            job_id=job.id,
            payload_name="analysis-result-heavy",
            payload=analysis_payload,
        )
        summary_json_for_db = dict(summary_json or {})
        visualizations_json_for_db = dict(visualizations_json or {})
        timeline_json_for_db = list(timeline_json or [])
        segments_json_for_db = list(segments_json or [])
        recommendations_json_for_db = list(recommendations_json or [])
        if offloaded_analysis_uri is not None:
            summary_metadata = dict(summary_json_for_db.get("metadata") or {})
            summary_metadata["analysis_payload_uri"] = offloaded_analysis_uri
            summary_metadata["analysis_payload_offloaded"] = True
            summary_json_for_db["metadata"] = summary_metadata
            timeline_json_for_db = timeline_json_for_db[
                : max(0, int(settings.analysis_offload_timeline_preview_rows))
            ]
            segments_json_for_db = segments_json_for_db[
                : max(0, int(settings.analysis_offload_segments_preview_rows))
            ]
            recommendations_json_for_db = recommendations_json_for_db[
                : max(0, int(settings.analysis_offload_recommendations_preview_rows))
            ]
            visualizations_json_for_db = {
                **visualizations_json_for_db,
                "_payload_offloaded": True,
                "_payload_uri": offloaded_analysis_uri,
                "_payload_summary": summarized_analysis_payload
                if isinstance(summarized_analysis_payload, dict)
                else {},
            }

        existing = await self.get_analysis_result_for_job(job.id)
        if existing is not None:
            existing.summary_json = summary_json_for_db
            existing.metrics_json = metrics_json
            existing.timeline_json = timeline_json_for_db
            existing.segments_json = segments_json_for_db
            existing.visualizations_json = visualizations_json_for_db
            existing.recommendations_json = recommendations_json_for_db
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        record = AnalysisResultRecord(
            job_id=job.id,
            summary_json=summary_json_for_db,
            metrics_json=metrics_json,
            timeline_json=timeline_json_for_db,
            segments_json=segments_json_for_db,
            visualizations_json=visualizations_json_for_db,
            recommendations_json=recommendations_json_for_db,
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
