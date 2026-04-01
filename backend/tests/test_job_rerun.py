"""Tests for the job rerun / reset logic in InferenceRepository and PredictionApplicationService."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.db.models import JobStatus


class _FakeJob:
    def __init__(self, status: JobStatus):
        self.id = uuid4()
        self.status = status
        self.error_message = "previous error"
        self.started_at = datetime.now(timezone.utc)
        self.completed_at = datetime.now(timezone.utc)
        self.created_by_user_id = None


class TestResetJobForRerun(unittest.IsolatedAsyncioTestCase):
    async def test_reset_sets_queued_status(self):
        from backend.db.repositories.inference import InferenceRepository

        session = AsyncMock()
        repo = InferenceRepository(session)
        job = _FakeJob(JobStatus.FAILED)
        await repo.reset_job_for_rerun(job)

        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertIsNone(job.error_message)
        self.assertIsNone(job.started_at)
        self.assertIsNone(job.completed_at)
        session.flush.assert_awaited_once()

    async def test_reset_preserves_other_fields(self):
        from backend.db.repositories.inference import InferenceRepository

        session = AsyncMock()
        repo = InferenceRepository(session)
        job = _FakeJob(JobStatus.CANCELED)
        original_id = job.id
        await repo.reset_job_for_rerun(job)

        self.assertEqual(job.id, original_id)
        self.assertEqual(job.status, JobStatus.QUEUED)


class TestPredictionServiceRerun(unittest.IsolatedAsyncioTestCase):
    async def test_rerun_raises_for_running_job(self):
        from backend.application.services.predictions import PredictionApplicationService
        from backend.core.exceptions import ConflictAppError

        session = AsyncMock()
        svc = PredictionApplicationService(session)
        job = _FakeJob(JobStatus.RUNNING)
        job.created_by_user_id = None

        with patch.object(svc.inference, "get_job_with_prediction", return_value=job):
            with self.assertRaises(ConflictAppError):
                await svc.rerun_job(job_id=job.id, user_id=uuid4())

    async def test_rerun_raises_for_succeeded_job(self):
        from backend.application.services.predictions import PredictionApplicationService
        from backend.core.exceptions import ConflictAppError

        session = AsyncMock()
        svc = PredictionApplicationService(session)
        job = _FakeJob(JobStatus.SUCCEEDED)

        with patch.object(svc.inference, "get_job_with_prediction", return_value=job):
            with self.assertRaises(ConflictAppError):
                await svc.rerun_job(job_id=job.id, user_id=uuid4())

    async def test_rerun_succeeds_for_failed_job(self):
        from backend.application.services.predictions import PredictionApplicationService

        session = AsyncMock()
        svc = PredictionApplicationService(session)
        job = _FakeJob(JobStatus.FAILED)
        reset_job = _FakeJob(JobStatus.QUEUED)

        with patch.object(svc.inference, "get_job_with_prediction", side_effect=[job, reset_job]):
            with patch.object(svc.inference, "reset_job_for_rerun", new_callable=AsyncMock) as mock_reset:
                result = await svc.rerun_job(job_id=job.id, user_id=uuid4())
                mock_reset.assert_awaited_once_with(job)
                self.assertEqual(result.status, JobStatus.QUEUED)

    async def test_rerun_raises_not_found_for_missing_job(self):
        from backend.application.services.predictions import PredictionApplicationService
        from backend.core.exceptions import NotFoundAppError

        session = AsyncMock()
        svc = PredictionApplicationService(session)

        with patch.object(svc.inference, "get_job_with_prediction", return_value=None):
            with self.assertRaises(NotFoundAppError):
                await svc.rerun_job(job_id=uuid4(), user_id=uuid4())


if __name__ == "__main__":
    unittest.main()
