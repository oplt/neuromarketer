from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from backend.application.services.account_admin import AccountAdminApplicationService
from backend.application.services.analysis import AnalysisApplicationService
from backend.application.services.analysis_comparisons import AnalysisComparisonApplicationService
from backend.application.services.analysis_insights import AnalysisInsightsApplicationService
from backend.application.services.analysis_job_processor import PERSISTED_PROGRESS_STAGES
from backend.core.exceptions import ConflictAppError
from backend.db.models import UploadStatus
from backend.db.repositories.account_admin import ControlCenterStats


class TestComparisonCandidateOrder(unittest.IsolatedAsyncioTestCase):
    async def test_load_candidates_preserves_selected_order(self) -> None:
        session = AsyncMock()
        service = AnalysisComparisonApplicationService(session)
        user_id = uuid4()
        project_id = uuid4()
        job_1_id = uuid4()
        job_2_id = uuid4()
        creative_id = uuid4()
        job_one = SimpleNamespace(
            id=job_1_id,
            project_id=project_id,
            created_by_user_id=user_id,
            creative_id=creative_id,
            creative_version_id=uuid4(),
            runtime_params={"analysis_surface": "analysis_dashboard", "asset_id": str(uuid4())},
            request_payload={},
            analysis_result_record=SimpleNamespace(created_at=None),
        )
        job_two = SimpleNamespace(
            id=job_2_id,
            project_id=project_id,
            created_by_user_id=user_id,
            creative_id=creative_id,
            creative_version_id=uuid4(),
            runtime_params={"analysis_surface": "analysis_dashboard", "asset_id": str(uuid4())},
            request_payload={},
            analysis_result_record=SimpleNamespace(created_at=None),
        )
        service.predictions.inference.list_analysis_jobs_by_ids = AsyncMock(
            return_value=[job_two, job_one]
        )
        service.analysis.uploads.get_analysis_artifacts_by_ids = AsyncMock(return_value={})
        service.analysis._build_result = lambda _: SimpleNamespace()
        service.analysis._build_job_read = lambda job: SimpleNamespace(id=job.id, objective=None)
        loaded = await service._load_candidates(
            user_id=user_id,
            project_id=project_id,
            analysis_job_ids=[job_1_id, job_2_id],
        )
        self.assertEqual([item.analysis_job_id for item in loaded], [job_1_id, job_2_id])


class TestBenchmarkFallbackOrder(unittest.IsolatedAsyncioTestCase):
    async def test_build_benchmark_cohort_uses_expected_fallback_sequence(self) -> None:
        session = AsyncMock()
        service = AnalysisInsightsApplicationService(session)
        project_id = uuid4()
        calls: list[tuple[str | None, str | None, str | None]] = []

        async def _query(**kwargs):
            calls.append((kwargs["media_type"], kwargs["goal_template"], kwargs["channel"]))
            if kwargs["media_type"] and kwargs["goal_template"] and kwargs["channel"]:
                return [SimpleNamespace(analysis_result_record=object())] * 2
            if kwargs["media_type"] and kwargs["goal_template"] and kwargs["channel"] is None:
                return [SimpleNamespace(analysis_result_record=object())] * 5
            return []

        service.inference.query_analysis_benchmark_candidates = _query
        job = SimpleNamespace(
            project_id=project_id,
            runtime_params={"media_type": "video"},
            request_payload={
                "campaign_context": {"goal_template": "awareness", "channel": "tiktok"}
            },
        )
        cohort, _, fallback_level = await service._build_benchmark_cohort(job)
        self.assertEqual(len(cohort), 5)
        self.assertEqual(fallback_level, "goal_template")
        self.assertEqual(
            calls[:2],
            [("video", "awareness", "tiktok"), ("video", "awareness", None)],
        )


class TestControlCenterStatsAggregation(unittest.IsolatedAsyncioTestCase):
    async def test_build_stats_uses_aggregate_repository_counts(self) -> None:
        session = AsyncMock()
        service = AccountAdminApplicationService(session)
        service.repo.get_control_center_stats = AsyncMock(
            return_value=ControlCenterStats(3, 4, 5, 6, 7)
        )
        result = await service._build_stats(organization_id=uuid4())
        self.assertEqual(result.member_count, 3)
        self.assertEqual(result.project_count, 4)
        self.assertEqual(result.active_api_key_count, 5)
        self.assertEqual(result.active_webhook_count, 6)
        self.assertEqual(result.completed_analysis_count, 7)


class TestDeferredAssetPromotion(unittest.IsolatedAsyncioTestCase):
    async def test_finalize_upload_can_defer_text_promotion(self) -> None:
        session = AsyncMock()
        service = AnalysisApplicationService(session)
        upload_session_id = uuid4()
        artifact_id = uuid4()
        user_id = uuid4()
        upload_session = SimpleNamespace(
            id=upload_session_id,
            creative_version_id=None,
            created_at=None,
            upload_token="token",
            status=SimpleNamespace(value="stored"),
        )
        asset = SimpleNamespace(
            id=artifact_id,
            creative_id=uuid4(),
            creative_version_id=None,
            metadata_json={},
            bucket_name="bucket",
            storage_key="key",
            storage_uri="s3://bucket/key",
            original_filename="doc.pdf",
            mime_type="application/pdf",
            file_size_bytes=5_000_000,
            sha256=None,
            upload_status=SimpleNamespace(value="stored"),
            created_at=None,
        )
        preprocess_result = SimpleNamespace(
            modality="text",
            preprocessing_summary={},
            extracted_metadata={},
        )
        service.uploads.mark_artifact_stored = AsyncMock()
        service.uploads.mark_stored = AsyncMock()
        service._build_upload_session_read = lambda _: SimpleNamespace()
        service._build_asset_read = lambda _: SimpleNamespace()
        service._extract_asset_text = AsyncMock(side_effect=AssertionError("must not extract sync"))
        import backend.tasks as tasks_module

        original_dispatch = tasks_module.dispatch_analysis_asset_promotion

        async def _fake_dispatch(**kwargs):
            return "in_process"

        tasks_module.dispatch_analysis_asset_promotion = _fake_dispatch
        try:
            await service._finalize_uploaded_asset(
                user_id=user_id,
                upload_session=upload_session,
                asset=asset,
                resolved_mime_type=asset.mime_type,
                resolved_file_size_bytes=asset.file_size_bytes,
                sha256=None,
                preprocess_result=preprocess_result,
                upload_etag=None,
                upload_source="backend_proxy",
            )
        finally:
            tasks_module.dispatch_analysis_asset_promotion = original_dispatch
        service.uploads.mark_stored.assert_awaited_once()


class TestAnalysisJobReadiness(unittest.IsolatedAsyncioTestCase):
    async def test_create_analysis_job_requires_creative_version(self) -> None:
        session = AsyncMock()
        service = AnalysisApplicationService(session)
        user_id = uuid4()
        project_id = uuid4()
        service.uploads.get_stored_artifact = AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(),
                created_by_user_id=user_id,
                project_id=project_id,
                upload_status=UploadStatus.STORED,
                creative_id=uuid4(),
                creative_version_id=None,
            )
        )
        with self.assertRaises(ConflictAppError):
            await service.create_analysis_job(
                user_id=user_id,
                asset_id=uuid4(),
                project_id=project_id,
                objective=None,
                goal_template=None,
                channel=None,
                audience_segment=None,
            )


class TestPersistedProgressStages(unittest.TestCase):
    def test_expected_progress_stages_are_persisted(self) -> None:
        self.assertIn("worker_started", PERSISTED_PROGRESS_STAGES)
        self.assertIn("scene_extraction_ready", PERSISTED_PROGRESS_STAGES)
        self.assertIn("primary_scoring_ready", PERSISTED_PROGRESS_STAGES)
        self.assertIn("recommendations_ready", PERSISTED_PROGRESS_STAGES)
        self.assertIn("completed", PERSISTED_PROGRESS_STAGES)


if __name__ == "__main__":
    unittest.main()
