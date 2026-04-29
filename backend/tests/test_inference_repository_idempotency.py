"""Idempotency tests for ``InferenceRepository`` write paths.

The Celery prediction pipeline runs with ``acks_late=True`` and
``max_retries=3`` on ``process_prediction_job``. A retry can therefore
re-execute ``store_prediction_handoff`` / ``replace_prediction_result``
/ ``replace_analysis_result`` against a job whose previous attempt
already persisted some rows. These tests pin down the contract:

1. parent rows are upserted in place (primary keys stay stable);
2. child rows are replaced with a scoped delete + insert in the same
   transaction (no orphans, no duplicates);
3. ``JobMetric`` rows are upserted by ``(job_id, name, phase)`` instead
   of accumulating duplicates.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.db.models import (
    AnalysisResultRecord,
    JobMetric,
    OptimizationSuggestion,
    PredictionResult,
    PredictionScore,
    PredictionTimelinePoint,
    PredictionVisualization,
    ScoreType,
    SuggestionStatus,
    SuggestionType,
    VisualizationType,
)
from backend.db.repositories.inference import InferenceRepository
from backend.services.scoring import (
    ScoreItem,
    ScoringBundle,
    SuggestionItem,
    TimelinePointItem,
    VisualizationItem,
)
from backend.services.tribe_runtime import TribeRuntimeOutput
from sqlalchemy.sql.dml import Delete


def _make_runtime_output() -> TribeRuntimeOutput:
    return TribeRuntimeOutput(
        raw_brain_response_uri="s3://bucket/raw.json",
        raw_brain_response_summary={"k": "v"},
        reduced_feature_vector={"vec": [0.1, 0.2]},
        region_activation_summary={"region": 0.3},
        provenance_json={"model_version": "tribe-v2"},
    )


def _make_scoring_bundle() -> ScoringBundle:
    return ScoringBundle(
        scores=[
            ScoreItem(
                score_type=ScoreType.ATTENTION.value,
                normalized_score=Decimal("88.50"),
                raw_value=Decimal("0.885"),
                confidence=Decimal("0.9"),
                percentile=Decimal("0.7"),
                metadata_json={},
            )
        ],
        visualizations=[
            VisualizationItem(
                visualization_type=VisualizationType.HEATMAP,
                title="Heatmap",
                storage_uri=None,
                data_json={"frames": []},
            )
        ],
        timeline_points=[
            TimelinePointItem(
                timestamp_ms=0,
                attention_score=Decimal("88.50"),
                emotion_score=None,
                memory_score=None,
                cognitive_load_score=None,
                conversion_proxy_score=None,
                metadata_json={},
            )
        ],
        suggestions=[
            SuggestionItem(
                suggestion_type=SuggestionType.COPY,
                status=SuggestionStatus.PROPOSED,
                title="Tighten hook",
                rationale="First 3 seconds drop attention.",
                proposed_change_json={},
                expected_score_lift_json={},
                confidence=Decimal("0.6"),
            )
        ],
        notes=[],
    )


def _make_session() -> tuple[AsyncMock, list]:
    """Return ``(session, executed)`` where ``executed`` records every
    ``session.execute`` call argument so tests can introspect the
    statements that were emitted."""

    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    executed: list = []

    async def _record_execute(stmt, *_args, **_kwargs):
        executed.append(stmt)
        return MagicMock()

    session.execute.side_effect = _record_execute
    return session, executed


def _delete_targets(executed: list) -> list[str]:
    return [
        getattr(stmt.table, "name", None)
        for stmt in executed
        if isinstance(stmt, Delete)
    ]


class TestReplaceAnalysisResultIdempotency(unittest.IsolatedAsyncioTestCase):
    async def test_updates_existing_record_in_place(self) -> None:
        session, _ = _make_session()
        repo = InferenceRepository(session)
        job_id = uuid4()
        existing = SimpleNamespace(
            id=uuid4(),
            job_id=job_id,
            summary_json={"old": True},
            metrics_json=[],
            timeline_json=[],
            segments_json=[],
            visualizations_json={},
            recommendations_json=[],
        )
        repo.get_analysis_result_for_job = AsyncMock(return_value=existing)

        record = await repo.replace_analysis_result(
            job=SimpleNamespace(id=job_id),
            summary_json={"updated": True},
            metrics_json=[{"m": 1}],
            timeline_json=[{"t": 0}],
            segments_json=[{"s": 0}],
            visualizations_json={"v": 1},
            recommendations_json=[{"r": 1}],
        )

        self.assertIs(record, existing)
        self.assertEqual(record.id, existing.id)
        self.assertEqual(record.summary_json, {"updated": True})
        self.assertEqual(record.metrics_json, [{"m": 1}])
        session.add.assert_not_called()
        session.delete.assert_not_called()

    async def test_inserts_when_no_existing_record(self) -> None:
        session, _ = _make_session()
        repo = InferenceRepository(session)
        job_id = uuid4()
        repo.get_analysis_result_for_job = AsyncMock(return_value=None)

        await repo.replace_analysis_result(
            job=SimpleNamespace(id=job_id),
            summary_json={"new": True},
            metrics_json=[],
            timeline_json=[],
            segments_json=[],
            visualizations_json={},
            recommendations_json=[],
        )

        session.delete.assert_not_called()
        session.add.assert_called_once()
        added = session.add.call_args.args[0]
        self.assertIsInstance(added, AnalysisResultRecord)
        self.assertEqual(added.job_id, job_id)


class TestReplacePredictionResultIdempotency(unittest.IsolatedAsyncioTestCase):
    async def test_updates_parent_and_replaces_children_with_scoped_deletes(self) -> None:
        session, executed = _make_session()
        repo = InferenceRepository(session)
        job = SimpleNamespace(
            id=uuid4(),
            project_id=uuid4(),
            creative_id=uuid4(),
            creative_version_id=uuid4(),
        )
        existing_prediction_id = uuid4()
        existing = SimpleNamespace(
            id=existing_prediction_id,
            job_id=job.id,
            project_id=job.project_id,
            creative_id=job.creative_id,
            creative_version_id=job.creative_version_id,
            raw_brain_response_uri=None,
            raw_brain_response_summary={},
            reduced_feature_vector={},
            region_activation_summary={},
            provenance_json={},
        )
        repo.get_prediction_result_for_job = AsyncMock(return_value=existing)

        prediction = await repo.replace_prediction_result(
            job=job,
            runtime_output=_make_runtime_output(),
            scoring_bundle=_make_scoring_bundle(),
            model_name="tribe-v2",
        )

        self.assertEqual(prediction.id, existing_prediction_id)
        self.assertEqual(prediction.raw_brain_response_uri, "s3://bucket/raw.json")
        session.delete.assert_not_called()

        delete_targets = _delete_targets(executed)
        self.assertIn(PredictionScore.__tablename__, delete_targets)
        self.assertIn(PredictionVisualization.__tablename__, delete_targets)
        self.assertIn(PredictionTimelinePoint.__tablename__, delete_targets)
        self.assertIn(OptimizationSuggestion.__tablename__, delete_targets)
        self.assertIn(JobMetric.__tablename__, delete_targets)

        added_kinds = {
            type(arg) for call_ in session.add_all.call_args_list for arg in call_.args[0]
        }
        self.assertEqual(
            added_kinds,
            {
                PredictionScore,
                PredictionVisualization,
                PredictionTimelinePoint,
                OptimizationSuggestion,
            },
        )
        added_singles = [c.args[0] for c in session.add.call_args_list]
        self.assertTrue(any(isinstance(item, JobMetric) for item in added_singles))

    async def test_inserts_parent_when_no_existing_prediction(self) -> None:
        session, _ = _make_session()
        repo = InferenceRepository(session)
        job = SimpleNamespace(
            id=uuid4(),
            project_id=uuid4(),
            creative_id=uuid4(),
            creative_version_id=uuid4(),
        )
        repo.get_prediction_result_for_job = AsyncMock(return_value=None)

        await repo.replace_prediction_result(
            job=job,
            runtime_output=_make_runtime_output(),
            scoring_bundle=ScoringBundle(
                scores=[],
                visualizations=[],
                timeline_points=[],
                suggestions=[],
                notes=[],
            ),
            model_name="tribe-v2",
        )

        added_singles = [c.args[0] for c in session.add.call_args_list]
        prediction_inserts = [
            item for item in added_singles if isinstance(item, PredictionResult)
        ]
        self.assertEqual(len(prediction_inserts), 1)
        metric_inserts = [item for item in added_singles if isinstance(item, JobMetric)]
        self.assertEqual(len(metric_inserts), 1)


class TestStorePredictionHandoffIdempotency(unittest.IsolatedAsyncioTestCase):
    async def test_handoff_metric_is_scoped_upsert(self) -> None:
        session, executed = _make_session()
        repo = InferenceRepository(session)
        job = SimpleNamespace(
            id=uuid4(),
            project_id=uuid4(),
            creative_id=uuid4(),
            creative_version_id=uuid4(),
        )
        existing = SimpleNamespace(
            id=uuid4(),
            job_id=job.id,
            project_id=job.project_id,
            creative_id=job.creative_id,
            creative_version_id=job.creative_version_id,
            raw_brain_response_uri=None,
            raw_brain_response_summary={},
            reduced_feature_vector={},
            region_activation_summary={},
            provenance_json={},
        )
        repo.get_prediction_result_for_job = AsyncMock(return_value=existing)

        await repo.store_prediction_handoff(
            job=job,
            runtime_output=_make_runtime_output(),
            model_name="tribe-v2",
        )

        delete_targets = _delete_targets(executed)
        self.assertEqual(delete_targets.count(JobMetric.__tablename__), 1)
        added_singles = [c.args[0] for c in session.add.call_args_list]
        self.assertEqual(
            sum(1 for item in added_singles if isinstance(item, JobMetric)), 1
        )


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    unittest.main()
