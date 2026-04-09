from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from backend.application.services.analysis import AnalysisApplicationService
from backend.db.models import JobStatus
from backend.db.repositories.inference import InferenceRepository


class TestFailedAnalysisResultRead(unittest.IsolatedAsyncioTestCase):
    async def test_build_result_returns_persisted_partial_record_for_failed_job(self) -> None:
        service = AnalysisApplicationService(AsyncMock())
        created_at = datetime.now(timezone.utc)
        record = SimpleNamespace(
            created_at=created_at,
            summary_json={
                "modality": "video",
                "overall_attention_score": 0.0,
                "hook_score_first_3_seconds": 0.0,
                "sustained_engagement_score": 0.0,
                "memory_proxy_score": 0.0,
                "cognitive_load_proxy": 0.0,
                "confidence": None,
                "completeness": 82.5,
                "notes": ["TRIBE-only fallback"],
                "metadata": {"scoring_status": "failed"},
            },
            metrics_json=[],
            timeline_json=[],
            segments_json=[],
            visualizations_json={
                "visualization_mode": "frame_grid_fallback",
                "heatmap_frames": [],
                "high_attention_intervals": [],
                "low_attention_intervals": [],
            },
            recommendations_json=[],
        )
        job = SimpleNamespace(
            id=uuid4(),
            status=JobStatus.FAILED,
            analysis_result_record=record,
        )

        result = service._build_result(job)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.summary_json.metadata["scoring_status"], "failed")
        self.assertEqual(result.recommendations_json, [])


class TestMarkJobFailedPartial(unittest.IsolatedAsyncioTestCase):
    async def test_mark_job_failed_preserves_partial_result_flag(self) -> None:
        session = AsyncMock()
        repo = InferenceRepository(session)
        job = SimpleNamespace(
            status=JobStatus.RUNNING,
            error_message=None,
            completed_at=None,
            runtime_params={
                "analysis_progress": {
                    "stage": "primary_scoring_started",
                    "stage_label": "Scoring in progress.",
                    "diagnostics": {"time_to_first_result_ms": 1234},
                }
            },
        )

        await repo.mark_job_failed(job, "ReadTimeout", partial_result_available=True)

        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.error_message, "ReadTimeout")
        self.assertTrue(job.runtime_params["analysis_progress"]["is_partial"])
        self.assertIn("TRIBE", job.runtime_params["analysis_progress"]["stage_label"])
        session.flush.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
