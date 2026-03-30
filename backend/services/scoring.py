from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.db.models import SuggestionStatus, SuggestionType, VisualizationType


def _decimal(value: float, *, precision: int = 2) -> Decimal:
    return Decimal(str(round(value, precision)))


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


class NeuroScoringService:
    """
    Product scoring layer.

    Inputs:
    - `reduced_feature_vector`: internal features derived from public TRIBE v2 mesh predictions
    - `region_activation_summary`: derived summaries over those predictions

    Outputs:
    - business-facing neuromarketing scores
    - visualizations and suggestions for marketers

    These public scores are our interpretation layer. They are not direct TRIBE outputs.
    """

    SCORE_MODEL_NAME = "neuro_scorer_v3"

    @staticmethod
    def _clip01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @classmethod
    def _to_pct(cls, value: float) -> Decimal:
        return _decimal(cls._clip01(value) * 100.0)

    async def score(
        self,
        *,
        reduced_feature_vector: dict[str, Any],
        region_activation_summary: dict[str, Any],
        context: dict[str, Any],
        modality: str,
    ) -> ScoringBundle:
        engagement = float(reduced_feature_vector.get("derived_neural_engagement_signal", 0.5))
        peak_focus = float(reduced_feature_vector.get("derived_peak_focus_signal", 0.5))
        temporal_dynamics = float(reduced_feature_vector.get("derived_temporal_dynamics_signal", 0.3))
        temporal_consistency = float(reduced_feature_vector.get("derived_temporal_consistency_signal", 0.5))
        linguistic_load = float(reduced_feature_vector.get("derived_linguistic_load_signal", 0.4))
        context_density = float(reduced_feature_vector.get("derived_context_density_signal", 0.4))
        hemisphere_balance = float(reduced_feature_vector.get("derived_hemisphere_balance_signal", 0.5))
        audio_language_mix = float(reduced_feature_vector.get("derived_audio_language_mix_signal", 0.3))
        segment_features = list(reduced_feature_vector.get("segment_features", []))
        hemisphere_summary = region_activation_summary.get("hemisphere_summary", {})

        attention_value = self._clip01(
            (engagement * 0.46)
            + (peak_focus * 0.28)
            + (temporal_consistency * 0.18)
            + (hemisphere_balance * 0.08)
        )
        emotion_value = self._clip01(
            (engagement * 0.34)
            + (temporal_dynamics * 0.24)
            + (audio_language_mix * 0.18)
            + (peak_focus * 0.12)
            + 0.12
        )
        memory_value = self._clip01(
            (temporal_consistency * 0.38)
            + (engagement * 0.32)
            + (peak_focus * 0.18)
            + (hemisphere_balance * 0.12)
        )
        cognitive_load_value = self._clip01(
            (linguistic_load * 0.5)
            + (context_density * 0.3)
            + ((1.0 - temporal_consistency) * 0.2)
        )
        conversion_proxy_value = self._clip01(
            (attention_value * 0.29)
            + (emotion_value * 0.17)
            + (memory_value * 0.27)
            + (peak_focus * 0.12)
            + (audio_language_mix * 0.08)
            - (cognitive_load_value * 0.13)
            + 0.09
        )

        score_values = {
            "attention": attention_value,
            "emotion": emotion_value,
            "memory": memory_value,
            "cognitive_load": cognitive_load_value,
            "conversion_proxy": conversion_proxy_value,
        }
        confidence_value = self._compute_confidence(
            segment_count=len(segment_features),
            context_density=context_density,
            modality=modality,
        )

        scores = [
            self._build_score_item(
                score_type="attention",
                normalized_value=attention_value,
                raw_value=engagement,
                confidence_value=confidence_value,
                modality=modality,
                feature_basis=["derived_neural_engagement_signal", "derived_peak_focus_signal"],
            ),
            self._build_score_item(
                score_type="emotion",
                normalized_value=emotion_value,
                raw_value=(temporal_dynamics + audio_language_mix) / 2,
                confidence_value=confidence_value,
                modality=modality,
                feature_basis=["derived_temporal_dynamics_signal", "derived_audio_language_mix_signal"],
            ),
            self._build_score_item(
                score_type="memory",
                normalized_value=memory_value,
                raw_value=temporal_consistency,
                confidence_value=confidence_value,
                modality=modality,
                feature_basis=["derived_temporal_consistency_signal", "derived_peak_focus_signal"],
            ),
            self._build_score_item(
                score_type="cognitive_load",
                normalized_value=cognitive_load_value,
                raw_value=linguistic_load,
                confidence_value=confidence_value,
                modality=modality,
                feature_basis=["derived_linguistic_load_signal", "derived_context_density_signal"],
            ),
            self._build_score_item(
                score_type="conversion_proxy",
                normalized_value=conversion_proxy_value,
                raw_value=conversion_proxy_value,
                confidence_value=max(0.5, confidence_value - 0.06),
                modality=modality,
                feature_basis=["attention", "emotion", "memory", "cognitive_load"],
            ),
        ]

        return ScoringBundle(
            scores=scores,
            visualizations=self._build_visualizations(
                score_values=score_values,
                segment_features=segment_features,
                region_activation_summary=region_activation_summary,
                modality=modality,
            ),
            timeline_points=self._build_timeline(
                score_values=score_values,
                segment_features=segment_features,
            ),
            suggestions=self._build_suggestions(
                score_values=score_values,
                modality=modality,
                context=context,
                reduced_feature_vector=reduced_feature_vector,
                hemisphere_summary=hemisphere_summary,
            ),
        )

    def _build_score_item(
        self,
        *,
        score_type: str,
        normalized_value: float,
        raw_value: float,
        confidence_value: float,
        modality: str,
        feature_basis: list[str],
    ) -> ScoreItem:
        percentile = self._to_pct(normalized_value)
        return ScoreItem(
            score_type=score_type,
            normalized_score=percentile,
            raw_value=_decimal(raw_value, precision=6),
            confidence=_decimal(confidence_value, precision=4),
            percentile=percentile,
            metadata_json={
                "model": self.SCORE_MODEL_NAME,
                "modality": modality,
                "feature_basis": feature_basis,
                "interpretation_layer": "Derived product score built on TRIBE v2 internal features.",
            },
        )

    def _compute_confidence(self, *, segment_count: int, context_density: float, modality: str) -> float:
        modality_bonus = 0.05 if modality in {"video", "audio"} else 0.0
        segment_bonus = min(0.16, max(0.0, (segment_count - 1) * 0.02))
        density_bonus = min(0.08, context_density * 0.08)
        return self._clip01(0.58 + modality_bonus + segment_bonus + density_bonus)

    def _build_visualizations(
        self,
        *,
        score_values: dict[str, float],
        segment_features: list[dict[str, Any]],
        region_activation_summary: dict[str, Any],
        modality: str,
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
                    "summary_scores": {key: round(value * 100.0, 2) for key, value in score_values.items()},
                    "note": "Timeline values are derived from internal features computed over TRIBE segment predictions.",
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
        score_values: dict[str, float],
        segment_features: list[dict[str, Any]],
    ) -> list[TimelinePointItem]:
        if not segment_features:
            return [
                TimelinePointItem(
                    timestamp_ms=0,
                    attention_score=self._to_pct(score_values["attention"]),
                    emotion_score=self._to_pct(score_values["emotion"]),
                    memory_score=self._to_pct(score_values["memory"]),
                    cognitive_load_score=self._to_pct(score_values["cognitive_load"]),
                    conversion_proxy_score=self._to_pct(score_values["conversion_proxy"]),
                    metadata_json={"segment_index": 0, "derived": True},
                )
            ]

        timeline: list[TimelinePointItem] = []
        for item in segment_features:
            engagement = float(item.get("engagement_signal", 0.0))
            peak_focus = float(item.get("peak_focus_signal", 0.0))
            consistency = float(item.get("consistency_signal", 0.0))
            temporal_change = float(item.get("temporal_change_signal", 0.0))
            balance = float(item.get("hemisphere_balance_signal", 0.0))

            attention_value = self._clip01(
                (engagement * 0.5)
                + (peak_focus * 0.32)
                + (consistency * 0.18)
            )
            emotion_value = self._clip01(
                (engagement * 0.38)
                + (temporal_change * 0.32)
                + (peak_focus * 0.14)
                + 0.12
            )
            memory_value = self._clip01(
                (consistency * 0.44)
                + (engagement * 0.26)
                + (peak_focus * 0.2)
                + (balance * 0.1)
            )
            cognitive_load_value = self._clip01(
                (temporal_change * 0.22)
                + ((1.0 - consistency) * 0.38)
                + ((1.0 - balance) * 0.16)
                + 0.24
            )
            conversion_proxy_value = self._clip01(
                (attention_value * 0.3)
                + (emotion_value * 0.16)
                + (memory_value * 0.28)
                - (cognitive_load_value * 0.12)
                + 0.1
            )

            timeline.append(
                TimelinePointItem(
                    timestamp_ms=int(item.get("start_ms", 0)),
                    attention_score=self._to_pct(attention_value),
                    emotion_score=self._to_pct(emotion_value),
                    memory_score=self._to_pct(memory_value),
                    cognitive_load_score=self._to_pct(cognitive_load_value),
                    conversion_proxy_score=self._to_pct(conversion_proxy_value),
                    metadata_json={
                        "segment_index": int(item.get("segment_index", len(timeline))),
                        "event_count": int(item.get("event_count", 0)),
                        "event_types": list(item.get("event_types", [])),
                        "derived_from": "TRIBE segment prediction summaries",
                    },
                )
            )
        return timeline

    def _build_suggestions(
        self,
        *,
        score_values: dict[str, float],
        modality: str,
        context: dict[str, Any],
        reduced_feature_vector: dict[str, Any],
        hemisphere_summary: dict[str, Any],
    ) -> list[SuggestionItem]:
        suggestions: list[SuggestionItem] = []

        if score_values["conversion_proxy"] < 0.68:
            suggestions.append(
                SuggestionItem(
                    suggestion_type=SuggestionType.CTA,
                    status=SuggestionStatus.PROPOSED,
                    title="Clarify the decision moment",
                    rationale=(
                        "Derived conversion potential trails the engagement profile. "
                        "Strengthen the primary action cue near the highest-engagement segment."
                    ),
                    proposed_change_json={
                        "action": "increase_cta_prominence",
                        "modality": modality,
                        "audience_context": context.get("audience_context", {}),
                    },
                    expected_score_lift_json={"conversion_proxy": 4.2, "attention": 1.8},
                    confidence=_decimal(0.8, precision=4),
                )
            )

        if score_values["attention"] < 0.66:
            suggestions.append(
                SuggestionItem(
                    suggestion_type=SuggestionType.FRAMING if modality == "text" else SuggestionType.PACING,
                    status=SuggestionStatus.PROPOSED,
                    title="Front-load the strongest cue",
                    rationale=(
                        "The derived engagement and peak-focus signals suggest the opening is not capturing attention quickly enough."
                    ),
                    proposed_change_json={"action": "move_key_message_earlier", "modality": modality},
                    expected_score_lift_json={"attention": 5.1, "memory": 2.1},
                    confidence=_decimal(0.76, precision=4),
                )
            )

        if score_values["memory"] < 0.64:
            suggestions.append(
                SuggestionItem(
                    suggestion_type=SuggestionType.BRANDING,
                    status=SuggestionStatus.PROPOSED,
                    title="Reinforce the brand anchor at the peak segment",
                    rationale=(
                        "Temporal consistency is moderate, which weakens downstream recall. "
                        "Repeat the brand or product anchor when the message is already landing."
                    ),
                    proposed_change_json={
                        "action": "repeat_brand_anchor",
                        "target_moment": "highest_engagement_segment",
                    },
                    expected_score_lift_json={"memory": 4.3, "conversion_proxy": 1.9},
                    confidence=_decimal(0.74, precision=4),
                )
            )

        if score_values["cognitive_load"] > 0.58:
            suggestions.append(
                SuggestionItem(
                    suggestion_type=SuggestionType.COPY if modality == "text" else SuggestionType.PACING,
                    status=SuggestionStatus.PROPOSED,
                    title="Reduce message density",
                    rationale=(
                        "Derived linguistic-load and context-density signals indicate more decoding effort than ideal."
                    ),
                    proposed_change_json={
                        "action": "simplify_message",
                        "hemisphere_balance_signal": hemisphere_summary.get("hemisphere_balance_signal"),
                    },
                    expected_score_lift_json={"cognitive_load": -6.0, "conversion_proxy": 2.2},
                    confidence=_decimal(0.82, precision=4),
                )
            )

        if score_values["emotion"] < 0.63 and modality in {"video", "audio"}:
            suggestions.append(
                SuggestionItem(
                    suggestion_type=SuggestionType.FRAMING,
                    status=SuggestionStatus.PROPOSED,
                    title="Add a stronger emotional contrast beat",
                    rationale=(
                        "Temporal dynamics are present, but the affective arc is still flatter than target."
                    ),
                    proposed_change_json={"action": "increase_emotional_contrast", "modality": modality},
                    expected_score_lift_json={"emotion": 3.2, "attention": 1.4},
                    confidence=_decimal(0.69, precision=4),
                )
            )

        if not suggestions:
            suggestions.append(
                SuggestionItem(
                    suggestion_type=SuggestionType.FRAMING,
                    status=SuggestionStatus.PROPOSED,
                    title="Test a sharper value proposition variant",
                    rationale=(
                        "The current prediction is balanced. Incremental upside is more likely to come from message framing than structural change."
                    ),
                    proposed_change_json={
                        "action": "test_value_proposition_variant",
                        "current_context_density": reduced_feature_vector.get("derived_context_density_signal"),
                    },
                    expected_score_lift_json={"emotion": 1.5, "conversion_proxy": 1.1},
                    confidence=_decimal(0.63, precision=4),
                )
            )

        suggestions.sort(
            key=lambda item: float(item.expected_score_lift_json.get("conversion_proxy", 0.0))
            + float(item.confidence or 0),
            reverse=True,
        )
        return suggestions
