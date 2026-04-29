from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from backend.application.services.analysis import AnalysisApplicationService
from backend.application.services.analysis_job_processor import AnalysisJobProcessor
from backend.core.exceptions import NotFoundAppError
from backend.db.models import JobStatus
from backend.db.repositories.inference import InferenceRepository


class TestFailedAnalysisResultRead(unittest.IsolatedAsyncioTestCase):
    async def test_build_result_returns_persisted_partial_record_for_failed_job(self) -> None:
        service = AnalysisApplicationService(AsyncMock())
        created_at = datetime.now(UTC)
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


class TestPartialProgressPersistence(unittest.IsolatedAsyncioTestCase):
    async def test_store_progress_persists_partial_snapshot_for_refresh_restore(self) -> None:
        session = AsyncMock()
        processor = AnalysisJobProcessor(session)
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            runtime_params={},
        )
        snapshot = {
            "job_id": str(job_id),
            "summary_json": {
                "modality": "video",
                "overall_attention_score": 38.4,
                "hook_score_first_3_seconds": 41.2,
                "sustained_engagement_score": 35.5,
                "memory_proxy_score": 33.7,
                "cognitive_load_proxy": 49.1,
                "confidence": 74.0,
                "completeness": 61.0,
                "notes": ["Primary scoring ready."],
                "metadata": {},
            },
            "metrics_json": [],
            "timeline_json": [],
            "segments_json": [],
            "visualizations_json": {
                "visualization_mode": "frame_grid_fallback",
                "heatmap_frames": [],
                "high_attention_intervals": [],
                "low_attention_intervals": [],
            },
            "recommendations_json": [],
            "created_at": datetime.now(UTC).isoformat(),
        }

        await processor._store_progress(
            job=job,
            stage="primary_scoring_ready",
            stage_label="Primary scoring complete.",
            partial_result=snapshot,
            is_partial=True,
            persist=True,
        )

        self.assertEqual(job.runtime_params["analysis_progress"]["stage"], "primary_scoring_ready")
        self.assertEqual(job.runtime_params["analysis_partial_result"]["job_id"], str(job_id))
        session.flush.assert_awaited_once()

    async def test_store_progress_clears_partial_snapshot_when_completed(self) -> None:
        session = AsyncMock()
        processor = AnalysisJobProcessor(session)
        job = SimpleNamespace(
            id=uuid4(),
            runtime_params={"analysis_partial_result": {"job_id": str(uuid4())}},
        )

        await processor._store_progress(
            job=job,
            stage="completed",
            stage_label="Done.",
            is_partial=False,
            persist=True,
        )

        self.assertNotIn("analysis_partial_result", job.runtime_params)


class TestAnalysisProcessorTransactionBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_process_commits_after_inference_acquire_before_long_work(self) -> None:
        session = AsyncMock()
        processor = AnalysisJobProcessor(session)
        job = SimpleNamespace(
            id=uuid4(),
            project_id=uuid4(),
            creative_id=uuid4(),
            creative_version_id=uuid4(),
            started_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            request_payload={},
            runtime_params={},
        )
        processor.inference = SimpleNamespace(acquire_job=AsyncMock(return_value=job))
        processor.creatives = SimpleNamespace(get_creative_version=AsyncMock(return_value=None))

        with self.assertRaises(NotFoundAppError):
            await processor.process(job.id)

        session.commit.assert_awaited_once()

    async def test_process_scoring_commits_after_acquire_before_long_scoring(self) -> None:
        session = AsyncMock()
        processor = AnalysisJobProcessor(session)
        job = SimpleNamespace(
            id=uuid4(),
            project_id=uuid4(),
            creative_id=uuid4(),
            creative_version_id=uuid4(),
            prediction=SimpleNamespace(id=uuid4()),
            started_at=datetime.now(UTC),
            request_payload={},
            runtime_params={},
        )
        processor.inference = SimpleNamespace(acquire_scoring_job=AsyncMock(return_value=job))
        processor.creatives = SimpleNamespace(get_creative_version=AsyncMock(return_value=None))

        with self.assertRaises(NotFoundAppError):
            await processor.process_scoring(job.id)

        session.commit.assert_awaited_once()

    async def test_process_scoring_commits_before_long_scoring_path(self) -> None:
        """pre-scoring commit ends idle-in-transaction during LLM scoring."""
        session = AsyncMock()
        processor = AnalysisJobProcessor(session)
        job_id = uuid4()
        creative_version = SimpleNamespace(
            id=uuid4(),
            preprocessing_summary={"modality": "video"},
            mime_type="video/mp4",
            raw_text=None,
            source_uri="s3://x",
        )
        prediction = SimpleNamespace(
            raw_brain_response_uri=None,
            raw_brain_response_summary={},
            reduced_feature_vector={},
            region_activation_summary={},
            provenance_json={},
        )
        job = SimpleNamespace(
            id=job_id,
            project_id=uuid4(),
            creative_id=uuid4(),
            creative_version_id=creative_version.id,
            started_at=datetime.now(UTC),
            request_payload={},
            runtime_params={"analysis_progress": {"diagnostics": {}}},
            prediction=prediction,
        )
        processor.inference = SimpleNamespace(
            acquire_scoring_job=AsyncMock(return_value=job),
        )
        processor.creatives = SimpleNamespace(
            get_creative_version=AsyncMock(return_value=creative_version),
        )
        processor.scoring.score = AsyncMock(side_effect=RuntimeError("expected stop"))

        with self.assertRaises(RuntimeError):
            await processor.process_scoring(job_id)

        self.assertGreaterEqual(session.commit.await_count, 2)


class TestPartialRestoreWithoutFinalRecord(unittest.IsolatedAsyncioTestCase):
    async def test_build_result_restores_persisted_partial_snapshot(self) -> None:
        service = AnalysisApplicationService(AsyncMock())
        job_id = uuid4()
        snapshot = {
            "job_id": str(job_id),
            "summary_json": {
                "modality": "video",
                "overall_attention_score": 21.3,
                "hook_score_first_3_seconds": 25.6,
                "sustained_engagement_score": 22.1,
                "memory_proxy_score": 20.2,
                "cognitive_load_proxy": 51.8,
                "confidence": 67.0,
                "completeness": 54.0,
                "notes": ["Scene extraction ready."],
                "metadata": {},
            },
            "metrics_json": [],
            "timeline_json": [],
            "segments_json": [],
            "visualizations_json": {
                "visualization_mode": "frame_grid_fallback",
                "heatmap_frames": [],
                "high_attention_intervals": [],
                "low_attention_intervals": [],
            },
            "recommendations_json": [],
            "created_at": datetime.now(UTC).isoformat(),
        }
        job = SimpleNamespace(
            id=job_id,
            created_at=datetime.now(UTC),
            analysis_result_record=None,
            runtime_params={"analysis_partial_result": snapshot},
        )

        result = service._build_result(job)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(str(result.job_id), str(job_id))
        self.assertEqual(result.summary_json.modality, "video")
        self.assertEqual(result.summary_json.notes[0], "Scene extraction ready.")


if __name__ == "__main__":
    unittest.main()
