from __future__ import annotations

import unittest

from backend.db.models import VisualizationType
from backend.services.scoring import NeuroScoringService


class NeuroScoringServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_score_returns_business_artifacts_from_tribe_derived_features(self) -> None:
        service = NeuroScoringService()

        bundle = await service.score(
            reduced_feature_vector={
                "derived_neural_engagement_signal": 0.74,
                "derived_peak_focus_signal": 0.81,
                "derived_temporal_dynamics_signal": 0.35,
                "derived_temporal_consistency_signal": 0.69,
                "derived_linguistic_load_signal": 0.41,
                "derived_context_density_signal": 0.52,
                "derived_hemisphere_balance_signal": 0.92,
                "derived_audio_language_mix_signal": 0.77,
                "segment_features": [
                    {
                        "segment_index": 0,
                        "start_ms": 0,
                        "event_count": 4,
                        "event_types": ["Video", "Word"],
                        "engagement_signal": 0.72,
                        "peak_focus_signal": 0.79,
                        "consistency_signal": 0.75,
                        "temporal_change_signal": 0.18,
                        "hemisphere_balance_signal": 0.91,
                    },
                    {
                        "segment_index": 1,
                        "start_ms": 1500,
                        "event_count": 5,
                        "event_types": ["Video", "Word"],
                        "engagement_signal": 0.78,
                        "peak_focus_signal": 0.83,
                        "consistency_signal": 0.68,
                        "temporal_change_signal": 0.27,
                        "hemisphere_balance_signal": 0.93,
                    },
                ],
            },
            region_activation_summary={
                "hemisphere_summary": {
                    "left_mean_abs_activation": 0.45,
                    "right_mean_abs_activation": 0.44,
                    "hemisphere_balance_signal": 0.98,
                },
                "top_rois": [],
            },
            context={"audience_context": {"segment": "prospecting"}},
            modality="video",
        )

        self.assertEqual(len(bundle.scores), 5)
        self.assertEqual(len(bundle.timeline_points), 2)
        self.assertTrue(bundle.suggestions)
        self.assertEqual(
            {item.visualization_type for item in bundle.visualizations},
            {VisualizationType.TIMELINE, VisualizationType.BRAIN_REGION_SUMMARY},
        )
        score_types = {item.score_type for item in bundle.scores}
        self.assertEqual(
            score_types,
            {"attention", "emotion", "memory", "cognitive_load", "conversion_proxy"},
        )


if __name__ == "__main__":
    unittest.main()
