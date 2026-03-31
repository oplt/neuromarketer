from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.dependencies import require_authenticated_context
from backend.api.main import app
from backend.db.session import get_db
from backend.schemas.evaluators import (
    EvaluationListResponse,
    EvaluationMode,
    EvaluationRecordRead,
    EvaluationStatus,
)


def build_record(mode: EvaluationMode) -> EvaluationRecordRead:
    timestamp = datetime.now(timezone.utc)
    return EvaluationRecordRead(
        id=uuid4(),
        job_id=uuid4(),
        user_id=uuid4(),
        mode=mode,
        status=EvaluationStatus.COMPLETED,
        model_provider="ollama",
        model_name="gemma3:27b",
        prompt_version="marketing_v2",
        evaluation_json=None,
        error_message=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


async def _fake_db():
    yield object()


async def _fake_auth():
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        organization=SimpleNamespace(id=uuid4()),
        default_project=SimpleNamespace(id=uuid4()),
        session_token="token",
    )


class LLMEvaluationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[require_authenticated_context] = _fake_auth
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.client.close()

    def test_post_evaluate_endpoint_returns_dispatched_items(self) -> None:
        service = SimpleNamespace(
            request_evaluations=AsyncMock(
                return_value=EvaluationListResponse(items=[build_record(EvaluationMode.MARKETING)])
            )
        )

        with patch("backend.api.router.analysis.AnalysisEvaluationApplicationService", return_value=service):
            response = self.client.post(
                f"/api/v1/analysis/jobs/{uuid4()}/evaluate",
                json={"modes": ["marketing"], "force_refresh": False},
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["items"][0]["mode"], "marketing")
        service.request_evaluations.assert_awaited_once()

    def test_get_evaluations_endpoint_returns_cached_items(self) -> None:
        service = SimpleNamespace(
            list_evaluations=AsyncMock(
                return_value=EvaluationListResponse(items=[build_record(EvaluationMode.SOCIAL_MEDIA)])
            )
        )

        with patch("backend.api.router.analysis.AnalysisEvaluationApplicationService", return_value=service):
            response = self.client.get(
                f"/api/v1/analysis/jobs/{uuid4()}/evaluations",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["mode"], "social_media")
        service.list_evaluations.assert_awaited_once()

    def test_get_single_evaluation_endpoint_returns_requested_mode(self) -> None:
        service = SimpleNamespace(
            get_evaluation=AsyncMock(return_value=build_record(EvaluationMode.DEFENCE))
        )

        with patch("backend.api.router.analysis.AnalysisEvaluationApplicationService", return_value=service):
            response = self.client.get(
                f"/api/v1/analysis/jobs/{uuid4()}/evaluations/defence",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "defence")
        service.get_evaluation.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
