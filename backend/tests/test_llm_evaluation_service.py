from __future__ import annotations

import unittest

from backend.llm.evaluation_service import EvaluationRequest, EvaluationService, EvaluationServiceError
from backend.llm.llm_client import LLMClientConfig, LLMResponseFormatError, StructuredGeneration, parse_json_object
from backend.schemas.evaluators import EvaluationMode


def build_valid_result_payload(mode: EvaluationMode) -> dict:
    return {
        "mode": mode.value,
        "overall_verdict": "Strong with targeted fixes needed.",
        "summary": "The structured analysis shows a solid opening but uneven mid-segment clarity.",
        "scores": {
            "clarity": 74,
            "engagement": 76,
            "retention": 71,
            "fit_for_purpose": 78,
            "risk": 29,
        },
        "strengths": ["Clear opening", "Strong value emphasis"],
        "weaknesses": ["Midpoint dip", "Late reinforcement"],
        "risks": [
            {
                "severity": "medium",
                "label": "Midpoint drop",
                "description": "Attention dips during the central segment.",
                "timestamp_start": 8000,
                "timestamp_end": 12000,
            }
        ],
        "recommendations": [
            {
                "priority": "high",
                "action": "Tighten the middle transition.",
                "reason": "The analysis shows a clear engagement dip in the midpoint window.",
                "timestamp_start": 8000,
                "timestamp_end": 12000,
            }
        ],
        "scorecard": {
            "hook_or_opening": {"score": 82, "reason": "The opening window performs well."},
            "message_clarity": {"score": 73, "reason": "Core message is mostly understandable."},
            "pacing": {"score": 69, "reason": "The middle section slows down."},
            "attention_alignment": {"score": 75, "reason": "Strong moments mostly support the main message."},
            "domain_effectiveness": {"score": 78, "reason": "The asset is generally fit for purpose."},
        },
        "model_metadata": {
            "provider": "placeholder",
            "model": "placeholder",
            "tokens_in": 0,
            "tokens_out": 0,
        },
        "marketing_summary": "Useful marketing framing with a soft midpoint.",
        "hook_assessment": "The opening is attention-positive.",
        "value_prop_assessment": "The value proposition is reasonably clear.",
        "conversion_friction_points": ["Midpoint drag"],
        "brand_alignment_feedback": "Brand voice is mostly consistent.",
    }


class _FakeClient:
    def __init__(self, generation: StructuredGeneration | None = None, error: Exception | None = None) -> None:
        self.config = LLMClientConfig(provider="ollama", base_url="http://localhost:11434", model="test-model")
        self._generation = generation
        self._error = error

    async def generate_structured_with_repair(self, **_: object) -> StructuredGeneration:
        if self._error is not None:
            raise self._error
        assert self._generation is not None
        return self._generation


class StructuredOutputTests(unittest.TestCase):
    def test_parse_json_object_handles_markdown_fences(self) -> None:
        parsed = parse_json_object("```json\n{\"ok\": true}\n```")
        self.assertEqual(parsed, {"ok": True})

    def test_parse_json_object_rejects_non_json(self) -> None:
        with self.assertRaises(LLMResponseFormatError):
            parse_json_object("not-json")


class EvaluationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluate_normalizes_provider_metadata(self) -> None:
        generation = StructuredGeneration(
            parsed_json=build_valid_result_payload(EvaluationMode.MARKETING),
            metadata={
                "provider": "ollama",
                "model": "gemma3:27b",
                "tokens_in": 321,
                "tokens_out": 654,
                "raw_text": "{}",
            },
        )
        service = EvaluationService(llm_client=_FakeClient(generation=generation))

        response = await service.evaluate(
            EvaluationRequest(
                mode=EvaluationMode.MARKETING,
                context={
                    "job_metadata": {"job_id": "job-1"},
                    "summary_metrics": {"overall_attention_score": 72},
                    "timeline_highlights": {"peak_attention_points": []},
                },
            )
        )

        self.assertEqual(response.result.mode, EvaluationMode.MARKETING)
        self.assertEqual(response.result.model_metadata.provider, "ollama")
        self.assertEqual(response.result.model_metadata.model, "gemma3:27b")
        self.assertEqual(response.result.model_metadata.tokens_in, 321)
        self.assertEqual(response.result.model_metadata.tokens_out, 654)

    async def test_evaluate_raises_service_error_for_malformed_output(self) -> None:
        service = EvaluationService(
            llm_client=_FakeClient(error=LLMResponseFormatError("invalid json"))
        )

        with self.assertRaises(EvaluationServiceError):
            await service.evaluate(
                EvaluationRequest(
                    mode=EvaluationMode.DEFENCE,
                    context={
                        "job_metadata": {"job_id": "job-1"},
                        "summary_metrics": {"overall_attention_score": 66},
                        "timeline_highlights": {"peak_attention_points": []},
                    },
                )
            )


if __name__ == "__main__":
    unittest.main()
