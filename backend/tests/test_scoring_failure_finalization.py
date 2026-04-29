"""Single-transaction guarantees for scoring failure finalization.

Pre-fix, ``_run_prediction_scoring_job`` committed twice on the failure
path: first to persist the TRIBE-only partial result, then to mark the
job ``FAILED``. If the second commit failed, the database was left with
a visible partial result row but a non-failed job status.

These tests pin the new behaviour:

1. ``_finalize_failed_scoring_job`` flushes both writes through the
   same session and never commits — the caller commits exactly once.
2. A failure inside the partial-result preserve step does NOT prevent
   the job from being marked failed; the SAVEPOINT isolates it.
3. When no prediction exists, only ``mark_job_failed`` runs and
   ``partial_result_available`` stays ``False``.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend import tasks
from backend.db.models import JobStatus


class _FakeSavepoint:
    """Minimal async ctx mgr for ``AsyncSession.begin_nested``.

    Records that it was entered/exited so tests can verify that the
    preserve step ran inside a SAVEPOINT. ``raise_on_exit`` simulates
    a SAVEPOINT rollback by swallowing exceptions like SQLAlchemy
    does for ``begin_nested``.
    """

    def __init__(self, *, swallow: bool = False) -> None:
        self.entered = False
        self.exited = False
        self.exit_exc_type = None
        self._swallow = swallow

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        self.exit_exc_type = exc_type
        return self._swallow and exc_type is not None


def _make_session_with_savepoint(swallow_savepoint_errors: bool = False):
    session = AsyncMock()
    savepoint = _FakeSavepoint(swallow=swallow_savepoint_errors)
    session.begin_nested = MagicMock(return_value=savepoint)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session, savepoint


class TestFinalizeFailedScoringJobSingleTransaction(unittest.IsolatedAsyncioTestCase):
    async def test_preserves_partial_and_marks_failed_without_committing(self) -> None:
        session, savepoint = _make_session_with_savepoint()
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.RUNNING,
            prediction=SimpleNamespace(),
            creative_version_id=uuid4(),
            request_payload={"campaign_context": {}},
            runtime_params={},
        )

        repo = MagicMock()
        repo.get_job_with_prediction = AsyncMock(return_value=job)
        repo.mark_job_failed = AsyncMock()

        with patch.object(tasks, "InferenceRepository", return_value=repo), patch.object(
            tasks,
            "_preserve_partial_scoring_result",
            new_callable=AsyncMock,
            return_value=True,
        ) as preserve_mock:
            await tasks._finalize_failed_scoring_job(
                session, job_id=job_id, error_message="LLM 5xx"
            )

        preserve_mock.assert_awaited_once()
        repo.mark_job_failed.assert_awaited_once_with(
            job, "LLM 5xx", partial_result_available=True
        )
        self.assertTrue(savepoint.entered)
        self.assertTrue(savepoint.exited)
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    async def test_savepoint_isolates_preserve_failure_but_still_marks_failed(self) -> None:
        session, savepoint = _make_session_with_savepoint(swallow_savepoint_errors=True)
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.RUNNING,
            prediction=SimpleNamespace(),
            creative_version_id=uuid4(),
            request_payload={},
            runtime_params={},
        )

        repo = MagicMock()
        repo.get_job_with_prediction = AsyncMock(return_value=job)
        repo.mark_job_failed = AsyncMock()

        with patch.object(tasks, "InferenceRepository", return_value=repo), patch.object(
            tasks,
            "_preserve_partial_scoring_result",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB statement timeout while writing fallback"),
        ):
            await tasks._finalize_failed_scoring_job(
                session, job_id=job_id, error_message="LLM 5xx"
            )

        repo.mark_job_failed.assert_awaited_once_with(
            job, "LLM 5xx", partial_result_available=False
        )
        self.assertTrue(savepoint.entered)
        self.assertEqual(savepoint.exit_exc_type, RuntimeError)
        session.commit.assert_not_called()

    async def test_skips_preserve_when_no_prediction_exists(self) -> None:
        session, savepoint = _make_session_with_savepoint()
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.RUNNING,
            prediction=None,
            creative_version_id=uuid4(),
            request_payload={},
            runtime_params={},
        )

        repo = MagicMock()
        repo.get_job_with_prediction = AsyncMock(return_value=job)
        repo.mark_job_failed = AsyncMock()

        with patch.object(tasks, "InferenceRepository", return_value=repo), patch.object(
            tasks,
            "_preserve_partial_scoring_result",
            new_callable=AsyncMock,
        ) as preserve_mock:
            await tasks._finalize_failed_scoring_job(
                session, job_id=job_id, error_message="LLM 5xx"
            )

        preserve_mock.assert_not_called()
        repo.mark_job_failed.assert_awaited_once_with(
            job, "LLM 5xx", partial_result_available=False
        )
        self.assertFalse(savepoint.entered)
        session.commit.assert_not_called()

    async def test_does_not_remark_already_failed_job(self) -> None:
        session, _ = _make_session_with_savepoint()
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.FAILED,
            prediction=None,
            creative_version_id=uuid4(),
            request_payload={},
            runtime_params={},
        )

        repo = MagicMock()
        repo.get_job_with_prediction = AsyncMock(return_value=job)
        repo.mark_job_failed = AsyncMock()

        with patch.object(tasks, "InferenceRepository", return_value=repo):
            await tasks._finalize_failed_scoring_job(
                session, job_id=job_id, error_message="LLM 5xx"
            )

        repo.mark_job_failed.assert_not_called()
        session.commit.assert_not_called()

    async def test_returns_silently_when_job_not_found(self) -> None:
        session, _ = _make_session_with_savepoint()
        repo = MagicMock()
        repo.get_job_with_prediction = AsyncMock(return_value=None)
        repo.mark_job_failed = AsyncMock()

        with patch.object(tasks, "InferenceRepository", return_value=repo):
            await tasks._finalize_failed_scoring_job(
                session, job_id=uuid4(), error_message="LLM 5xx"
            )

        repo.mark_job_failed.assert_not_called()
        session.commit.assert_not_called()


class TestRunPredictionScoringJobCommitCount(unittest.IsolatedAsyncioTestCase):
    async def test_failure_path_commits_exactly_once(self) -> None:
        """The whole failure-finalization path must produce exactly one commit."""

        session = AsyncMock()
        # ``_failure_recovery_session`` will yield this same session
        # because ``safe_rollback`` returns True for it.
        session.commit = AsyncMock()

        sessionmaker_cm = AsyncMock()
        sessionmaker_cm.__aenter__.return_value = session
        sessionmaker_cm.__aexit__.return_value = False

        finalize_mock = AsyncMock()

        prediction_service = MagicMock()
        prediction_service.process_prediction_scoring_job = AsyncMock(
            side_effect=RuntimeError("LLM 5xx")
        )

        with patch.object(
            tasks, "AsyncSessionLocal", return_value=sessionmaker_cm
        ), patch.object(
            tasks, "PredictionApplicationService", return_value=prediction_service
        ), patch.object(
            tasks, "safe_rollback", new_callable=AsyncMock, return_value=True
        ), patch.object(
            tasks, "_finalize_failed_scoring_job", finalize_mock
        ), patch.object(
            tasks, "publish_analysis_job_event", new_callable=AsyncMock
        ), self.assertRaises(RuntimeError):
            await tasks._run_prediction_scoring_job(uuid4())

        finalize_mock.assert_awaited_once()
        # Exactly one commit on the failure path: the success-path
        # commit never runs because the inner await raised.
        self.assertEqual(session.commit.await_count, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
