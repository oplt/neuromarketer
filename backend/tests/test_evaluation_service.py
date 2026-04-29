from backend.llm.evaluation_service import EvaluationService
from backend.schemas.evaluators import EvaluationMode, EvaluationResult


def test_evaluation_payload_normalization_accepts_mode_specific_body() -> None:
    service = EvaluationService(router=None)  # type: ignore[arg-type]

    payload = service._normalize_generation_payload(
        raw_payload={
            "educational_summary": "The lesson is understandable, but the midpoint is dense.",
            "comprehension_risks": ["The midpoint introduces too many ideas at once."],
            "pacing_feedback": "Add a recap beat before the dense section.",
            "recommendations": ["Add a short checkpoint question."],
        },
        mode=EvaluationMode.EDUCATIONAL,
        metadata={
            "provider": "test-provider",
            "model": "test-model",
            "tokens_in": 120,
            "tokens_out": 80,
        },
    )

    result = EvaluationResult.model_validate(payload)

    assert result.mode == EvaluationMode.EDUCATIONAL
    assert result.educational_summary == "The lesson is understandable, but the midpoint is dense."
    assert result.scores.clarity == 50
    assert result.scorecard.message_clarity.score == 50
    assert result.model_metadata.provider == "test-provider"
    assert result.recommendations[0].action == "Add a short checkpoint question."
