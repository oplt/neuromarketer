from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.core.logging import duration_ms, get_logger, log_event
from backend.db.models import SuggestionStatus, SuggestionType, VisualizationType
from backend.llm.analysis_scoring_service import AnalysisScoringResponse, AnalysisScoringService
from backend.schemas.llm_scoring import MetricAssessment, TimelineMetricPoint

logger = get_logger(__name__)
MAX_SCORING_SEGMENTS = 12
MAX_SCORING_EVENT_TYPES = 4
MAX_SCORING_TOP_ROIS = 6
MAX_AUDIENCE_CONTEXT_FIELDS = 8


def _decimal(value: float, *, precision: int = 2) -> Decimal:
    return Decimal(str(round(value, precision)))


def _score_decimal(value: int | float) -> Decimal:
    return _decimal(float(value), precision=2)


def _normalize_notes(values: Iterable[str], *, limit: int = 6) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        text = str(raw_value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _round_signal(value: Any, *, precision: int = 4) -> float:
    try:
        return round(float(value), precision)
    except (TypeError, ValueError):
        return 0.0


def _compact_audience_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    compacted: dict[str, Any] = {}
    for key in sorted(value.keys()):
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        raw_value = value.get(key)
        if isinstance(raw_value, (str, int, float, bool)) or raw_value is None:
            compacted[normalized_key] = raw_value
        elif isinstance(raw_value, list):
            scalar_items = [item for item in raw_value if isinstance(item, (str, int, float, bool))]
            if scalar_items:
                compacted[normalized_key] = scalar_items[:4]
        if len(compacted) >= MAX_AUDIENCE_CONTEXT_FIELDS:
            break
    return compacted


@dataclass(slots=True)
class ScoreItem:
    score_type: str
    normalized_score: Decimal
    raw_value: Decimal | None
    confidence: Decimal | None
    percentile: Decimal | None
    metadata_json: dict[str, Any]


@dataclass(slots=True)
class VisualizationItem:
    visualization_type: VisualizationType
    title: str | None
    storage_uri: str | None
    data_json: dict[str, Any]


@dataclass(slots=True)
class TimelinePointItem:
    timestamp_ms: int
    attention_score: Decimal | None
    emotion_score: Decimal | None
    memory_score: Decimal | None
    cognitive_load_score: Decimal | None
    conversion_proxy_score: Decimal | None
    metadata_json: dict[str, Any]


@dataclass(slots=True)
class SuggestionItem:
    suggestion_type: SuggestionType
    status: SuggestionStatus
    title: str
    rationale: str
    proposed_change_json: dict[str, Any]
    expected_score_lift_json: dict[str, Any]
    confidence: Decimal | None


@dataclass(slots=True)
class ScoringBundle:
    scores: list[ScoreItem]
    visualizations: list[VisualizationItem]
    timeline_points: list[TimelinePointItem]
    suggestions: list[SuggestionItem]
    notes: list[str]


class NeuroScoringService:
    """
    Product scoring layer.

    Inputs:
    - `reduced_feature_vector`: internal features derived from public TRIBE v2 mesh predictions
    - `region_activation_summary`: derived summaries over those predictions

    Outputs:
    - business-facing neuromarketing scores
    - visualizations and suggestions for marketers

    These public scores are an LLM interpretation layer grounded in TRIBE-derived evidence.
    They are not direct TRIBE outputs.
    """

    SCORE_MODEL_NAME = "llm_analysis_scorer_v1"

    def __init__(self, analysis_scoring_service: AnalysisScoringService | None = None) -> None:
        self.analysis_scoring_service = (
            analysis_scoring_service or AnalysisScoringService.from_settings()
        )

    async def score(
        self,
        *,
        reduced_feature_vector: dict[str, Any],
        region_activation_summary: dict[str, Any],
        context: dict[str, Any],
        modality: str,
    ) -> ScoringBundle:
        started_at = time.perf_counter()
        segment_features = list(reduced_feature_vector.get("segment_features", []))[
            :MAX_SCORING_SEGMENTS
        ]

        log_event(
            logger,
            "scoring_started",
            modality=modality,
            status="started",
            segment_count=len(segment_features),
        )

        scoring_context = self._build_scoring_context(
            reduced_feature_vector=reduced_feature_vector,
            region_activation_summary=region_activation_summary,
            context=context,
            modality=modality,
        )
        scoring_response = await self.analysis_scoring_service.score(scoring_context)

        score_values = self._score_values_from_response(scoring_response)
        bundle = ScoringBundle(
            scores=self._build_scores(
                scoring_response=scoring_response,
                modality=modality,
            ),
            visualizations=self._build_visualizations(
                score_values=score_values,
                segment_features=segment_features,
                region_activation_summary=region_activation_summary,
                modality=modality,
                scoring_response=scoring_response,
            ),
            timeline_points=self._build_timeline(
                scoring_response=scoring_response,
                segment_features=segment_features,
            ),
            suggestions=self._build_suggestions(scoring_response=scoring_response),
            notes=self._build_notes(scoring_response=scoring_response),
        )
        finished_at = time.perf_counter()

        log_event(
            logger,
            "scoring_finished",
            modality=modality,
            status="succeeded",
            duration_ms=duration_ms(started_at, finished_at),
            suggestion_count=len(bundle.suggestions),
            timeline_points=len(bundle.timeline_points),
            score_summary={
                score.score_type: round(float(score.normalized_score), 2) for score in bundle.scores
            },
            provider=scoring_response.provider,
            model=scoring_response.model,
            prompt_version=scoring_response.prompt_version,
        )
        return bundle

    def _build_scores(
        self,
        *,
        scoring_response: AnalysisScoringResponse,
        modality: str,
    ) -> list[ScoreItem]:
        assessments = scoring_response.result.scores
        return [
            self._build_score_item(
                score_type="attention",
                assessment=assessments.attention,
                modality=modality,
                scoring_response=scoring_response,
            ),
            self._build_score_item(
                score_type="emotion",
                assessment=assessments.emotion,
                modality=modality,
                scoring_response=scoring_response,
            ),
            self._build_score_item(
                score_type="memory",
                assessment=assessments.memory,
                modality=modality,
                scoring_response=scoring_response,
            ),
            self._build_score_item(
                score_type="cognitive_load",
                assessment=assessments.cognitive_load,
                modality=modality,
                scoring_response=scoring_response,
            ),
            self._build_score_item(
                score_type="conversion_proxy",
                assessment=assessments.conversion_proxy,
                modality=modality,
                scoring_response=scoring_response,
            ),
        ]

    def _build_score_item(
        self,
        *,
        score_type: str,
        assessment: MetricAssessment,
        modality: str,
        scoring_response: AnalysisScoringResponse,
    ) -> ScoreItem:
        normalized_score = _score_decimal(assessment.score)
        evidence = _normalize_notes(assessment.evidence, limit=4)
        return ScoreItem(
            score_type=score_type,
            normalized_score=normalized_score,
            raw_value=None,
            confidence=_decimal(assessment.confidence, precision=4),
            percentile=normalized_score,
            metadata_json={
                "model": self.SCORE_MODEL_NAME,
                "modality": modality,
                "provider": scoring_response.provider,
                "provider_id": scoring_response.provider_id,
                "model_name": scoring_response.model,
                "prompt_version": scoring_response.prompt_version,
                "reason": assessment.reason,
                "evidence": evidence,
                "telemetry": scoring_response.telemetry,
                "interpretation_layer": (
                    "LLM-evaluated product score grounded in TRIBE-derived internal features and summaries."
                ),
            },
        )

    def _build_visualizations(
        self,
        *,
        score_values: dict[str, float],
        segment_features: list[dict[str, Any]],
        region_activation_summary: dict[str, Any],
        modality: str,
        scoring_response: AnalysisScoringResponse,
    ) -> list[VisualizationItem]:
        timeline_curve = [
            {
                "timestamp_ms": int(item.get("start_ms", index * 1000)),
                "engagement_signal": float(item.get("engagement_signal", 0.0)),
                "peak_focus_signal": float(item.get("peak_focus_signal", 0.0)),
                "consistency_signal": float(item.get("consistency_signal", 0.0)),
            }
            for index, item in enumerate(segment_features)
        ]

        return [
            VisualizationItem(
                visualization_type=VisualizationType.TIMELINE,
                title="Predicted Engagement Timeline",
                storage_uri=None,
                data_json={
                    "modality": modality,
                    "curve": timeline_curve,
                    "summary_scores": {
                        key: round(value * 100.0, 2) for key, value in score_values.items()
                    },
                    "note": "Summary scores are LLM-evaluated from TRIBE-derived evidence. Timeline curve values come from TRIBE segment features.",
                    "provider": scoring_response.provider,
                    "model_name": scoring_response.model,
                    "prompt_version": scoring_response.prompt_version,
                },
            ),
            VisualizationItem(
                visualization_type=VisualizationType.BRAIN_REGION_SUMMARY,
                title="Derived Brain Response Summary",
                storage_uri=None,
                data_json=region_activation_summary,
            ),
        ]

    def _build_timeline(
        self,
        *,
        scoring_response: AnalysisScoringResponse,
        segment_features: list[dict[str, Any]],
    ) -> list[TimelinePointItem]:
        overall_scores = scoring_response.result.scores
        points_by_index = {
            int(point.segment_index): point for point in scoring_response.result.timeline_points
        }

        if segment_features:
            timeline: list[TimelinePointItem] = []
            for index, segment in enumerate(segment_features):
                point = points_by_index.get(index)
                timestamp_ms = int(
                    segment.get(
                        "start_ms",
                        point.timestamp_ms if point is not None else index * 1000,
                    )
                )
                timeline.append(
                    self._timeline_item_from_point(
                        point=point,
                        timestamp_ms=timestamp_ms,
                        segment_index=index,
                        scoring_response=scoring_response,
                        fallback_scores=overall_scores,
                        segment=segment,
                    )
                )
            return timeline

        if scoring_response.result.timeline_points:
            return [
                self._timeline_item_from_point(
                    point=point,
                    timestamp_ms=int(point.timestamp_ms),
                    segment_index=int(point.segment_index),
                    scoring_response=scoring_response,
                    fallback_scores=overall_scores,
                    segment=None,
                )
                for point in scoring_response.result.timeline_points
            ]

        return [
            TimelinePointItem(
                timestamp_ms=0,
                attention_score=_score_decimal(overall_scores.attention.score),
                emotion_score=_score_decimal(overall_scores.emotion.score),
                memory_score=_score_decimal(overall_scores.memory.score),
                cognitive_load_score=_score_decimal(overall_scores.cognitive_load.score),
                conversion_proxy_score=_score_decimal(overall_scores.conversion_proxy.score),
                metadata_json={
                    "segment_index": 0,
                    "source": "llm_analysis_scoring",
                    "provider": scoring_response.provider,
                    "model_name": scoring_response.model,
                },
            )
        ]

    def _timeline_item_from_point(
        self,
        *,
        point: TimelineMetricPoint | None,
        timestamp_ms: int,
        segment_index: int,
        scoring_response: AnalysisScoringResponse,
        fallback_scores: Any,
        segment: dict[str, Any] | None,
    ) -> TimelinePointItem:
        rationale = point.rationale if point is not None else None
        metadata_json = {
            "segment_index": segment_index,
            "source": "llm_analysis_scoring",
            "provider": scoring_response.provider,
            "model_name": scoring_response.model,
        }
        if rationale:
            metadata_json["rationale"] = rationale
        if segment is not None:
            metadata_json["event_count"] = int(segment.get("event_count", 0))
            metadata_json["event_types"] = list(segment.get("event_types", []))

        return TimelinePointItem(
            timestamp_ms=timestamp_ms,
            attention_score=_score_decimal(
                point.attention_score if point is not None else fallback_scores.attention.score
            ),
            emotion_score=_score_decimal(
                point.emotion_score if point is not None else fallback_scores.emotion.score
            ),
            memory_score=_score_decimal(
                point.memory_score if point is not None else fallback_scores.memory.score
            ),
            cognitive_load_score=_score_decimal(
                point.cognitive_load_score
                if point is not None
                else fallback_scores.cognitive_load.score
            ),
            conversion_proxy_score=_score_decimal(
                point.conversion_proxy_score
                if point is not None
                else fallback_scores.conversion_proxy.score
            ),
            metadata_json=metadata_json,
        )

    def _build_suggestions(
        self, *, scoring_response: AnalysisScoringResponse
    ) -> list[SuggestionItem]:
        suggestions: list[SuggestionItem] = []
        for suggestion in scoring_response.result.suggestions:
            proposed_change_json = dict(suggestion.proposed_change_json or {})
            if suggestion.timestamp_ms is not None:
                proposed_change_json.setdefault("timestamp_ms", int(suggestion.timestamp_ms))
            suggestions.append(
                SuggestionItem(
                    suggestion_type=SuggestionType(suggestion.suggestion_type),
                    status=SuggestionStatus.PROPOSED,
                    title=suggestion.title,
                    rationale=suggestion.rationale,
                    proposed_change_json=proposed_change_json,
                    expected_score_lift_json={
                        key: round(float(value), 2)
                        for key, value in suggestion.expected_score_lift_json.items()
                    },
                    confidence=_decimal(suggestion.confidence, precision=4),
                )
            )
        return suggestions

    def _build_notes(self, *, scoring_response: AnalysisScoringResponse) -> list[str]:
        return _normalize_notes(
            [
                scoring_response.result.overall_summary,
                *scoring_response.result.notes,
            ]
        )

    def _build_scoring_context(
        self,
        *,
        reduced_feature_vector: dict[str, Any],
        region_activation_summary: dict[str, Any],
        context: dict[str, Any],
        modality: str,
    ) -> dict[str, Any]:
        campaign_context = context.get("campaign_context") if isinstance(context, dict) else {}
        campaign_context = campaign_context if isinstance(campaign_context, dict) else {}
        audience_context = context.get("audience_context") if isinstance(context, dict) else {}
        audience_context = audience_context if isinstance(audience_context, dict) else {}
        segment_features = list(reduced_feature_vector.get("segment_features", []))[
            :MAX_SCORING_SEGMENTS
        ]

        scalar_features = {
            key: reduced_feature_vector.get(key)
            for key in (
                "feature_contract_version",
                "global_abs_mean_activation",
                "global_abs_peak_activation",
                "segment_count",
                "event_row_count",
                "derived_neural_engagement_signal",
                "derived_peak_focus_signal",
                "derived_temporal_dynamics_signal",
                "derived_temporal_consistency_signal",
                "derived_linguistic_load_signal",
                "derived_context_density_signal",
                "derived_hemisphere_balance_signal",
                "derived_audio_language_mix_signal",
            )
            if key in reduced_feature_vector
        }

        return {
            "modality": modality,
            "campaign_context": {
                "objective": campaign_context.get("objective"),
                "goal_template": campaign_context.get("goal_template"),
                "channel": campaign_context.get("channel"),
                "audience_segment": campaign_context.get("audience_segment"),
            },
            "audience_context": _compact_audience_context(audience_context),
            "tribe_feature_summary": scalar_features,
            "segment_features": [
                {
                    "segment_index": int(segment.get("segment_index", index)),
                    "start_ms": int(segment.get("start_ms", index * 1000)),
                    "duration_ms": int(segment.get("duration_ms", 1000)),
                    "event_count": int(segment.get("event_count", 0)),
                    "event_types": [
                        str(item)
                        for item in list(segment.get("event_types", []))[:MAX_SCORING_EVENT_TYPES]
                    ],
                    "engagement_signal": _round_signal(segment.get("engagement_signal", 0.0)),
                    "peak_focus_signal": _round_signal(segment.get("peak_focus_signal", 0.0)),
                    "consistency_signal": _round_signal(segment.get("consistency_signal", 0.0)),
                    "temporal_change_signal": _round_signal(
                        segment.get("temporal_change_signal", 0.0)
                    ),
                    "hemisphere_balance_signal": _round_signal(
                        segment.get("hemisphere_balance_signal", 0.0)
                    ),
                }
                for index, segment in enumerate(segment_features)
            ],
            "region_activation_summary": {
                "hemisphere_summary": region_activation_summary.get("hemisphere_summary"),
                "top_rois": list(region_activation_summary.get("top_rois") or [])[
                    :MAX_SCORING_TOP_ROIS
                ],
            },
        }

    def _score_values_from_response(
        self, scoring_response: AnalysisScoringResponse
    ) -> dict[str, float]:
        assessments = scoring_response.result.scores
        return {
            "attention": float(assessments.attention.score) / 100.0,
            "emotion": float(assessments.emotion.score) / 100.0,
            "memory": float(assessments.memory.score) / 100.0,
            "cognitive_load": float(assessments.cognitive_load.score) / 100.0,
            "conversion_proxy": float(assessments.conversion_proxy.score) / 100.0,
        }
