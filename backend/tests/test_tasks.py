from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from backend.schemas.evaluators import EvaluationMode
from backend.tasks import (
    _run_llm_evaluation_job,
    _run_prediction_job,
    _schedule_llm_evaluation_job_in_process,
    _schedule_prediction_job_in_process,
    dispatch_llm_evaluation_job,
    dispatch_prediction_job,
)


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

    async def test_dispatch_prediction_job_uses_in_process_when_workers_unavailable(self) -> None:
        job_id = uuid4()

        with (
            patch("backend.tasks._has_active_workers", return_value=False),
            patch("backend.tasks._schedule_prediction_job_in_process") as schedule,
            patch("backend.tasks.process_prediction_job_task.delay") as delay,
        ):
            mode = await dispatch_prediction_job(job_id)

        self.assertEqual(mode, "in_process")
        schedule.assert_called_once_with(job_id)
        delay.assert_not_called()

    async def test_dispatch_prediction_job_uses_celery_when_worker_available(self) -> None:
        job_id = uuid4()

        with (
            patch("backend.tasks._has_active_workers", return_value=True),
            patch("backend.tasks._schedule_prediction_job_in_process") as schedule,
            patch("backend.tasks.process_prediction_job_task.delay") as delay,
        ):
            mode = await dispatch_prediction_job(job_id)

        self.assertEqual(mode, "celery")
        delay.assert_called_once_with(str(job_id))
        schedule.assert_not_called()

    async def test_dispatch_prediction_job_falls_back_when_delay_raises(self) -> None:
        job_id = uuid4()

        with (
            patch("backend.tasks._has_active_workers", return_value=True),
            patch("backend.tasks._schedule_prediction_job_in_process") as schedule,
            patch("backend.tasks.process_prediction_job_task.delay", side_effect=RuntimeError("boom")),
        ):
            mode = await dispatch_prediction_job(job_id)

        self.assertEqual(mode, "in_process")
        schedule.assert_called_once_with(job_id)

    async def test_schedule_prediction_job_in_process_uses_current_loop(self) -> None:
        job_id = uuid4()
        created_task = Mock()
        loop = Mock()

        def _capture_task(coro, *, name=None):
            coro.close()
            return created_task

        loop.create_task.side_effect = _capture_task

        with (
            patch("backend.tasks.asyncio.get_running_loop", return_value=loop),
            patch("backend.tasks._in_process_tasks", set()),
        ):
            _schedule_prediction_job_in_process(job_id)

        loop.create_task.assert_called_once()
        created_task.add_done_callback.assert_called_once()

    async def test_run_llm_evaluation_job_marks_failed_after_rollback(self) -> None:
        job_id = uuid4()
        session_context = _FakeSessionContext()
        service = SimpleNamespace(
            process_evaluation=AsyncMock(side_effect=RuntimeError("boom")),
            evaluations=SimpleNamespace(
                get_for_job_and_mode=AsyncMock(return_value=SimpleNamespace()),
                mark_failed=AsyncMock(return_value=None),
            ),
        )

        with (
            patch("backend.tasks.AsyncSessionLocal", return_value=session_context),
            patch("backend.tasks.AnalysisEvaluationApplicationService", return_value=service),
        ):
            with self.assertRaises(RuntimeError):
                await _run_llm_evaluation_job(job_id, EvaluationMode.MARKETING)

        session_context.session.rollback.assert_awaited_once()
        service.process_evaluation.assert_awaited_once_with(job_id=job_id, mode=EvaluationMode.MARKETING)
        service.evaluations.mark_failed.assert_awaited_once()
        session_context.session.commit.assert_awaited_once()

    async def test_dispatch_llm_evaluation_uses_in_process_when_workers_unavailable(self) -> None:
        job_id = uuid4()

        with (
            patch("backend.tasks._has_active_workers", return_value=False),
            patch("backend.tasks._schedule_llm_evaluation_job_in_process") as schedule,
            patch("backend.tasks.process_llm_evaluation_task.delay") as delay,
        ):
            mode = await dispatch_llm_evaluation_job(job_id, EvaluationMode.DEFENCE)

        self.assertEqual(mode, "in_process")
        schedule.assert_called_once_with(job_id, EvaluationMode.DEFENCE)
        delay.assert_not_called()

    async def test_dispatch_llm_evaluation_uses_celery_when_worker_available(self) -> None:
        job_id = uuid4()

        with (
            patch("backend.tasks._has_active_workers", return_value=True),
            patch("backend.tasks._schedule_llm_evaluation_job_in_process") as schedule,
            patch("backend.tasks.process_llm_evaluation_task.delay") as delay,
        ):
            mode = await dispatch_llm_evaluation_job(job_id, EvaluationMode.SOCIAL_MEDIA)

        self.assertEqual(mode, "celery")
        delay.assert_called_once_with(str(job_id), "social_media")
        schedule.assert_not_called()

    async def test_schedule_llm_evaluation_job_in_process_uses_current_loop(self) -> None:
        job_id = uuid4()
        created_task = Mock()
        loop = Mock()

        def _capture_task(coro, *, name=None):
            coro.close()
            return created_task

        loop.create_task.side_effect = _capture_task

        with (
            patch("backend.tasks.asyncio.get_running_loop", return_value=loop),
            patch("backend.tasks._in_process_llm_tasks", set()),
        ):
            _schedule_llm_evaluation_job_in_process(job_id, EvaluationMode.EDUCATIONAL)

        loop.create_task.assert_called_once()
        created_task.add_done_callback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
