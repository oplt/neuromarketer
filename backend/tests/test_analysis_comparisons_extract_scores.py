"""Regression: comparison must not show flat 50s when LLM clamps but TRIBE has signal."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from backend.application.services.analysis_comparisons import AnalysisComparisonApplicationService
from backend.schemas.analysis import (
    AnalysisMetricRowRead,
    AnalysisResultRead,
    AnalysisSegmentRowRead,
    AnalysisSummaryPayload,
    AnalysisTimelinePointRead,
    AnalysisVisualizationsPayload,
)


def _neutral_summary() -> AnalysisSummaryPayload:
    return AnalysisSummaryPayload(
        modality="video",
        overall_attention_score=50.0,
        hook_score_first_3_seconds=50.0,
        sustained_engagement_score=50.0,
        memory_proxy_score=50.0,
        cognitive_load_proxy=50.0,
        confidence=0.55,
        completeness=0.72,
    )


class TestExtractScoreMapTribeFallback(unittest.TestCase):
    def test_neutral_llm_uses_timeline_engagement(self) -> None:
        svc = AnalysisComparisonApplicationService(AsyncMock())
        jid = uuid4()
        timeline = [
            AnalysisTimelinePointRead(
                timestamp_ms=0,
                engagement_score=42.0,
                attention_score=50.0,
                memory_proxy=50.0,
            ),
            AnalysisTimelinePointRead(
                timestamp_ms=4000,
                engagement_score=68.0,
                attention_score=50.0,
                memory_proxy=50.0,
            ),
        ]
        result = AnalysisResultRead(
            job_id=jid,
            summary_json=_neutral_summary(),
            metrics_json=[
                AnalysisMetricRowRead(
                    key="conversion_proxy_score",
                    label="Conversion proxy",
                    value=62.0,
                    unit="/100",
                    source="llm",
                )
            ],
            timeline_json=timeline,
            segments_json=[],
            visualizations_json=AnalysisVisualizationsPayload(visualization_mode="frame_grid"),
            recommendations_json=[],
            created_at=datetime.now(UTC),
        )
        m = svc._extract_score_map(result)
        self.assertNotEqual(m["overall_attention"], 50.0)
        self.assertNotEqual(m["hook"], 50.0)
        self.assertNotEqual(m["sustained_engagement"], 50.0)
        self.assertEqual(m["conversion_proxy"], 62.0)

    def test_non_neutral_summary_unchanged(self) -> None:
        svc = AnalysisComparisonApplicationService(AsyncMock())
        jid = uuid4()
        summary = _neutral_summary()
        summary = summary.model_copy(update={"overall_attention_score": 63.0})
        timeline = [
            AnalysisTimelinePointRead(
                timestamp_ms=0,
                engagement_score=20.0,
                attention_score=50.0,
                memory_proxy=50.0,
            ),
            AnalysisTimelinePointRead(
                timestamp_ms=4000,
                engagement_score=80.0,
                attention_score=50.0,
                memory_proxy=50.0,
            ),
        ]
        result = AnalysisResultRead(
            job_id=jid,
            summary_json=summary,
            metrics_json=[],
            timeline_json=timeline,
            segments_json=[],
            visualizations_json=AnalysisVisualizationsPayload(visualization_mode="frame_grid"),
            recommendations_json=[],
            created_at=datetime.now(UTC),
        )
        m = svc._extract_score_map(result)
        self.assertEqual(m["overall_attention"], 63.0)

    def test_segment_cognitive_fills_low_load(self) -> None:
        svc = AnalysisComparisonApplicationService(AsyncMock())
        jid = uuid4()
        segs = [
            AnalysisSegmentRowRead(
                segment_index=0,
                label="A",
                start_time_ms=0,
                end_time_ms=2000,
                attention_score=50.0,
                engagement_delta=0.0,
                cognitive_load=35.0,
                note="",
            ),
            AnalysisSegmentRowRead(
                segment_index=1,
                label="B",
                start_time_ms=2000,
                end_time_ms=4000,
                attention_score=50.0,
                engagement_delta=0.0,
                cognitive_load=48.0,
                note="",
            ),
        ]
        result = AnalysisResultRead(
            job_id=jid,
            summary_json=_neutral_summary(),
            metrics_json=[],
            timeline_json=[
                AnalysisTimelinePointRead(
                    timestamp_ms=0,
                    engagement_score=50.0,
                    attention_score=50.0,
                    memory_proxy=50.0,
                ),
                AnalysisTimelinePointRead(
                    timestamp_ms=1000,
                    engagement_score=50.0,
                    attention_score=50.0,
                    memory_proxy=50.0,
                ),
            ],
            segments_json=segs,
            visualizations_json=AnalysisVisualizationsPayload(visualization_mode="frame_grid"),
            recommendations_json=[],
            created_at=datetime.now(UTC),
        )
        m = svc._extract_score_map(result)
        self.assertEqual(m["low_cognitive_load"], 58.5)


if __name__ == "__main__":
    unittest.main()
