from __future__ import annotations

from decimal import Decimal
import unittest

from backend.db.models import SuggestionStatus, SuggestionType
from backend.services.analysis_postprocessor import AnalysisPostprocessor
from backend.services.scoring import ScoreItem, ScoringBundle, SuggestionItem, TimelinePointItem
from backend.services.tribe_runtime import TribeRuntimeOutput


class AnalysisPostprocessorTests(unittest.TestCase):
    def test_build_dashboard_payload_creates_marketer_facing_outputs(self) -> None:
        processor = AnalysisPostprocessor()
        runtime_output = TribeRuntimeOutput(
            raw_brain_response_uri=None,
            raw_brain_response_summary={"prediction_summary": {"segment_count": 3}},
            reduced_feature_vector={
                "event_row_count": 18,
                "segment_count": 3,
                "segment_features": [
                    {
                        "segment_index": 0,
                        "start_ms": 0,
                        "duration_ms": 1500,
                        "event_count": 4,
                        "engagement_signal": 0.44,
                        "peak_focus_signal": 0.62,
                        "temporal_change_signal": 0.16,
                        "consistency_signal": 0.74,
                    },
                    {
                        "segment_index": 1,
                        "start_ms": 1500,
                        "duration_ms": 1500,
                        "event_count": 8,
                        "engagement_signal": 0.81,
                        "peak_focus_signal": 0.79,
                        "temporal_change_signal": 0.21,
                        "consistency_signal": 0.72,
                    },
                    {
                        "segment_index": 2,
                        "start_ms": 3000,
                        "duration_ms": 1500,
                        "event_count": 13,
                        "engagement_signal": 0.32,
                        "peak_focus_signal": 0.41,
                        "temporal_change_signal": 0.54,
                        "consistency_signal": 0.49,
                    },
                ],
            },
            region_activation_summary={"mesh": "fsaverage5"},
            provenance_json={"provider": "Meta"},
        )
        scoring_bundle = ScoringBundle(
            scores=[
                ScoreItem(
                    score_type="attention",
                    normalized_score=Decimal("71.2"),
                    raw_value=Decimal("0.71"),
                    confidence=Decimal("0.82"),
                    percentile=Decimal("71.2"),
                    metadata_json={},
                ),
                ScoreItem(
                    score_type="memory",
                    normalized_score=Decimal("66.5"),
                    raw_value=Decimal("0.66"),
                    confidence=Decimal("0.81"),
                    percentile=Decimal("66.5"),
                    metadata_json={},
                ),
                ScoreItem(
                    score_type="cognitive_load",
                    normalized_score=Decimal("61.0"),
                    raw_value=Decimal("0.61"),
                    confidence=Decimal("0.77"),
                    percentile=Decimal("61.0"),
                    metadata_json={},
                ),
                ScoreItem(
                    score_type="conversion_proxy",
                    normalized_score=Decimal("58.4"),
                    raw_value=Decimal("0.58"),
                    confidence=Decimal("0.74"),
                    percentile=Decimal("58.4"),
                    metadata_json={},
                ),
            ],
            visualizations=[],
            timeline_points=[
                TimelinePointItem(
                    timestamp_ms=0,
                    attention_score=Decimal("54.0"),
                    emotion_score=None,
                    memory_score=Decimal("49.0"),
                    cognitive_load_score=None,
                    conversion_proxy_score=None,
                    metadata_json={},
                ),
                TimelinePointItem(
                    timestamp_ms=1500,
                    attention_score=Decimal("82.0"),
                    emotion_score=None,
                    memory_score=Decimal("74.0"),
                    cognitive_load_score=None,
                    conversion_proxy_score=None,
                    metadata_json={},
                ),
                TimelinePointItem(
                    timestamp_ms=3000,
                    attention_score=Decimal("38.0"),
                    emotion_score=None,
                    memory_score=Decimal("42.0"),
                    cognitive_load_score=None,
                    conversion_proxy_score=None,
                    metadata_json={},
                ),
            ],
            suggestions=[
                SuggestionItem(
                    suggestion_type=SuggestionType.PACING,
                    status=SuggestionStatus.PROPOSED,
                    title="Front-load the strongest cue",
                    rationale="The opening can work harder.",
                    proposed_change_json={},
                    expected_score_lift_json={"attention": 4.0},
                    confidence=Decimal("0.74"),
                )
            ],
        )

        payload = processor.build_dashboard_payload(
            runtime_output=runtime_output,
            scoring_bundle=scoring_bundle,
            modality="video",
            objective="Improve hook rate",
            source_label="launch-spot.mp4",
        )

        self.assertEqual(payload.summary_json["modality"], "video")
        self.assertIn("overall_attention_score", payload.summary_json)
        self.assertIn("confidence", payload.summary_json)
        self.assertEqual(len(payload.timeline_json), 3)
        self.assertEqual(payload.timeline_json[1]["timestamp_ms"], 1500)
        self.assertEqual(payload.segments_json[0]["label"], "Scene 01")
        self.assertTrue(payload.visualizations_json["heatmap_frames"])
        self.assertTrue(payload.visualizations_json["high_attention_intervals"])
        self.assertTrue(payload.visualizations_json["low_attention_intervals"])
        self.assertTrue(payload.recommendations_json)
        self.assertNotIn("brain", payload.visualizations_json)


if __name__ == "__main__":
    unittest.main()
