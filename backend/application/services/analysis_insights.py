from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from statistics import median
from typing import Any
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.db.models import (
    AuditLog,
    CalibrationObservation,
    InferenceJob,
    JobStatus,
    OutcomeEvent,
    OutcomeMetricType,
    PredictionResult,
    PredictionScore,
    ScoreType,
    User,
)
from backend.schemas.analysis import (
    AnalysisBenchmarkMetricRead,
    AnalysisBenchmarkResponse,
    AnalysisCalibrationDashboardResponse,
    AnalysisCalibrationDashboardSummaryRead,
    AnalysisCalibrationMetricSummaryRead,
    AnalysisCalibrationObservationRead,
    AnalysisCalibrationResponse,
    AnalysisCalibrationSummaryRead,
    AnalysisCalibrationTrendPointRead,
    AnalysisExecutiveVerdictRead,
    AnalysisOutcomeImportHistoryRead,
    AnalysisOutcomeImportResponse,
)

BENCHMARK_METRICS = (
    ("overall_attention_score", "Overall Attention", "higher"),
    ("hook_score_first_3_seconds", "Hook Score", "higher"),
    ("sustained_engagement_score", "Sustained Engagement", "higher"),
    ("memory_proxy_score", "Memory Proxy", "higher"),
    ("cognitive_load_proxy", "Cognitive Load", "lower"),
    ("conversion_proxy_score", "Conversion Proxy", "higher"),
)

VERDICT_STATUS_THRESHOLD_SHIP = 67.0
VERDICT_STATUS_THRESHOLD_HIGH_RISK = 42.0
CALIBRATION_IMPORT_COLUMNS = {
    "analysis_job_id",
    "creative_version_id",
    "metric_type",
    "metric_value",
    "metric_unit",
    "observed_at",
    "source_system",
    "source_ref",
}
LOWER_IS_BETTER_METRICS = {
    OutcomeMetricType.CPC,
    OutcomeMetricType.CPA,
    OutcomeMetricType.BOUNCE_RATE,
}


class AnalysisInsightsApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_benchmark(self, *, user_id: UUID, job_id: UUID) -> AnalysisBenchmarkResponse:
        job = await self._load_analysis_job(user_id=user_id, job_id=job_id)
        cohort_jobs, cohort_label, fallback_level = await self._build_benchmark_cohort(job)
        analysis_record = job.analysis_result_record
        if analysis_record is None:
            raise ConflictAppError("Analysis results are not ready yet.")

        metrics = []
        for key, label, orientation in BENCHMARK_METRICS:
            current_value = self._extract_metric_value(analysis_record, key)
            cohort_values = [
                self._extract_metric_value(candidate.analysis_result_record, key)
                for candidate in cohort_jobs
                if candidate.analysis_result_record is not None
            ]
            metrics.append(
                AnalysisBenchmarkMetricRead(
                    key=key,
                    label=label,
                    value=round(current_value, 2),
                    percentile=round(self._compute_percentile(current_value, cohort_values, orientation=orientation), 1),
                    cohort_median=round(self._compute_quantile(cohort_values, percentile=50), 2),
                    cohort_p75=round(self._compute_quantile(cohort_values, percentile=75), 2),
                    orientation=orientation,
                    detail=f"{label} benchmarked against {cohort_label.lower()}.",
                )
            )

        return AnalysisBenchmarkResponse(
            job_id=job.id,
            cohort_label=cohort_label,
            cohort_size=len(cohort_jobs),
            fallback_level=fallback_level,
            metrics=metrics,
            generated_at=datetime.now(timezone.utc),
        )

    async def get_executive_verdict(self, *, user_id: UUID, job_id: UUID) -> AnalysisExecutiveVerdictRead:
        benchmark = await self.get_benchmark(user_id=user_id, job_id=job_id)
        job = await self._load_analysis_job(user_id=user_id, job_id=job_id)
        analysis_record = job.analysis_result_record
        if analysis_record is None:
            raise ConflictAppError("Analysis results are not ready yet.")

        metric_percentiles = {metric.key: metric.percentile for metric in benchmark.metrics}
        weighted_average = round(
            (
                metric_percentiles.get("hook_score_first_3_seconds", 0.0) * 0.24
                + metric_percentiles.get("overall_attention_score", 0.0) * 0.22
                + metric_percentiles.get("sustained_engagement_score", 0.0) * 0.18
                + metric_percentiles.get("memory_proxy_score", 0.0) * 0.16
                + metric_percentiles.get("conversion_proxy_score", 0.0) * 0.12
                + metric_percentiles.get("cognitive_load_proxy", 0.0) * 0.08
            ),
            1,
        )

        if weighted_average >= VERDICT_STATUS_THRESHOLD_SHIP:
            status = "ship"
            headline = "Ship with confidence"
        elif weighted_average <= VERDICT_STATUS_THRESHOLD_HIGH_RISK:
            status = "high_risk"
            headline = "High revision risk"
        else:
            status = "iterate"
            headline = "Promising, but iterate before launch"

        sorted_metrics = sorted(benchmark.metrics, key=lambda item: item.percentile, reverse=True)
        top_strengths = [
            f"{metric.label} ranks in the {self._ordinal_percentile(metric.percentile)} percentile for this cohort."
            for metric in sorted_metrics[:3]
        ]
        top_risks = [
            f"{metric.label} is lagging at the {self._ordinal_percentile(metric.percentile)} percentile."
            for metric in sorted_metrics[-3:]
        ]

        recommendations = analysis_record.recommendations_json or []
        recommended_actions = [
            str(item.get("title") or "").strip()
            for item in recommendations
            if str(item.get("title") or "").strip()
        ][:3]
        if not recommended_actions:
            recommended_actions = [
                "Tighten the opening to improve early attention retention.",
                "Reduce cognitive load in the densest scenes or messaging blocks.",
                "Clarify the CTA to improve the conversion proxy.",
            ]

        summary = (
            f"{headline}. Average benchmark percentile is {weighted_average:.1f} across "
            f"{benchmark.cohort_size} comparable completed analyses."
        )
        return AnalysisExecutiveVerdictRead(
            job_id=job.id,
            status=status,
            headline=headline,
            summary=summary,
            benchmark_average_percentile=weighted_average,
            top_strengths=top_strengths,
            top_risks=top_risks,
            recommended_actions=recommended_actions,
            generated_at=datetime.now(timezone.utc),
        )

    async def import_outcomes_csv(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        file: UploadFile,
    ) -> AnalysisOutcomeImportResponse:
        raw_bytes = await file.read()
        if not raw_bytes:
            raise ValidationAppError("The uploaded CSV file is empty.")

        try:
            decoded = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationAppError("Outcome import expects a UTF-8 CSV file.") from exc

        reader = csv.DictReader(io.StringIO(decoded))
        if not reader.fieldnames:
            raise ValidationAppError("Outcome import CSV is missing a header row.")
        missing_columns = {"metric_type", "metric_value", "observed_at"} - set(reader.fieldnames)
        if missing_columns:
            raise ValidationAppError(
                f"Outcome import CSV is missing required columns: {', '.join(sorted(missing_columns))}."
            )

        imported_events = 0
        imported_observations = 0
        errors: list[str] = []

        for row_index, row in enumerate(reader, start=2):
            try:
                prediction, owner_job = await self._resolve_prediction_target(
                    user_id=user_id,
                    project_id=project_id,
                    analysis_job_id=row.get("analysis_job_id"),
                    creative_version_id=row.get("creative_version_id"),
                )
                metric_type = OutcomeMetricType(str(row.get("metric_type") or "").strip())
                metric_value = Decimal(str(row.get("metric_value") or "").strip())
                observed_at = self._parse_datetime(row.get("observed_at"))
                outcome_event = OutcomeEvent(
                    project_id=owner_job.project_id,
                    creative_id=owner_job.creative_id,
                    creative_version_id=owner_job.creative_version_id,
                    campaign_id=None,
                    metric_type=metric_type,
                    metric_value=metric_value,
                    metric_unit=str(row.get("metric_unit") or "").strip() or None,
                    observed_at=observed_at,
                    source_system=str(row.get("source_system") or "").strip() or "csv_import",
                    source_ref=str(row.get("source_ref") or "").strip() or None,
                    dimensions_json={
                        key: value
                        for key, value in row.items()
                        if key not in CALIBRATION_IMPORT_COLUMNS and value not in (None, "")
                    },
                )
                self.session.add(outcome_event)
                await self.session.flush()
                imported_events += 1

                if prediction is not None:
                    for score in prediction.scores:
                        self.session.add(
                            CalibrationObservation(
                                prediction_result_id=prediction.id,
                                outcome_event_id=outcome_event.id,
                                score_type=score.score_type,
                                predicted_value=score.normalized_score,
                                metric_type=metric_type,
                                actual_value=metric_value,
                                metadata_json={
                                    "analysis_job_id": str(owner_job.id),
                                    "source_system": outcome_event.source_system,
                                },
                            )
                        )
                        imported_observations += 1
            except Exception as exc:
                errors.append(f"Row {row_index}: {exc}")

        await self.session.commit()
        return AnalysisOutcomeImportResponse(
            imported_events=imported_events,
            imported_observations=imported_observations,
            failed_rows=len(errors),
            errors=errors[:20],
        )

    async def get_calibration(self, *, user_id: UUID, job_id: UUID) -> AnalysisCalibrationResponse:
        job = await self._load_analysis_job(user_id=user_id, job_id=job_id)
        prediction = job.prediction
        if prediction is None:
            return AnalysisCalibrationResponse(
                job_id=job.id,
                summary=AnalysisCalibrationSummaryRead(
                    observation_count=0,
                    metric_types=[],
                    latest_observed_at=None,
                    average_predicted_value=None,
                    average_actual_value=None,
                ),
                observations=[],
            )

        result = await self.session.execute(
            select(CalibrationObservation, OutcomeEvent)
            .join(OutcomeEvent, OutcomeEvent.id == CalibrationObservation.outcome_event_id)
            .where(CalibrationObservation.prediction_result_id == prediction.id)
            .order_by(desc(OutcomeEvent.observed_at))
            .limit(100)
        )
        rows = result.all()
        observations = [
            AnalysisCalibrationObservationRead(
                id=observation.id,
                metric_type=observation.metric_type.value,
                score_type=observation.score_type.value,
                predicted_value=float(observation.predicted_value),
                actual_value=float(observation.actual_value),
                observed_at=outcome_event.observed_at,
                source_system=outcome_event.source_system,
                source_ref=outcome_event.source_ref,
            )
            for observation, outcome_event in rows
        ]
        average_predicted = round(sum(item.predicted_value for item in observations) / len(observations), 2) if observations else None
        average_actual = round(sum(item.actual_value for item in observations) / len(observations), 2) if observations else None
        latest_observed_at = observations[0].observed_at if observations else None
        metric_types = sorted({item.metric_type for item in observations})

        return AnalysisCalibrationResponse(
            job_id=job.id,
            summary=AnalysisCalibrationSummaryRead(
                observation_count=len(observations),
                metric_types=metric_types,
                latest_observed_at=latest_observed_at,
                average_predicted_value=average_predicted,
                average_actual_value=average_actual,
            ),
            observations=observations,
        )

    async def _load_analysis_job(self, *, user_id: UUID, job_id: UUID) -> InferenceJob:
        result = await self.session.execute(
            select(InferenceJob)
            .options(
                selectinload(InferenceJob.analysis_result_record),
                selectinload(InferenceJob.prediction).selectinload(PredictionResult.scores),
            )
            .where(InferenceJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None or job.created_by_user_id != user_id:
            raise NotFoundAppError("Analysis job not found.")
        return job

    async def _build_benchmark_cohort(
        self,
        job: InferenceJob,
    ) -> tuple[list[InferenceJob], str, str]:
        result = await self.session.execute(
            select(InferenceJob)
            .options(selectinload(InferenceJob.analysis_result_record))
            .where(
                InferenceJob.project_id == job.project_id,
                InferenceJob.status == JobStatus.SUCCEEDED,
            )
            .order_by(desc(InferenceJob.created_at))
            .limit(250)
        )
        candidates = [
            candidate
            for candidate in result.scalars().all()
            if candidate.analysis_result_record is not None
            and (candidate.runtime_params or {}).get("analysis_surface") == "analysis_dashboard"
        ]

        media_type = str((job.runtime_params or {}).get("media_type") or "")
        campaign_context = (job.request_payload or {}).get("campaign_context") or {}
        goal_template = str(campaign_context.get("goal_template") or "")
        channel = str(campaign_context.get("channel") or "")

        cohort_options = [
            (
                [
                    candidate
                    for candidate in candidates
                    if str((candidate.runtime_params or {}).get("media_type") or "") == media_type
                    and str(((candidate.request_payload or {}).get("campaign_context") or {}).get("goal_template") or "") == goal_template
                    and str(((candidate.request_payload or {}).get("campaign_context") or {}).get("channel") or "") == channel
                ],
                f"{media_type or 'analysis'} cohort for {goal_template or 'general'} / {channel or 'default'}",
                "exact_match",
            ),
            (
                [
                    candidate
                    for candidate in candidates
                    if str((candidate.runtime_params or {}).get("media_type") or "") == media_type
                    and str(((candidate.request_payload or {}).get("campaign_context") or {}).get("goal_template") or "") == goal_template
                ],
                f"{media_type or 'analysis'} cohort for {goal_template or 'general'}",
                "goal_template",
            ),
            (
                [
                    candidate
                    for candidate in candidates
                    if str((candidate.runtime_params or {}).get("media_type") or "") == media_type
                ],
                f"{media_type or 'analysis'} cohort",
                "media_type",
            ),
            (candidates, "Project-wide analysis cohort", "project"),
        ]

        for cohort, label, fallback_level in cohort_options:
            if len(cohort) >= 5:
                return cohort, label, fallback_level
        return candidates or [job], "Project-wide analysis cohort", "project"

    async def _resolve_prediction_target(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        analysis_job_id: str | None,
        creative_version_id: str | None,
    ) -> tuple[PredictionResult | None, InferenceJob]:
        if analysis_job_id:
            job = await self._load_analysis_job(user_id=user_id, job_id=UUID(str(analysis_job_id)))
            return job.prediction, job

        if creative_version_id:
            creative_version_uuid = UUID(str(creative_version_id))
            result = await self.session.execute(
                select(InferenceJob)
                .options(
                    selectinload(InferenceJob.prediction).selectinload(PredictionResult.scores),
                )
                .where(
                    InferenceJob.project_id == project_id,
                    InferenceJob.creative_version_id == creative_version_uuid,
                    InferenceJob.created_by_user_id == user_id,
                )
                .order_by(desc(InferenceJob.created_at))
                .limit(1)
            )
            job = result.scalar_one_or_none()
            if job is None:
                raise ValidationAppError("Unable to resolve the provided creative_version_id.")
            return job.prediction, job

        raise ValidationAppError("Each CSV row must include analysis_job_id or creative_version_id.")

    def _extract_metric_value(self, analysis_record, key: str) -> float:
        summary_json = analysis_record.summary_json or {}
        if key in summary_json:
            return float(summary_json.get(key) or 0.0)
        for item in analysis_record.metrics_json or []:
            if str(item.get("key") or "") == key:
                return float(item.get("value") or 0.0)
        return 0.0

    def _compute_percentile(self, current_value: float, cohort_values: list[float], *, orientation: str) -> float:
        comparable_values = sorted(float(value) for value in cohort_values)
        if not comparable_values:
            return 50.0
        if orientation == "lower":
            passing_values = sum(1 for value in comparable_values if value >= current_value)
        else:
            passing_values = sum(1 for value in comparable_values if value <= current_value)
        return (passing_values / len(comparable_values)) * 100.0

    def _compute_quantile(self, values: list[float], *, percentile: int) -> float:
        comparable_values = sorted(float(value) for value in values)
        if not comparable_values:
            return 0.0
        if percentile == 50:
            return float(median(comparable_values))
        if len(comparable_values) == 1:
            return comparable_values[0]
        position = (len(comparable_values) - 1) * (percentile / 100)
        lower_index = int(position)
        upper_index = min(lower_index + 1, len(comparable_values) - 1)
        weight = position - lower_index
        return comparable_values[lower_index] + (comparable_values[upper_index] - comparable_values[lower_index]) * weight

    def _ordinal_percentile(self, value: float) -> str:
        rounded = max(1, min(99, int(round(value))))
        if 10 <= rounded % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(rounded % 10, "th")
        return f"{rounded}{suffix}"

    def _parse_datetime(self, value: str | None) -> datetime:
        if not value:
            raise ValidationAppError("observed_at is required.")
        normalized = value.strip()
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationAppError(f"Invalid observed_at timestamp: {value}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
