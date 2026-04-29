"""Denormalization contract for ``InferenceJob`` filter columns.

The analysis dashboard list and the benchmark cohort query used to
filter via ``request_payload['campaign_context'][...].astext``. That
hits no btree index (the previous expression indexes were syntactically
non-equivalent to the SQLAlchemy-rendered path) and degrades fast as
job volume grows.

These tests pin the new contract:

1. ``create_job`` lifts ``goal_template``, ``channel`` and
   ``audience_segment`` from the JSONB payload onto the indexed
   columns at write time, including trim / truncate semantics.
2. ``list_analysis_jobs_for_user`` and
   ``query_analysis_benchmark_candidates`` filter on those columns
   (so the planner can use the new btree indexes) instead of on JSONB
   paths.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.db.models import InferenceJob, JobStatus
from backend.db.repositories.inference import (
    InferenceRepository,
    _coerce_short_text,
)


def _make_session_capture():
    """Return ``(session, captured)`` where ``captured`` is filled by
    ``session.execute`` with the rendered statement so tests can
    introspect WHERE clauses without a real database."""

    session = AsyncMock()
    captured: list = []

    async def _record_execute(stmt, *_args, **_kwargs):
        captured.append(stmt)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result

    session.execute.side_effect = _record_execute
    session.add = MagicMock()
    return session, captured


class TestCoerceShortText(unittest.TestCase):
    def test_trims_and_returns_value(self) -> None:
        self.assertEqual(_coerce_short_text("  paid_social_hook  ", 64), "paid_social_hook")

    def test_returns_none_for_blank(self) -> None:
        self.assertIsNone(_coerce_short_text("   ", 64))
        self.assertIsNone(_coerce_short_text("", 64))

    def test_returns_none_for_non_string(self) -> None:
        self.assertIsNone(_coerce_short_text(None, 64))
        self.assertIsNone(_coerce_short_text(42, 64))
        self.assertIsNone(_coerce_short_text({"k": "v"}, 64))

    def test_truncates_to_max_length(self) -> None:
        self.assertEqual(_coerce_short_text("a" * 300, 255), "a" * 255)


class TestCreateJobDenormalizesCampaignContext(unittest.IsolatedAsyncioTestCase):
    async def test_create_job_populates_filter_columns(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        repo = InferenceRepository(session)

        await repo.create_job(
            project_id=uuid4(),
            creative_id=uuid4(),
            creative_version_id=uuid4(),
            created_by_user_id=uuid4(),
            request_payload={
                "campaign_context": {
                    "goal_template": "  paid_social_hook  ",
                    "channel": "meta_feed",
                    "audience_segment": "  Founders 25-34  ",
                    "objective": "Ship more demos",
                }
            },
            runtime_params={"analysis_surface": "analysis_dashboard", "media_type": "video"},
        )

        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        self.assertIsInstance(added, InferenceJob)
        self.assertEqual(added.goal_template, "paid_social_hook")
        self.assertEqual(added.channel, "meta_feed")
        self.assertEqual(added.audience_segment, "Founders 25-34")
        # The original JSONB stays intact as the source of truth.
        self.assertEqual(
            added.request_payload["campaign_context"]["goal_template"],
            "  paid_social_hook  ",
        )
        self.assertEqual(added.status, JobStatus.QUEUED)

    async def test_create_job_handles_missing_campaign_context(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        repo = InferenceRepository(session)

        await repo.create_job(
            project_id=uuid4(),
            creative_id=uuid4(),
            creative_version_id=uuid4(),
            created_by_user_id=None,
            request_payload={},
            runtime_params={},
        )

        added = session.add.call_args.args[0]
        self.assertIsNone(added.goal_template)
        self.assertIsNone(added.channel)
        self.assertIsNone(added.audience_segment)

    async def test_create_job_truncates_oversize_audience(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        repo = InferenceRepository(session)

        await repo.create_job(
            project_id=uuid4(),
            creative_id=uuid4(),
            creative_version_id=uuid4(),
            created_by_user_id=uuid4(),
            request_payload={
                "campaign_context": {"audience_segment": "x" * 1000}
            },
            runtime_params={},
        )

        added = session.add.call_args.args[0]
        assert added.audience_segment is not None
        self.assertEqual(len(added.audience_segment), 255)


class TestListAnalysisJobsForUserUsesIndexedColumns(unittest.IsolatedAsyncioTestCase):
    async def test_filters_use_first_class_columns_not_jsonb(self) -> None:
        session, captured = _make_session_capture()
        repo = InferenceRepository(session)

        await repo.list_analysis_jobs_for_user(
            project_id=uuid4(),
            created_by_user_id=uuid4(),
            media_type="video",
            goal_template="paid_social_hook",
            channel="meta_feed",
            audience_contains="founders",
            limit=10,
        )

        self.assertEqual(len(captured), 1)
        compiled = str(
            captured[0].compile(compile_kwargs={"literal_binds": True})
        )
        # New, indexed predicates exist.
        self.assertIn("inference_jobs.goal_template", compiled)
        self.assertIn("inference_jobs.channel", compiled)
        self.assertIn("lower(inference_jobs.audience_segment)", compiled)
        # And the old JSONB-path predicates are gone from the WHERE
        # clause for these filters.
        self.assertNotIn("'campaign_context'", compiled)


class TestBenchmarkCandidatesUseIndexedColumns(unittest.IsolatedAsyncioTestCase):
    async def test_benchmark_query_uses_case_weighted_ranking(self) -> None:
        session, captured = _make_session_capture()
        repo = InferenceRepository(session)

        await repo.query_analysis_benchmark_candidates(
            project_id=uuid4(),
            media_type="video",
            goal_template="paid_social_hook",
            channel="meta_feed",
            limit=50,
        )

        self.assertEqual(len(captured), 1)
        compiled = str(
            captured[0].compile(compile_kwargs={"literal_binds": True})
        )
        self.assertIn("inference_jobs.goal_template", compiled)
        self.assertIn("inference_jobs.channel", compiled)
        self.assertIn("CASE", compiled)
        self.assertIn("tier_rank", compiled)
        self.assertIn("EXISTS", compiled)
        self.assertNotIn("'campaign_context'", compiled)


class TestBenchmarkCohortSingleQuery(unittest.IsolatedAsyncioTestCase):
    async def test_list_benchmark_cohort_uses_single_weighted_query(self) -> None:
        session, _captured = _make_session_capture()
        repo = InferenceRepository(session)
        repo.query_analysis_benchmark_candidates = AsyncMock(return_value=[])

        await repo.list_benchmark_cohort(
            project_id=uuid4(),
            media_type="video",
            goal_template="paid_social_hook",
            channel="meta_feed",
            limit=50,
        )

        repo.query_analysis_benchmark_candidates.assert_awaited_once_with(
            project_id=unittest.mock.ANY,
            media_type="video",
            goal_template="paid_social_hook",
            channel="meta_feed",
            limit=50,
        )


class TestModelExposesIndexedColumns(unittest.TestCase):
    def test_columns_and_indexes_exist(self) -> None:
        # Columns
        column_names = {c.name for c in InferenceJob.__table__.columns}
        self.assertIn("goal_template", column_names)
        self.assertIn("channel", column_names)
        self.assertIn("audience_segment", column_names)

        # Indexes
        index_names = {idx.name for idx in InferenceJob.__table__.indexes}
        self.assertIn(
            "ix_inference_jobs_project_status_surface_media_created_desc", index_names
        )
        self.assertIn("ix_inference_jobs_project_goal_template", index_names)
        self.assertIn("ix_inference_jobs_project_channel", index_names)


# ``SimpleNamespace`` import is intentional to keep the test file
# self-contained for engineers reading it.
_ = SimpleNamespace


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
