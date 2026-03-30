from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from backend.tasks import _run_prediction_job


class _FakeSessionContext:
    def __init__(self) -> None:
        self.session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class PredictionTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_prediction_job_commits_on_success(self) -> None:
        job_id = uuid4()
        session_context = _FakeSessionContext()
        service = SimpleNamespace(
            process_prediction_job=AsyncMock(return_value=None),
            mark_job_failed=AsyncMock(),
        )

        with (
            patch("backend.tasks.AsyncSessionLocal", return_value=session_context),
            patch("backend.tasks.PredictionApplicationService", return_value=service),
        ):
            await _run_prediction_job(job_id)

        service.process_prediction_job.assert_awaited_once_with(job_id)
        service.mark_job_failed.assert_not_awaited()
        session_context.session.commit.assert_awaited_once()
        session_context.session.rollback.assert_not_awaited()

    async def test_run_prediction_job_marks_failed_after_rollback(self) -> None:
        job_id = uuid4()
        session_context = _FakeSessionContext()
        service = SimpleNamespace(
            process_prediction_job=AsyncMock(side_effect=RuntimeError("boom")),
            mark_job_failed=AsyncMock(return_value=None),
        )

        with (
            patch("backend.tasks.AsyncSessionLocal", return_value=session_context),
            patch("backend.tasks.PredictionApplicationService", return_value=service),
        ):
            with self.assertRaises(RuntimeError):
                await _run_prediction_job(job_id)

        session_context.session.rollback.assert_awaited_once()
        service.mark_job_failed.assert_awaited_once_with(job_id, "boom")
        session_context.session.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
