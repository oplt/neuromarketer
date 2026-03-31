from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from backend.application.services.analysis_evaluations import AnalysisEvaluationApplicationService
from backend.db.models import JobStatus
from backend.schemas.evaluators import EvaluationDispatchRequest, EvaluationMode, EvaluationStatus


def _build_cached_result_payload() -> dict:
    return {
        "mode": "marketing",
        "overall_verdict": "Usable cached result.",
        "summary": "Cached evaluation should remain visible if refresh fails.",
        "scores": {
            "clarity": 70,
            "engagement": 75,
            "retention": 72,
            "fit_for_purpose": 76,
            "risk": 24,
        },
        "strengths": ["Clear opening"],
        "weaknesses": ["Soft middle"],
        "risks": [],
        "recommendations": [],
        "scorecard": {
            "hook_or_opening": {"score": 78, "reason": "Opening is solid."},
            "message_clarity": {"score": 70, "reason": "Message is understandable."},
            "pacing": {"score": 68, "reason": "Middle section slows."},
            "attention_alignment": {"score": 74, "reason": "Attention mostly supports the message."},
            "domain_effectiveness": {"score": 76, "reason": "Overall marketing fit is decent."},
        },
        "model_metadata": {"provider": "ollama", "model": "gemma3:27b", "tokens_in": 10, "tokens_out": 20},
        "marketing_summary": "Solid opener with room to tighten the middle.",
        "hook_assessment": "The first three seconds are effective.",
        "value_prop_assessment": "Value is mostly clear.",
        "conversion_friction_points": ["Middle drag"],
        "brand_alignment_feedback": "Mostly on brand.",
    }


class AnalysisEvaluationApplicationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_evaluations_returns_cached_result_without_dispatch(self) -> None:
        session = AsyncMock()
        user_id = uuid4()
        job_id = uuid4()
        record = SimpleNamespace(
            id=uuid4(),
            job_id=job_id,
            user_id=user_id,
            mode="marketing",
            status="completed",
            model_provider="ollama",
            model_name="gemma3:27b",
            prompt_version="marketing_v2",
            evaluation_json=_build_cached_result_payload(),
            error_message=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        job = SimpleNamespace(
            id=job_id,
            created_by_user_id=user_id,
            status=JobStatus.SUCCEEDED,
            analysis_result_record=SimpleNamespace(),
            creative_version=SimpleNamespace(extracted_metadata={}, preprocessing_summary={}, mime_type="video/mp4"),
        )

        service = AnalysisEvaluationApplicationService(session)
        service.inference = SimpleNamespace(get_job_for_analysis_evaluation=AsyncMock(return_value=job))
        service.evaluations = SimpleNamespace(
            get_for_job_and_mode=AsyncMock(return_value=record),
            queue_evaluation=AsyncMock(),
            list_for_job=AsyncMock(return_value=[record]),
        )

        with patch("backend.tasks.dispatch_llm_evaluation_job", new=AsyncMock()) as dispatch:
            response = await service.request_evaluations(
                user_id=user_id,
                job_id=job_id,
                payload=EvaluationDispatchRequest(modes=[EvaluationMode.MARKETING], force_refresh=False),
            )

        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].status, EvaluationStatus.COMPLETED)
        service.evaluations.queue_evaluation.assert_not_awaited()
        dispatch.assert_not_awaited()

    async def test_process_evaluation_preserves_cached_result_when_refresh_fails(self) -> None:
        session = AsyncMock()
        user_id = uuid4()
        job_id = uuid4()
        record = SimpleNamespace(
            id=uuid4(),
            job_id=job_id,
            user_id=user_id,
            mode="marketing",
            status="processing",
            model_provider="ollama",
            model_name="gemma3:27b",
            prompt_version="marketing_v2",
            input_snapshot_json={
                "job_metadata": {"job_id": "job-1"},
                "summary_metrics": {"overall_attention_score": 72},
                "timeline_highlights": {"peak_attention_points": []},
            },
            evaluation_json=_build_cached_result_payload(),
            error_message=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        job = SimpleNamespace(
            id=job_id,
            created_by_user_id=user_id,
            status=JobStatus.SUCCEEDED,
            analysis_result_record=SimpleNamespace(),
            creative_version=SimpleNamespace(extracted_metadata={}, preprocessing_summary={}, mime_type="video/mp4"),
        )

        async def _mark_failed(*, record, error_message: str) -> None:
            record.status = "failed"
            record.error_message = error_message

        service = AnalysisEvaluationApplicationService(session)
        service.inference = SimpleNamespace(get_job_for_analysis_evaluation=AsyncMock(return_value=job))
        service.evaluations = SimpleNamespace(
            acquire_for_processing=AsyncMock(return_value=record),
            get_for_job_and_mode=AsyncMock(return_value=record),
            mark_completed=AsyncMock(),
            mark_failed=AsyncMock(side_effect=_mark_failed),
        )
        service._engine = SimpleNamespace(evaluate=AsyncMock(side_effect=RuntimeError("boom")))

        response = await service.process_evaluation(job_id=job_id, mode=EvaluationMode.MARKETING)

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response.status, EvaluationStatus.FAILED)
        self.assertIsNotNone(response.evaluation_json)
        self.assertEqual(response.evaluation_json.summary, "Cached evaluation should remain visible if refresh fails.")
        self.assertEqual(response.error_message, "boom")


if __name__ == "__main__":
    unittest.main()
