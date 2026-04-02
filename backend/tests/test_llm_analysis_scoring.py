from __future__ import annotations

import asyncio

from backend.llm.analysis_scoring_service import AnalysisScoringResponse
from backend.schemas.llm_scoring import AnalysisScoringResult
from backend.services.analysis_postprocessor import AnalysisPostprocessor
from backend.services.scoring import NeuroScoringService
from backend.services.tribe_runtime import TribeRuntimeOutput


class _FakeAnalysisScoringService:
    def __init__(self, response: AnalysisScoringResponse) -> None:
        self.response = response
        self.last_context: dict | None = None

    async def score(self, context: dict) -> AnalysisScoringResponse:
        self.last_context = context
        return self.response


def _fake_scoring_response() -> AnalysisScoringResponse:
    result = AnalysisScoringResult.model_validate(
        {
            "overall_summary": "The opening holds attention and the CTA is understandable.",
            "notes": [
                "Mid-stream engagement stays stable instead of collapsing after the hook.",
                "The main friction point is message density in the closing section.",
            ],
            "scores": {
                "attention": {
                    "score": 78,
                    "confidence": 0.86,
                    "reason": "Opening and mid-stream signals keep attention relatively stable.",
                    "evidence": ["Segment 0 opens strongly.", "Segment 1 stays above the midpoint."],
                },
                "emotion": {
                    "score": 62,
                    "confidence": 0.73,
                    "reason": "The emotional arc exists but is not especially intense.",
                    "evidence": ["Temporal change is present but moderate."],
                },
                "memory": {
                    "score": 71,
                    "confidence": 0.82,
                    "reason": "Consistency and reinforcement cues support recall.",
                    "evidence": ["Consistency remains high across both segments."],
                },
                "cognitive_load": {
                    "score": 41,
                    "confidence": 0.79,
                    "reason": "The content is mostly understandable with some late density.",
                    "evidence": ["Closing segment adds more event density than the opening."],
                },
                "conversion_proxy": {
                    "score": 69,
                    "confidence": 0.76,
                    "reason": "The CTA is present and generally aligned with the strongest sections.",
                    "evidence": ["The recommendation focuses on clarifying the closing CTA."],
                },
            },
            "timeline_points": [
                {
                    "segment_index": 0,
                    "timestamp_ms": 0,
                    "attention_score": 82,
                    "emotion_score": 64,
                    "memory_score": 74,
                    "cognitive_load_score": 34,
                    "conversion_proxy_score": 70,
                    "rationale": "The opening segment captures attention quickly.",
                },
                {
                    "segment_index": 1,
                    "timestamp_ms": 4000,
                    "attention_score": 74,
                    "emotion_score": 60,
                    "memory_score": 68,
                    "cognitive_load_score": 47,
                    "conversion_proxy_score": 67,
                    "rationale": "The closing remains clear but becomes denser.",
                },
            ],
            "suggestions": [
                {
                    "suggestion_type": "cta",
                    "title": "Clarify the CTA wording in the closing segment",
                    "rationale": "The action cue is present, but making it more explicit should reduce friction.",
                    "proposed_change_json": {"action": "simplify_cta_copy"},
                    "expected_score_lift_json": {"conversion_proxy": 4.0, "cognitive_load": -3.0},
                    "confidence": 0.81,
                    "timestamp_ms": 4000,
                }
            ],
        }
    )
    return AnalysisScoringResponse(
        result=result,
        provider_id="test-route",
        provider="ollama",
        model="test-model",
        tokens_in=321,
        tokens_out=147,
        prompt_version="analysis_scoring_v2",
        telemetry={"latency_ms": 55},
    )


def _runtime_output() -> TribeRuntimeOutput:
    return TribeRuntimeOutput(
        raw_brain_response_uri=None,
        raw_brain_response_summary={},
        reduced_feature_vector={
            "feature_contract_version": "tribe_v2_business_bridge_v1",
            "segment_count": 2,
            "event_row_count": 18,
            "derived_neural_engagement_signal": 0.62,
            "derived_peak_focus_signal": 0.58,
            "derived_temporal_dynamics_signal": 0.44,
            "derived_temporal_consistency_signal": 0.67,
            "derived_linguistic_load_signal": 0.39,
            "derived_context_density_signal": 0.42,
            "derived_hemisphere_balance_signal": 0.55,
            "derived_audio_language_mix_signal": 0.31,
            "segment_features": [
                {
                    "segment_index": 0,
                    "start_ms": 0,
                    "duration_ms": 4000,
                    "event_count": 7,
                    "event_types": ["Word", "Shot"],
                    "engagement_signal": 0.72,
                    "peak_focus_signal": 0.69,
                    "consistency_signal": 0.74,
                    "temporal_change_signal": 0.33,
                    "hemisphere_balance_signal": 0.56,
                },
                {
                    "segment_index": 1,
                    "start_ms": 4000,
                    "duration_ms": 4000,
                    "event_count": 11,
                    "event_types": ["Word", "Shot", "Object"],
                    "engagement_signal": 0.64,
                    "peak_focus_signal": 0.55,
                    "consistency_signal": 0.66,
                    "temporal_change_signal": 0.41,
                    "hemisphere_balance_signal": 0.52,
                },
            ],
        },
        region_activation_summary={
            "mesh": "fsaverage5",
            "hemisphere_summary": {"hemisphere_balance_signal": 0.54},
            "top_rois": [{"roi": "V1", "activation": 0.28}],
        },
        provenance_json={},
    )


def test_neuro_scoring_service_maps_llm_scores_into_bundle() -> None:
    response = _fake_scoring_response()
    fake_service = _FakeAnalysisScoringService(response)
    scoring_service = NeuroScoringService(analysis_scoring_service=fake_service)

    bundle = asyncio.run(
        scoring_service.score(
            reduced_feature_vector=_runtime_output().reduced_feature_vector,
            region_activation_summary=_runtime_output().region_activation_summary,
            context={
                "campaign_context": {
                    "objective": "Drive signups",
                    "goal_template": "cta",
                    "channel": "social",
                    "audience_segment": "Founders",
                }
            },
            modality="video",
        )
    )

    assert fake_service.last_context is not None
    assert fake_service.last_context["tribe_feature_summary"]["segment_count"] == 2
    assert [score.score_type for score in bundle.scores] == [
        "attention",
        "emotion",
        "memory",
        "cognitive_load",
        "conversion_proxy",
    ]
    assert all(score.raw_value is None for score in bundle.scores)
    assert float(bundle.scores[0].normalized_score) == 78.0
    assert bundle.scores[0].metadata_json["reason"] == "Opening and mid-stream signals keep attention relatively stable."
    assert bundle.scores[0].metadata_json["prompt_version"] == "analysis_scoring_v2"
    assert bundle.timeline_points[0].metadata_json["rationale"] == "The opening segment captures attention quickly."
    assert bundle.suggestions[0].suggestion_type.value == "cta"
    assert bundle.suggestions[0].proposed_change_json["timestamp_ms"] == 4000
    assert bundle.notes[0] == "The opening holds attention and the CTA is understandable."


def test_analysis_postprocessor_uses_llm_outputs_without_threshold_intervals() -> None:
    response = _fake_scoring_response()
    scoring_service = NeuroScoringService(
        analysis_scoring_service=_FakeAnalysisScoringService(response)
    )
    runtime_output = _runtime_output()
    bundle = asyncio.run(
        scoring_service.score(
            reduced_feature_vector=runtime_output.reduced_feature_vector,
            region_activation_summary=runtime_output.region_activation_summary,
            context={},
            modality="video",
        )
    )

    payload = AnalysisPostprocessor().build_dashboard_payload(
        runtime_output=runtime_output,
        scoring_bundle=bundle,
        modality="video",
        objective=None,
        goal_template=None,
        channel=None,
        audience_segment=None,
        source_label="demo.mp4",
    )

    assert payload.summary_json["notes"] == bundle.notes
    assert payload.visualizations_json["high_attention_intervals"] == []
    assert payload.visualizations_json["low_attention_intervals"] == []
    assert payload.recommendations_json == [
        {
            "title": "Clarify the CTA wording in the closing segment",
            "detail": "The action cue is present, but making it more explicit should reduce friction.",
            "priority": "medium",
            "timestamp_ms": 4000,
            "confidence": 81.0,
        }
    ]
    assert any(metric["key"] == "emotion_score" and metric["value"] == 62.0 for metric in payload.metrics_json)
    assert payload.segments_json[0]["note"] == "The opening segment captures attention quickly."
