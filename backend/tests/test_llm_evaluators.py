from __future__ import annotations

import unittest

from backend.llm.llm_evaluators.registry import get_evaluator
from backend.schemas.evaluators import EvaluationMode


class EvaluatorRegistryTests(unittest.TestCase):
    def test_registry_returns_expected_evaluator_types(self) -> None:
        self.assertEqual(get_evaluator(EvaluationMode.EDUCATIONAL).__class__.__name__, "EducationalEvaluator")
        self.assertEqual(get_evaluator(EvaluationMode.DEFENCE).__class__.__name__, "DefenceEvaluator")
        self.assertEqual(get_evaluator(EvaluationMode.MARKETING).__class__.__name__, "MarketingEvaluator")
        self.assertEqual(get_evaluator(EvaluationMode.SOCIAL_MEDIA).__class__.__name__, "SocialMediaEvaluator")

    def test_prompt_building_uses_domain_specific_contracts(self) -> None:
        expected_markers = {
            EvaluationMode.EDUCATIONAL: "educational_summary",
            EvaluationMode.DEFENCE: "operational_clarity_assessment",
            EvaluationMode.MARKETING: "value_prop_assessment",
            EvaluationMode.SOCIAL_MEDIA: "scroll_stop_assessment",
        }
        context = {
            "job_metadata": {"job_id": "job-1"},
            "summary_metrics": {"overall_attention_score": 72},
            "timeline_highlights": {"peak_attention_points": []},
        }

        for mode, marker in expected_markers.items():
            with self.subTest(mode=mode.value):
                evaluator = get_evaluator(mode)
                prompt = evaluator.build_prompt(context)
                self.assertEqual(prompt["mode"], mode.value)
                self.assertEqual(len(prompt["messages"]), 4)
                self.assertIn(marker, prompt["messages"][1]["content"])
                self.assertIn("Structured analysis context", prompt["messages"][3]["content"])


if __name__ == "__main__":
    unittest.main()
