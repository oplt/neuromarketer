from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.analysis import AnalysisApplicationService
from backend.application.services.predictions import PredictionApplicationService
from backend.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.core.log_context import bound_log_context
from backend.core.logging import get_logger, log_event
from backend.db.repositories import ComparisonRepository
from backend.schemas.analysis import (
    AnalysisAssetRead,
    AnalysisComparisonCreateRequest,
    AnalysisComparisonItemRead,
    AnalysisComparisonListItemRead,
    AnalysisComparisonListResponse,
    AnalysisComparisonRead,
    AnalysisJobRead,
    AnalysisResultRead,
    AnalysisSummaryPayload,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class LoadedAnalysisComparisonCandidate:
    analysis_job_id: UUID
    creative_id: UUID
    creative_version_id: UUID
    job: AnalysisJobRead
    asset: AnalysisAssetRead | None
    result: AnalysisResultRead


@dataclass(slots=True)
class RankedAnalysisComparisonCandidate:
    candidate: LoadedAnalysisComparisonCandidate
    overall_rank: int
    scores_json: dict[str, Any]
    rationale: str


class AnalysisComparisonApplicationService:
    SCORE_WEIGHTS: ClassVar[dict[str, float]] = {
        "conversion_proxy": 0.30,
        "overall_attention": 0.22,
        "hook": 0.18,
        "sustained_engagement": 0.14,
        "memory_proxy": 0.12,
        "low_cognitive_load": 0.04,
    }
    # LLM scoring clamps missing/bad fields to 50 (see AnalysisScoringService._clamp_score).
    _NEUTRAL_SCORE_LOW: ClassVar[float] = 49.0
    _NEUTRAL_SCORE_HIGH: ClassVar[float] = 51.0

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.analysis = AnalysisApplicationService(session)
        self.predictions = PredictionApplicationService(session)
        self.comparisons = ComparisonRepository(session)

    async def create_comparison(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        payload: AnalysisComparisonCreateRequest,
    ) -> AnalysisComparisonRead:
        self._validate_create_payload(payload)
        with bound_log_context(project_id=str(project_id), user_id=str(user_id)):
            log_event(
                logger,
                "analysis_comparison_requested",
                project_id=str(project_id),
                user_id=str(user_id),
                candidate_count=len(payload.analysis_job_ids),
                status="started",
            )
            loaded_candidates = await self._load_candidates(
                user_id=user_id,
                project_id=project_id,
                analysis_job_ids=payload.analysis_job_ids,
            )
            ranked_candidates = self._rank_candidates(loaded_candidates)
            baseline_job_id = payload.baseline_job_id or loaded_candidates[0].analysis_job_id
            comparison_name = payload.name or self._build_default_name(loaded_candidates)

            comparison_context = self._build_stored_comparison_context(
                user_id=user_id,
                payload=payload,
                baseline_job_id=baseline_job_id,
                ranked_candidates=ranked_candidates,
            )
            creative_items_by_version: dict[UUID, tuple[UUID, UUID]] = {}
            for candidate in loaded_candidates:
                creative_items_by_version.setdefault(
                    candidate.creative_version_id,
                    (candidate.creative_id, candidate.creative_version_id),
                )

            result_items_by_version: dict[UUID, dict[str, Any]] = {}
            for ranked_candidate in ranked_candidates:
                result_items_by_version.setdefault(
                    ranked_candidate.candidate.creative_version_id,
                    {
                        "creative_version_id": ranked_candidate.candidate.creative_version_id,
                        "overall_rank": ranked_candidate.overall_rank,
                        "scores_json": ranked_candidate.scores_json,
                        "rationale": ranked_candidate.rationale,
                    },
                )

            comparison = await self.comparisons.create_comparison(
                project_id=project_id,
                name=comparison_name,
                creative_items=list(creative_items_by_version.values()),
                comparison_context=comparison_context,
            )

            winner = ranked_candidates[0].candidate if ranked_candidates else None
            await self.comparisons.replace_result(
                comparison_id=comparison.id,
                winning_creative_version_id=winner.creative_version_id
                if winner is not None
                else None,
                summary_json=self._build_summary_json(
                    ranked_candidates=ranked_candidates,
                    baseline_job_id=baseline_job_id,
                ),
                items=list(result_items_by_version.values()),
            )
            await self.session.commit()

            persisted = await self.comparisons.get_comparison(comparison.id, project_id=project_id)
            if persisted is None or persisted.result is None:
                raise NotFoundAppError("Comparison result not found.")

            response = self._build_comparison_read(persisted)
            log_event(
                logger,
                "analysis_comparison_completed",
                comparison_id=str(comparison.id),
                project_id=str(project_id),
                user_id=str(user_id),
                winning_analysis_job_id=str(response.winning_analysis_job_id)
                if response.winning_analysis_job_id
                else None,
                candidate_count=len(response.items),
                status="succeeded",
            )
            return response

    async def list_comparisons(
        self,
        *,
        project_id: UUID,
        limit: int,
    ) -> AnalysisComparisonListResponse:
        comparisons = await self.comparisons.list_comparisons_for_project(
            project_id=project_id, limit=limit
        )
        items = [
            self._build_list_item(comparison)
            for comparison in comparisons
            if self._is_analysis_workspace_comparison(comparison.comparison_context)
        ]
        return AnalysisComparisonListResponse(items=items)

    async def get_comparison(
        self,
        *,
        project_id: UUID,
        comparison_id: UUID,
    ) -> AnalysisComparisonRead:
        comparison = await self.comparisons.get_comparison(comparison_id, project_id=project_id)
        if comparison is None or not self._is_analysis_workspace_comparison(
            comparison.comparison_context
        ):
            raise NotFoundAppError("Comparison not found.")
        return self._build_comparison_read(comparison)

    def _validate_create_payload(self, payload: AnalysisComparisonCreateRequest) -> None:
        job_ids = payload.analysis_job_ids
        if len(set(job_ids)) != len(job_ids):
            raise ValidationAppError("Select distinct analyses before creating a comparison.")
        if payload.baseline_job_id is not None and payload.baseline_job_id not in job_ids:
            raise ValidationAppError(
                "The selected baseline must also be part of the comparison set."
            )

    async def _load_candidates(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        analysis_job_ids: list[UUID],
    ) -> list[LoadedAnalysisComparisonCandidate]:
        jobs = await self.predictions.inference.list_analysis_jobs_by_ids(job_ids=analysis_job_ids)
        jobs_by_id = {job.id: job for job in jobs}
        missing_ids = [job_id for job_id in analysis_job_ids if job_id not in jobs_by_id]
        if missing_ids:
            raise NotFoundAppError("Analysis job not found.")
        asset_ids: list[UUID] = []
        ordered_jobs = [jobs_by_id[job_id] for job_id in analysis_job_ids]
        for job in ordered_jobs:
            raw_asset_id = (job.runtime_params or {}).get("asset_id")
            if raw_asset_id is None:
                continue
            try:
                asset_ids.append(UUID(str(raw_asset_id)))
            except (TypeError, ValueError):
                continue
        assets_by_id = await self.analysis.uploads.get_analysis_artifacts_by_ids(
            artifact_ids=asset_ids,
            project_id=project_id,
            created_by_user_id=user_id,
        )

        loaded: list[LoadedAnalysisComparisonCandidate] = []
        for raw_job in ordered_jobs:
            self.analysis._ensure_job_ownership(raw_job, user_id=user_id)
            if raw_job.project_id != project_id:
                raise ValidationAppError(
                    "All analyses in a comparison must belong to the active workspace."
                )
            if (
                str((raw_job.runtime_params or {}).get("analysis_surface") or "")
                != "analysis_dashboard"
            ):
                raise ValidationAppError("Only analysis workspace jobs can be compared here.")
            result = self.analysis._build_result(raw_job)
            if result is None:
                raise ConflictAppError(
                    "Each selected analysis must have completed results before comparison."
                )
            raw_asset_id = (raw_job.runtime_params or {}).get("asset_id")
            asset = None
            if raw_asset_id is not None:
                try:
                    asset = assets_by_id.get(UUID(str(raw_asset_id)))
                except (TypeError, ValueError):
                    asset = None
            creative_version_id = raw_job.creative_version_id or (
                asset.creative_version_id if asset is not None else None
            )
            if creative_version_id is None:
                raise ConflictAppError(
                    "This analysis was created before creative version promotion completed. "
                    "Re-run it before comparing."
                )

            loaded.append(
                LoadedAnalysisComparisonCandidate(
                    analysis_job_id=raw_job.id,
                    creative_id=raw_job.creative_id,
                    creative_version_id=creative_version_id,
                    job=self.analysis._build_job_read(raw_job),
                    asset=self.analysis._build_asset_read(asset) if asset is not None else None,
                    result=result,
                )
            )
        return loaded

    def _rank_candidates(
        self,
        loaded_candidates: list[LoadedAnalysisComparisonCandidate],
    ) -> list[RankedAnalysisComparisonCandidate]:
        ranked_payloads: list[dict[str, Any]] = []
        for candidate in loaded_candidates:
            score_map = self._extract_score_map(candidate.result)
            ranked_payloads.append(
                {
                    "candidate": candidate,
                    "scores_json": score_map,
                    "rationale": self._build_rationale(score_map),
                }
            )

        ranked_payloads.sort(
            key=lambda item: (
                float(item["scores_json"].get("composite", 0.0)),
                float(item["scores_json"].get("conversion_proxy", 0.0)),
                float(item["scores_json"].get("overall_attention", 0.0)),
                float(item["scores_json"].get("confidence", 0.0)),
                str(item["candidate"].analysis_job_id),
            ),
            reverse=True,
        )
        return [
            RankedAnalysisComparisonCandidate(
                candidate=payload["candidate"],
                overall_rank=index,
                scores_json=payload["scores_json"],
                rationale=payload["rationale"],
            )
            for index, payload in enumerate(ranked_payloads, start=1)
        ]

    def _score_in_llm_neutral_band(self, value: float) -> bool:
        return self._NEUTRAL_SCORE_LOW <= float(value) <= self._NEUTRAL_SCORE_HIGH

    def _summary_looks_like_llm_neutral_defaults(self, summary: AnalysisSummaryPayload) -> bool:
        """True when all core summary scores sit at the LLM fallback (~50)."""
        checks = (
            summary.overall_attention_score,
            summary.hook_score_first_3_seconds,
            summary.sustained_engagement_score,
            summary.memory_proxy_score,
            summary.cognitive_load_proxy,
        )
        return all(self._score_in_llm_neutral_band(float(v)) for v in checks)

    def _tribe_timeline_engagement_scores(
        self, result: AnalysisResultRead
    ) -> dict[str, float] | None:
        """Derive attention/hook/sustained from TRIBE timeline when LLM returned neutral scores."""
        timeline = result.timeline_json or []
        if len(timeline) < 2:
            return None
        engagements = [float(p.engagement_score) for p in timeline]
        span = max(engagements) - min(engagements)
        if span < 0.25:
            return None
        overall = sum(engagements) / len(engagements)
        opening = [float(p.engagement_score) for p in timeline if p.timestamp_ms < 3000]
        sustained_rows = [float(p.engagement_score) for p in timeline if p.timestamp_ms >= 3000]
        hook_base = opening if opening else engagements[: max(1, len(engagements) // 4)]
        hook = sum(hook_base) / len(hook_base)
        sustained = (
            sum(sustained_rows) / len(sustained_rows) if sustained_rows else overall
        )
        return {
            "overall_attention": round(overall, 2),
            "hook": round(hook, 2),
            "sustained_engagement": round(sustained, 2),
        }

    def _tribe_timeline_memory_score(self, result: AnalysisResultRead) -> float | None:
        timeline = result.timeline_json or []
        if len(timeline) < 2:
            return None
        memories = [float(p.memory_proxy) for p in timeline]
        if max(memories) - min(memories) < 0.25:
            return None
        return round(sum(memories) / len(memories), 2)

    def _tribe_segment_low_cognitive_load(self, result: AnalysisResultRead) -> float | None:
        segments = result.segments_json or []
        if len(segments) < 2:
            return None
        loads = [float(s.cognitive_load) for s in segments]
        if max(loads) - min(loads) < 0.25:
            return None
        avg_load = sum(loads) / len(loads)
        return round(min(100.0, max(0.0, 100.0 - avg_load)), 2)

    def _extract_score_map(self, result: AnalysisResultRead) -> dict[str, float]:
        metrics_by_key = {str(metric.key): float(metric.value) for metric in result.metrics_json}
        summary = result.summary_json
        score_map = {
            "conversion_proxy": round(float(metrics_by_key.get("conversion_proxy_score", 0.0)), 2),
            "overall_attention": round(float(summary.overall_attention_score), 2),
            "hook": round(float(summary.hook_score_first_3_seconds), 2),
            "sustained_engagement": round(float(summary.sustained_engagement_score), 2),
            "memory_proxy": round(float(summary.memory_proxy_score), 2),
            "low_cognitive_load": round(100.0 - float(summary.cognitive_load_proxy), 2),
            "confidence": round(float(summary.confidence or 0.0), 2),
        }
        if self._summary_looks_like_llm_neutral_defaults(summary):
            tribe_eng = self._tribe_timeline_engagement_scores(result)
            if tribe_eng:
                score_map.update(tribe_eng)
            mem_fb = self._tribe_timeline_memory_score(result)
            if mem_fb is not None:
                score_map["memory_proxy"] = mem_fb
            low_fb = self._tribe_segment_low_cognitive_load(result)
            if low_fb is not None:
                score_map["low_cognitive_load"] = low_fb
        score_map["composite"] = round(
            sum(score_map[key] * weight for key, weight in self.SCORE_WEIGHTS.items()),
            2,
        )
        return score_map

    def _build_rationale(self, score_map: dict[str, float]) -> str:
        ranked_metrics = sorted(
            (
                (key, value)
                for key, value in score_map.items()
                if key not in {"composite", "confidence"}
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        strongest = ", ".join(
            self._format_metric_label(metric_name) for metric_name, _ in ranked_metrics[:2]
        )
        weakest_metric = ranked_metrics[-1][0] if ranked_metrics else "unknown"
        weakest_label = self._format_metric_label(weakest_metric)
        return f"Strongest predicted drivers: {strongest}. Primary drag: {weakest_label}."

    def _build_summary_json(
        self,
        *,
        ranked_candidates: list[RankedAnalysisComparisonCandidate],
        baseline_job_id: UUID,
    ) -> dict[str, Any]:
        metric_leaders: list[dict[str, Any]] = []
        metrics_to_compare = [
            "composite",
            "conversion_proxy",
            "overall_attention",
            "hook",
            "sustained_engagement",
            "memory_proxy",
            "low_cognitive_load",
        ]
        for metric_name in metrics_to_compare:
            leader = max(
                ranked_candidates,
                key=lambda candidate: float(candidate.scores_json.get(metric_name, 0.0)),
            )
            metric_leaders.append(
                {
                    "metric": metric_name,
                    "analysis_job_id": str(leader.candidate.analysis_job_id),
                    "value": leader.scores_json.get(metric_name, 0.0),
                }
            )

        winner = ranked_candidates[0] if ranked_candidates else None
        return {
            "method": "analysis_dashboard_weighted_composite",
            "weights": self.SCORE_WEIGHTS,
            "candidate_count": len(ranked_candidates),
            "baseline_job_id": str(baseline_job_id),
            "winning_analysis_job_id": str(winner.candidate.analysis_job_id)
            if winner is not None
            else None,
            "winning_rationale": winner.rationale if winner is not None else None,
            "metric_leaders": metric_leaders,
        }

    def _build_stored_comparison_context(
        self,
        *,
        user_id: UUID,
        payload: AnalysisComparisonCreateRequest,
        baseline_job_id: UUID,
        ranked_candidates: list[RankedAnalysisComparisonCandidate],
    ) -> dict[str, Any]:
        ordered_job_ids = [str(job_id) for job_id in payload.analysis_job_ids]
        winner = ranked_candidates[0] if ranked_candidates else None
        return {
            "analysis_surface": "analysis_compare_workspace",
            "created_by_user_id": str(user_id),
            "baseline_job_id": str(baseline_job_id),
            "winning_analysis_job_id": str(winner.candidate.analysis_job_id)
            if winner is not None
            else None,
            "analysis_job_ids": ordered_job_ids,
            "requested_context": payload.comparison_context,
            "items_metadata": [
                {
                    "analysis_job_id": str(ranked_candidate.candidate.analysis_job_id),
                    "creative_id": str(ranked_candidate.candidate.creative_id),
                    "creative_version_id": str(ranked_candidate.candidate.creative_version_id),
                    "label": self._build_candidate_label(ranked_candidate.candidate),
                    "job": ranked_candidate.candidate.job.model_dump(mode="json"),
                    "asset": ranked_candidate.candidate.asset.model_dump(mode="json")
                    if ranked_candidate.candidate.asset is not None
                    else None,
                    "result": ranked_candidate.candidate.result.model_dump(mode="json"),
                    "overall_rank": ranked_candidate.overall_rank,
                    "scores_json": ranked_candidate.scores_json,
                    "rationale": ranked_candidate.rationale,
                    "selected_order": payload.analysis_job_ids.index(
                        ranked_candidate.candidate.analysis_job_id
                    )
                    + 1,
                }
                for ranked_candidate in ranked_candidates
            ],
        }

    def _build_default_name(
        self, loaded_candidates: list[LoadedAnalysisComparisonCandidate]
    ) -> str:
        primary_label = (
            self._build_candidate_label(loaded_candidates[0])
            if loaded_candidates
            else "Analysis compare"
        )
        if len(loaded_candidates) == 2:
            return f"{primary_label} vs {self._build_candidate_label(loaded_candidates[1])}"
        return f"{primary_label} + {len(loaded_candidates) - 1} more"

    def _build_list_item(self, comparison) -> AnalysisComparisonListItemRead:
        items_metadata = self._read_items_metadata(comparison.comparison_context)
        winning_analysis_job_id = self._resolve_winning_analysis_job_id(
            comparison_context=comparison.comparison_context,
            winning_creative_version_id=comparison.result.winning_creative_version_id
            if comparison.result
            else None,
        )
        baseline_job_id = self._read_uuid(comparison.comparison_context.get("baseline_job_id"))
        return AnalysisComparisonListItemRead(
            id=comparison.id,
            name=comparison.name,
            created_at=comparison.created_at,
            winning_analysis_job_id=winning_analysis_job_id,
            baseline_job_id=baseline_job_id,
            candidate_count=len(items_metadata),
            summary_json=comparison.result.summary_json if comparison.result is not None else {},
            item_labels=[str(item.get("label") or "Comparison item") for item in items_metadata],
        )

    def _build_comparison_read(self, comparison) -> AnalysisComparisonRead:
        if comparison.result is None:
            raise NotFoundAppError("Comparison result not found.")

        items_metadata = self._read_items_metadata(comparison.comparison_context)
        results_by_version_id = {
            str(item_result.creative_version_id): item_result
            for item_result in comparison.result.item_results
        }
        metadata_by_job_id = {str(item.get("analysis_job_id")): item for item in items_metadata}
        baseline_job_id = self._read_uuid(comparison.comparison_context.get("baseline_job_id"))
        baseline_metadata = (
            metadata_by_job_id.get(str(baseline_job_id)) if baseline_job_id is not None else None
        )
        baseline_result = (
            self._parse_result_metadata(baseline_metadata.get("result"))
            if baseline_metadata is not None
            else None
        )

        items: list[AnalysisComparisonItemRead] = []
        winning_analysis_job_id = self._resolve_winning_analysis_job_id(
            comparison_context=comparison.comparison_context,
            winning_creative_version_id=comparison.result.winning_creative_version_id,
        )
        for metadata in items_metadata:
            creative_version_id = str(metadata.get("creative_version_id") or "")
            item_result = results_by_version_id.get(creative_version_id)
            analysis_job_id = self._read_uuid(metadata.get("analysis_job_id"))
            if analysis_job_id is None:
                continue
            candidate_result = self._parse_result_metadata(metadata.get("result"))
            metadata_scores = dict(metadata.get("scores_json") or {})
            item_scores = dict(item_result.scores_json or {}) if item_result is not None else {}
            overall_rank = self._read_int(metadata.get("overall_rank"))
            if overall_rank is None and item_result is not None:
                overall_rank = item_result.overall_rank
            if overall_rank is None:
                continue
            items.append(
                AnalysisComparisonItemRead(
                    analysis_job_id=analysis_job_id,
                    job=self._parse_job_metadata(metadata.get("job")),
                    asset=self._parse_asset_metadata(metadata.get("asset")),
                    result=candidate_result,
                    overall_rank=overall_rank,
                    is_winner=analysis_job_id == winning_analysis_job_id,
                    is_baseline=analysis_job_id == baseline_job_id,
                    scores_json=metadata_scores or item_scores,
                    delta_json=self._build_delta_json(
                        baseline_result=baseline_result,
                        candidate_result=candidate_result,
                        baseline_scores=baseline_metadata.get("scores_json")
                        if baseline_metadata is not None
                        else None,
                        candidate_scores=metadata_scores or item_scores,
                    ),
                    rationale=str(
                        metadata.get("rationale")
                        or (item_result.rationale if item_result is not None else "")
                        or ""
                    ),
                    scene_deltas_json=self._build_scene_deltas(
                        baseline_result=baseline_result,
                        candidate_result=candidate_result,
                        is_baseline=analysis_job_id == baseline_job_id,
                    ),
                    recommendation_overlap_json=self._build_recommendation_overlap(
                        baseline_result=baseline_result,
                        candidate_result=candidate_result,
                        is_baseline=analysis_job_id == baseline_job_id,
                    ),
                )
            )

        items.sort(key=lambda item: item.overall_rank)
        return AnalysisComparisonRead(
            id=comparison.id,
            name=comparison.name,
            created_at=comparison.created_at,
            winning_analysis_job_id=winning_analysis_job_id,
            baseline_job_id=baseline_job_id,
            summary_json=comparison.result.summary_json or {},
            comparison_context=comparison.comparison_context or {},
            items=items,
        )

    def _resolve_winning_analysis_job_id(
        self,
        *,
        comparison_context: dict[str, Any],
        winning_creative_version_id: UUID | None,
    ) -> UUID | None:
        stored_winning_job_id = self._read_uuid(
            comparison_context.get("winning_analysis_job_id")
        )
        if stored_winning_job_id is not None:
            return stored_winning_job_id
        winning_version = (
            str(winning_creative_version_id) if winning_creative_version_id is not None else None
        )
        if winning_version is None:
            return None
        for metadata in self._read_items_metadata(comparison_context):
            if str(metadata.get("creative_version_id") or "") == winning_version:
                return self._read_uuid(metadata.get("analysis_job_id"))
        return None

    def _build_delta_json(
        self,
        *,
        baseline_result: AnalysisResultRead | None,
        candidate_result: AnalysisResultRead,
        baseline_scores: dict[str, Any] | None,
        candidate_scores: dict[str, Any],
    ) -> dict[str, float]:
        if baseline_result is None:
            return {}

        baseline_metric_rows = {
            metric.key: float(metric.value) for metric in baseline_result.metrics_json
        }
        candidate_metric_rows = {
            metric.key: float(metric.value) for metric in candidate_result.metrics_json
        }
        baseline_score_map = {
            str(key): float(value) for key, value in (baseline_scores or {}).items()
        }
        candidate_score_map = {str(key): float(value) for key, value in candidate_scores.items()}

        return {
            "overall_attention": round(
                float(candidate_result.summary_json.overall_attention_score)
                - float(baseline_result.summary_json.overall_attention_score),
                2,
            ),
            "hook": round(
                float(candidate_result.summary_json.hook_score_first_3_seconds)
                - float(baseline_result.summary_json.hook_score_first_3_seconds),
                2,
            ),
            "sustained_engagement": round(
                float(candidate_result.summary_json.sustained_engagement_score)
                - float(baseline_result.summary_json.sustained_engagement_score),
                2,
            ),
            "memory_proxy": round(
                float(candidate_result.summary_json.memory_proxy_score)
                - float(baseline_result.summary_json.memory_proxy_score),
                2,
            ),
            "conversion_proxy": round(
                float(candidate_metric_rows.get("conversion_proxy_score", 0.0))
                - float(baseline_metric_rows.get("conversion_proxy_score", 0.0)),
                2,
            ),
            "low_cognitive_load": round(
                (100.0 - float(candidate_result.summary_json.cognitive_load_proxy))
                - (100.0 - float(baseline_result.summary_json.cognitive_load_proxy)),
                2,
            ),
            "composite": round(
                float(candidate_score_map.get("composite", 0.0))
                - float(baseline_score_map.get("composite", 0.0)),
                2,
            ),
        }

    def _build_scene_deltas(
        self,
        *,
        baseline_result: AnalysisResultRead | None,
        candidate_result: AnalysisResultRead,
        is_baseline: bool,
    ) -> list[dict[str, Any]]:
        if baseline_result is None or is_baseline:
            return []

        rows: list[dict[str, Any]] = []
        baseline_segments = baseline_result.segments_json
        candidate_segments = candidate_result.segments_json
        for index, candidate_segment in enumerate(candidate_segments):
            baseline_segment = baseline_segments[index] if index < len(baseline_segments) else None
            baseline_attention = (
                float(baseline_segment.attention_score) if baseline_segment is not None else 0.0
            )
            candidate_attention = float(candidate_segment.attention_score)
            rows.append(
                {
                    "segment_index": candidate_segment.segment_index,
                    "label": candidate_segment.label,
                    "baseline_window": (
                        f"{baseline_segment.start_time_ms}-{baseline_segment.end_time_ms}"
                        if baseline_segment is not None
                        else None
                    ),
                    "candidate_window": (
                        f"{candidate_segment.start_time_ms}-{candidate_segment.end_time_ms}"
                    ),
                    "baseline_attention": round(baseline_attention, 2),
                    "candidate_attention": round(candidate_attention, 2),
                    "attention_delta": round(candidate_attention - baseline_attention, 2),
                    "engagement_delta_delta": round(
                        float(candidate_segment.engagement_delta)
                        - float(
                            baseline_segment.engagement_delta
                            if baseline_segment is not None
                            else 0.0
                        ),
                        2,
                    ),
                    "baseline_note": baseline_segment.note
                    if baseline_segment is not None
                    else None,
                    "candidate_note": candidate_segment.note,
                }
            )
        rows.sort(key=lambda row: abs(float(row["attention_delta"])), reverse=True)
        return rows[:5]

    def _build_recommendation_overlap(
        self,
        *,
        baseline_result: AnalysisResultRead | None,
        candidate_result: AnalysisResultRead,
        is_baseline: bool,
    ) -> dict[str, Any]:
        candidate_titles = [
            recommendation.title for recommendation in candidate_result.recommendations_json
        ]
        if baseline_result is None or is_baseline:
            return {
                "shared_titles": [],
                "candidate_only_titles": candidate_titles,
                "baseline_only_titles": [],
            }

        baseline_titles = [
            recommendation.title for recommendation in baseline_result.recommendations_json
        ]
        normalized_baseline = {
            self._normalize_recommendation_title(title): title for title in baseline_titles
        }
        normalized_candidate = {
            self._normalize_recommendation_title(title): title for title in candidate_titles
        }
        shared_keys = sorted(set(normalized_baseline).intersection(normalized_candidate))
        candidate_only_keys = sorted(set(normalized_candidate) - set(normalized_baseline))
        baseline_only_keys = sorted(set(normalized_baseline) - set(normalized_candidate))
        return {
            "shared_titles": [normalized_candidate[key] for key in shared_keys],
            "candidate_only_titles": [normalized_candidate[key] for key in candidate_only_keys],
            "baseline_only_titles": [normalized_baseline[key] for key in baseline_only_keys],
        }

    def _build_candidate_label(self, candidate: LoadedAnalysisComparisonCandidate) -> str:
        if candidate.asset is not None and candidate.asset.original_filename:
            return candidate.asset.original_filename
        if candidate.job.objective:
            return candidate.job.objective
        return f"Analysis {str(candidate.analysis_job_id)[:8]}"

    def _is_analysis_workspace_comparison(self, comparison_context: dict[str, Any] | None) -> bool:
        return (
            str((comparison_context or {}).get("analysis_surface") or "")
            == "analysis_compare_workspace"
        )

    def _read_items_metadata(
        self, comparison_context: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        raw_items = (comparison_context or {}).get("items_metadata") or []
        return [item for item in raw_items if isinstance(item, dict)]

    def _parse_job_metadata(self, raw_value: Any) -> AnalysisJobRead:
        return AnalysisJobRead.model_validate(raw_value or {})

    def _parse_asset_metadata(self, raw_value: Any) -> AnalysisAssetRead | None:
        if raw_value is None:
            return None
        return AnalysisAssetRead.model_validate(raw_value)

    def _parse_result_metadata(self, raw_value: Any) -> AnalysisResultRead:
        return AnalysisResultRead.model_validate(raw_value or {})

    def _read_uuid(self, raw_value: Any) -> UUID | None:
        try:
            return UUID(str(raw_value))
        except (TypeError, ValueError):
            return None

    def _read_int(self, raw_value: Any) -> int | None:
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _format_metric_label(self, metric_name: str) -> str:
        label_map = {
            "conversion_proxy": "conversion proxy",
            "overall_attention": "overall attention",
            "hook": "hook strength",
            "sustained_engagement": "sustained engagement",
            "memory_proxy": "memory proxy",
            "low_cognitive_load": "low cognitive load",
        }
        return label_map.get(metric_name, metric_name.replace("_", " "))

    def _normalize_recommendation_title(self, value: str) -> str:
        return " ".join(value.lower().split())
