from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from backend.services.scoring import ScoringBundle
from backend.services.tribe_runtime import TribeRuntimeOutput


@dataclass(slots=True)
class AnalysisDashboardPayload:
    summary_json: dict[str, Any]
    metrics_json: list[dict[str, Any]]
    timeline_json: list[dict[str, Any]]
    segments_json: list[dict[str, Any]]
    visualizations_json: dict[str, Any]
    recommendations_json: list[dict[str, Any]]


class AnalysisPostprocessor:
    GRID_LABELS = (
        "top_left",
        "top_center",
        "top_right",
        "middle_left",
        "middle_center",
        "middle_right",
        "bottom_left",
        "bottom_center",
        "bottom_right",
    )

    MODALITY_PRESENTATION = {
        "video": {
            "segment_prefix": "Scene",
            "segment_plural": "Scenes",
            "heatmap_prefix": "Keyframe",
            "heatmap_subject": "Scene",
            "timeline_label": "Video timeline",
            "visualization_mode": "video_frame_grid",
            "grid_caption": (
                "Frame-grid using direct TRIBE-derived segment signals and "
                "LLM-evaluated summary scores."
            ),
        },
        "audio": {
            "segment_prefix": "Audio window",
            "segment_plural": "Audio windows",
            "heatmap_prefix": "Audio signal",
            "heatmap_subject": "Window",
            "timeline_label": "Audio timeline",
            "visualization_mode": "audio_signal_grid",
            "grid_caption": (
                "Signal grid using audio timeline features; it is not a spatial frame."
            ),
        },
        "text": {
            "segment_prefix": "Passage",
            "segment_plural": "Passages",
            "heatmap_prefix": "Copy signal",
            "heatmap_subject": "Passage",
            "timeline_label": "Text sequence",
            "visualization_mode": "text_signal_grid",
            "grid_caption": (
                "Signal grid using text sequence features; it is not a visual heatmap."
            ),
        },
    }

    def build_dashboard_payload(
        self,
        *,
        runtime_output: TribeRuntimeOutput,
        scoring_bundle: ScoringBundle,
        modality: str,
        objective: str | None,
        goal_template: str | None,
        channel: str | None,
        audience_segment: str | None,
        source_label: str | None,
        include_recommendations: bool = True,
    ) -> AnalysisDashboardPayload:
        reduced_feature_vector = runtime_output.reduced_feature_vector or {}
        segment_features = list(reduced_feature_vector.get("segment_features", []))
        score_items = {score.score_type: score for score in scoring_bundle.scores}
        score_map = {
            score.score_type: self._to_float(score.normalized_score)
            for score in scoring_bundle.scores
        }
        confidence_values = [
            self._to_float(score.confidence)
            for score in scoring_bundle.scores
            if score.confidence is not None
        ]
        completeness_score = self._build_completeness_score(
            segment_count=len(segment_features),
            event_row_count=int(reduced_feature_vector.get("event_row_count", 0)),
        )
        confidence_score = (
            round(
                sum(confidence_values) / len(confidence_values) * 100.0,
                2,
            )
            if confidence_values
            else round(completeness_score, 2)
        )

        timeline_rows = self._build_timeline_rows(
            segment_features=segment_features,
            scoring_bundle=scoring_bundle,
            score_map=score_map,
        )
        segment_rows = self._build_segment_rows(
            timeline_rows=timeline_rows,
            segment_features=segment_features,
            scoring_bundle=scoring_bundle,
            score_map=score_map,
            modality=modality,
        )
        total_duration_ms = max(
            (int(row["end_time_ms"]) for row in segment_rows),
            default=max((int(row["timestamp_ms"]) for row in timeline_rows), default=0),
        )

        summary_json = self._build_summary_json(
            modality=modality,
            score_map=score_map,
            timeline_rows=timeline_rows,
            confidence_score=confidence_score,
            completeness_score=completeness_score,
            notes=scoring_bundle.notes,
            objective=objective,
            goal_template=goal_template,
            channel=channel,
            audience_segment=audience_segment,
            source_label=source_label,
            total_duration_ms=total_duration_ms,
            segment_count=len(segment_rows),
        )
        metrics_json = self._build_metrics_json(
            summary_json=summary_json,
            score_map=score_map,
            score_items=score_items,
            timeline_rows=timeline_rows,
            total_duration_ms=total_duration_ms,
        )
        high_attention_intervals: list[dict[str, Any]] = []
        low_attention_intervals: list[dict[str, Any]] = []
        presentation = self._presentation_for_modality(modality)
        visualizations_json = {
            "heatmap_frames": self._build_heatmap_frames(
                timeline_rows=timeline_rows,
                segment_features=segment_features,
                score_map=score_map,
                modality=modality,
            ),
            "high_attention_intervals": high_attention_intervals,
            "low_attention_intervals": low_attention_intervals,
            "visualization_mode": presentation["visualization_mode"],
            "presentation": presentation,
        }
        recommendations_json = (
            self._build_recommendations(
                scoring_bundle=scoring_bundle,
            )
            if include_recommendations
            else []
        )

        return AnalysisDashboardPayload(
            summary_json=summary_json,
            metrics_json=metrics_json,
            timeline_json=timeline_rows,
            segments_json=segment_rows,
            visualizations_json=visualizations_json,
            recommendations_json=recommendations_json,
        )

    def build_scene_extraction_payload(
        self,
        *,
        runtime_output: TribeRuntimeOutput,
        modality: str,
        objective: str | None,
        goal_template: str | None,
        channel: str | None,
        audience_segment: str | None,
        source_label: str | None,
    ) -> AnalysisDashboardPayload:
        reduced_feature_vector = runtime_output.reduced_feature_vector or {}
        segment_features = list(reduced_feature_vector.get("segment_features", []))
        completeness_score = self._build_completeness_score(
            segment_count=len(segment_features),
            event_row_count=int(reduced_feature_vector.get("event_row_count", 0)),
        )
        timeline_rows = self._build_scene_extraction_timeline_rows(
            segment_features=segment_features
        )
        segment_rows = self._build_segment_rows(
            timeline_rows=timeline_rows,
            segment_features=segment_features,
            modality=modality,
        )
        total_duration_ms = max(
            (int(row["end_time_ms"]) for row in segment_rows),
            default=max((int(row["timestamp_ms"]) for row in timeline_rows), default=0),
        )

        for row in segment_rows:
            row["attention_score"] = 0.0
            row["engagement_delta"] = 0.0
            row["note"] = (
                "Scene extraction is ready. Primary scoring is still generating the attention profile."
            )

        summary_json = {
            "modality": modality,
            "overall_attention_score": 0.0,
            "hook_score_first_3_seconds": 0.0,
            "sustained_engagement_score": 0.0,
            "memory_proxy_score": 0.0,
            "cognitive_load_proxy": 0.0,
            "confidence": None,
            "completeness": round(completeness_score, 2),
            "notes": [
                "Scene extraction is complete. Attention, memory, and recommendation scoring are still running.",
            ],
            "metadata": {
                "objective": objective,
                "goal_template": goal_template,
                "channel": channel,
                "audience_segment": audience_segment,
                "source_label": source_label,
                "segment_count": len(segment_rows),
                "duration_ms": total_duration_ms,
            },
        }
        presentation = self._presentation_for_modality(modality)
        visualizations_json = {
            "heatmap_frames": self._build_heatmap_frames(
                timeline_rows=timeline_rows,
                segment_features=segment_features,
                score_map={
                    "attention": 0.0,
                    "memory": 0.0,
                    "cognitive_load": 0.0,
                    "conversion_proxy": 0.0,
                },
                modality=modality,
            ),
            "high_attention_intervals": [],
            "low_attention_intervals": [],
            "visualization_mode": presentation["visualization_mode"],
            "presentation": presentation,
        }

        return AnalysisDashboardPayload(
            summary_json=summary_json,
            metrics_json=[],
            timeline_json=timeline_rows,
            segments_json=segment_rows,
            visualizations_json=visualizations_json,
            recommendations_json=[],
        )

    def with_recommendations(
        self,
        base_payload: AnalysisDashboardPayload,
        scoring_bundle: ScoringBundle,
    ) -> AnalysisDashboardPayload:
        return AnalysisDashboardPayload(
            summary_json=copy.deepcopy(base_payload.summary_json),
            metrics_json=copy.deepcopy(base_payload.metrics_json),
            timeline_json=copy.deepcopy(base_payload.timeline_json),
            segments_json=copy.deepcopy(base_payload.segments_json),
            visualizations_json=copy.deepcopy(base_payload.visualizations_json),
            recommendations_json=self._build_recommendations(scoring_bundle=scoring_bundle),
        )

    def build_result_payload(
        self,
        *,
        job_id: UUID,
        dashboard_payload: AnalysisDashboardPayload,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = created_at or datetime.now(UTC)
        return {
            "job_id": str(job_id),
            "summary_json": dashboard_payload.summary_json,
            "metrics_json": dashboard_payload.metrics_json,
            "timeline_json": dashboard_payload.timeline_json,
            "segments_json": dashboard_payload.segments_json,
            "visualizations_json": dashboard_payload.visualizations_json,
            "recommendations_json": dashboard_payload.recommendations_json,
            "created_at": timestamp.isoformat(),
        }

    def _build_scene_extraction_timeline_rows(
        self,
        *,
        segment_features: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, segment in enumerate(segment_features):
            timestamp_ms = int(segment.get("start_ms", index * 1000))
            engagement_score = round(float(segment.get("engagement_signal", 0.0)) * 100.0, 2)
            rows.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "engagement_score": engagement_score,
                    "attention_score": 0.0,
                    "memory_proxy": 0.0,
                }
            )
        if rows:
            return rows
        return [
            {
                "timestamp_ms": 0,
                "engagement_score": 0.0,
                "attention_score": 0.0,
                "memory_proxy": 0.0,
            }
        ]

    def _presentation_for_modality(self, modality: str) -> dict[str, str]:
        return dict(
            self.MODALITY_PRESENTATION.get(
                modality,
                {
                    **self.MODALITY_PRESENTATION["video"],
                    "visualization_mode": f"{modality or 'analysis'}_signal_grid",
                },
            )
        )

    def _build_summary_json(
        self,
        *,
        modality: str,
        score_map: dict[str, float],
        timeline_rows: list[dict[str, Any]],
        confidence_score: float,
        completeness_score: float,
        notes: list[str],
        objective: str | None,
        goal_template: str | None,
        channel: str | None,
        audience_segment: str | None,
        source_label: str | None,
        total_duration_ms: int,
        segment_count: int,
    ) -> dict[str, Any]:
        overall_attention_score = round(score_map.get("attention", 0.0), 2)
        opening_attention_scores = [
            row["attention_score"] for row in timeline_rows if row["timestamp_ms"] < 3_000
        ]
        post_opening_engagement_scores = [
            row["engagement_score"] for row in timeline_rows if row["timestamp_ms"] >= 3_000
        ]
        hook_score = (
            round(
                self._average(opening_attention_scores)
                if opening_attention_scores
                else self._average([row["attention_score"] for row in timeline_rows]),
                2,
            )
            if timeline_rows
            else 0.0
        )
        sustained_engagement_score = round(
            self._average(post_opening_engagement_scores)
            if post_opening_engagement_scores
            else self._average([row["engagement_score"] for row in timeline_rows]),
            2,
        )
        presentation = self._presentation_for_modality(modality)
        return {
            "modality": modality,
            "overall_attention_score": overall_attention_score,
            "hook_score_first_3_seconds": hook_score,
            "sustained_engagement_score": sustained_engagement_score,
            "memory_proxy_score": round(score_map.get("memory", 0.0), 2),
            "cognitive_load_proxy": round(score_map.get("cognitive_load", 0.0), 2),
            "confidence": round(confidence_score, 2),
            "completeness": round(completeness_score, 2),
            "notes": list(notes),
            "metadata": {
                "objective": objective,
                "goal_template": goal_template,
                "channel": channel,
                "audience_segment": audience_segment,
                "source_label": source_label,
                "segment_count": segment_count,
                "duration_ms": total_duration_ms,
                "segment_label": presentation["segment_prefix"],
                "segment_label_plural": presentation["segment_plural"],
                "timeline_label": presentation["timeline_label"],
                "visualization_mode": presentation["visualization_mode"],
            },
        }

    def _build_metrics_json(
        self,
        *,
        summary_json: dict[str, Any],
        score_map: dict[str, float],
        score_items: dict[str, Any],
        timeline_rows: list[dict[str, Any]],
        total_duration_ms: int,
    ) -> list[dict[str, Any]]:
        values = [
            {
                "key": "overall_attention_score",
                "label": "Overall Attention",
                "value": summary_json["overall_attention_score"],
                "unit": "/100",
                "source": "llm_analysis_scoring",
                "detail": "LLM-evaluated attention proxy grounded in TRIBE-derived evidence.",
                "confidence": self._score_confidence(
                    score_items, "attention", fallback=summary_json["confidence"]
                ),
            },
            {
                "key": "emotion_score",
                "label": "Emotion",
                "value": round(score_map.get("emotion", 0.0), 2),
                "unit": "/100",
                "source": "llm_analysis_scoring",
                "detail": "LLM-evaluated emotion proxy grounded in TRIBE-derived evidence.",
                "confidence": self._score_confidence(
                    score_items, "emotion", fallback=summary_json["confidence"]
                ),
            },
            {
                "key": "hook_score_first_3_seconds",
                "label": "Hook Score First 3 Seconds",
                "value": summary_json["hook_score_first_3_seconds"],
                "unit": "/100",
                "source": "analysis_postprocessor",
                "detail": "Opening-window average of the attention timeline.",
                "confidence": summary_json["confidence"],
            },
            {
                "key": "sustained_engagement_score",
                "label": "Sustained Engagement",
                "value": summary_json["sustained_engagement_score"],
                "unit": "/100",
                "source": "analysis_postprocessor",
                "detail": "Average engagement after the opening window.",
                "confidence": summary_json["confidence"],
            },
            {
                "key": "memory_proxy_score",
                "label": "Memory Proxy",
                "value": summary_json["memory_proxy_score"],
                "unit": "/100",
                "source": "llm_analysis_scoring",
                "detail": "LLM-evaluated recall proxy grounded in TRIBE-derived evidence.",
                "confidence": self._score_confidence(
                    score_items, "memory", fallback=summary_json["confidence"]
                ),
            },
            {
                "key": "cognitive_load_proxy",
                "label": "Cognitive Load Proxy",
                "value": summary_json["cognitive_load_proxy"],
                "unit": "/100",
                "source": "llm_analysis_scoring",
                "detail": "LLM-evaluated processing-friction proxy grounded in TRIBE-derived evidence.",
                "confidence": self._score_confidence(
                    score_items, "cognitive_load", fallback=summary_json["confidence"]
                ),
            },
            {
                "key": "conversion_proxy_score",
                "label": "Conversion Proxy",
                "value": round(score_map.get("conversion_proxy", 0.0), 2),
                "unit": "/100",
                "source": "llm_analysis_scoring",
                "detail": "LLM-evaluated persuasive-action proxy grounded in TRIBE-derived evidence.",
                "confidence": self._score_confidence(
                    score_items, "conversion_proxy", fallback=summary_json["confidence"]
                ),
            },
            {
                "key": "average_engagement",
                "label": "Average Engagement",
                "value": round(
                    self._average([row["engagement_score"] for row in timeline_rows]), 2
                ),
                "unit": "/100",
                "source": "analysis_postprocessor",
                "detail": "Mean engagement across all segments.",
                "confidence": summary_json["confidence"],
            },
            {
                "key": "asset_duration_seconds",
                "label": "Asset Duration",
                "value": round(total_duration_ms / 1000.0, 2),
                "unit": "seconds",
                "source": "analysis_postprocessor",
                "detail": "Duration estimated from segment boundaries.",
                "confidence": summary_json["completeness"],
            },
            {
                "key": "confidence",
                "label": "Confidence",
                "value": summary_json["confidence"],
                "unit": "/100",
                "source": "analysis_postprocessor",
                "detail": "Score confidence based on TRIBE segment coverage and scoring confidence.",
                "confidence": summary_json["confidence"],
            },
            {
                "key": "completeness",
                "label": "Completeness",
                "value": summary_json["completeness"],
                "unit": "/100",
                "source": "analysis_postprocessor",
                "detail": "How complete the source timeline is for analysis.",
                "confidence": summary_json["completeness"],
            },
        ]
        return values

    def _build_timeline_rows(
        self,
        *,
        segment_features: list[dict[str, Any]],
        scoring_bundle: ScoringBundle,
        score_map: dict[str, float],
    ) -> list[dict[str, Any]]:
        point_by_timestamp = {
            int(point.timestamp_ms): point for point in scoring_bundle.timeline_points
        }
        # Secondary index by segment_index stored in metadata_json for robust lookup
        point_by_index: dict[int, Any] = {}
        for point in scoring_bundle.timeline_points:
            seg_idx = point.metadata_json.get("segment_index")
            if seg_idx is not None:
                point_by_index[int(seg_idx)] = point
        rows: list[dict[str, Any]] = []
        for index, segment in enumerate(segment_features):
            timestamp_ms = int(segment.get("start_ms", index * 1000))
            scoring_point = point_by_timestamp.get(timestamp_ms) or point_by_index.get(index)
            engagement_score = round(float(segment.get("engagement_signal", 0.0)) * 100.0, 2)
            point_attention = self._to_float(getattr(scoring_point, "attention_score", None))
            point_memory = self._to_float(getattr(scoring_point, "memory_score", None))
            attention_score = round(
                point_attention
                if scoring_point is not None
                and getattr(scoring_point, "attention_score", None) is not None
                else score_map.get("attention", 0.0),
                2,
            )
            memory_proxy = round(
                point_memory
                if scoring_point is not None
                and getattr(scoring_point, "memory_score", None) is not None
                else score_map.get("memory", 0.0),
                2,
            )
            rows.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "engagement_score": engagement_score,
                    "attention_score": attention_score,
                    "memory_proxy": memory_proxy,
                }
            )
        if rows:
            return rows
        return [
            {
                "timestamp_ms": 0,
                "engagement_score": round(score_map.get("attention", 0.0), 2),
                "attention_score": round(score_map.get("attention", 0.0), 2),
                "memory_proxy": round(score_map.get("memory", 0.0), 2),
            }
        ]

    def _build_segment_rows(
        self,
        *,
        timeline_rows: list[dict[str, Any]],
        segment_features: list[dict[str, Any]],
        scoring_bundle: ScoringBundle | None = None,
        score_map: dict[str, float] | None = None,
        modality: str = "video",
    ) -> list[dict[str, Any]]:
        # Build lookup maps once for O(1) per-segment access
        _bundle_points = scoring_bundle.timeline_points if scoring_bundle is not None else []
        _point_by_ts: dict[int, Any] = {int(p.timestamp_ms): p for p in _bundle_points}
        _point_by_idx: dict[int, Any] = {}
        for p in _bundle_points:
            si = p.metadata_json.get("segment_index")
            if si is not None:
                _point_by_idx[int(si)] = p

        rows: list[dict[str, Any]] = []
        previous_engagement: float | None = None
        _score_map = score_map or {}
        presentation = self._presentation_for_modality(modality)
        for index, timeline_row in enumerate(timeline_rows):
            segment = segment_features[index] if index < len(segment_features) else {}
            duration_ms = int(segment.get("duration_ms", 1000))
            engagement_score = float(timeline_row["engagement_score"])
            attention_score = float(timeline_row["attention_score"])
            memory_proxy = float(timeline_row.get("memory_proxy", 0.0))
            scoring_point = _point_by_ts.get(
                int(timeline_row["timestamp_ms"])
            ) or _point_by_idx.get(index)
            engagement_delta = (
                round(
                    engagement_score - previous_engagement,
                    2,
                )
                if previous_engagement is not None
                else 0.0
            )
            note = self._build_segment_note(scoring_point=scoring_point)

            # TRIBE-direct per-segment signals (model output, 0–1 → 0–100)
            peak_focus = round(float(segment.get("peak_focus_signal", 0.0)) * 100.0, 2)
            temporal_change = round(float(segment.get("temporal_change_signal", 0.0)) * 100.0, 2)
            consistency = round(float(segment.get("consistency_signal", 0.0)) * 100.0, 2)
            hemisphere_balance = round(
                float(segment.get("hemisphere_balance_signal", 0.0)) * 100.0, 2
            )

            # LLM-evaluated per-segment signals (with global fallback)
            def _pt(attr: str, fallback_key: str) -> float:
                val = getattr(scoring_point, attr, None) if scoring_point is not None else None
                return round(
                    self._to_float(val) if val is not None else _score_map.get(fallback_key, 0.0), 2
                )

            rows.append(
                {
                    "segment_index": index,
                    "label": f"{presentation['segment_prefix']} {index + 1:02d}",
                    "start_time_ms": int(timeline_row["timestamp_ms"]),
                    "end_time_ms": int(timeline_row["timestamp_ms"]) + duration_ms,
                    "attention_score": round(attention_score, 2),
                    "engagement_score": round(engagement_score, 2),
                    "engagement_delta": engagement_delta,
                    "memory_proxy": round(memory_proxy, 2),
                    "emotion_score": _pt("emotion_score", "emotion"),
                    "cognitive_load": _pt("cognitive_load_score", "cognitive_load"),
                    "conversion_proxy": _pt("conversion_proxy_score", "conversion_proxy"),
                    "peak_focus": peak_focus,
                    "temporal_change": temporal_change,
                    "consistency": consistency,
                    "hemisphere_balance": hemisphere_balance,
                    "note": note,
                }
            )
            previous_engagement = engagement_score
        return rows

    def _build_heatmap_frames(
        self,
        *,
        timeline_rows: list[dict[str, Any]],
        segment_features: list[dict[str, Any]],
        score_map: dict[str, float],
        modality: str = "video",
    ) -> list[dict[str, Any]]:
        if not timeline_rows:
            return []

        ranked_rows = sorted(
            enumerate(timeline_rows),
            key=lambda item: item[1]["attention_score"],
            reverse=True,
        )
        selected_indices = {0, len(timeline_rows) - 1}
        if ranked_rows:
            selected_indices.add(ranked_rows[0][0])
            selected_indices.add(ranked_rows[-1][0])

        frames: list[dict[str, Any]] = []
        presentation = self._presentation_for_modality(modality)
        for index in sorted(selected_indices)[:4]:
            timeline_row = timeline_rows[index]
            segment = segment_features[index] if index < len(segment_features) else {}
            attention_score = float(timeline_row["attention_score"])
            engagement_score = float(timeline_row["engagement_score"])
            memory_proxy = float(timeline_row["memory_proxy"])
            cognitive_load = float(score_map.get("cognitive_load", 0.0))
            temporal_change = float(segment.get("temporal_change_signal", 0.0)) * 100.0
            consistency = float(segment.get("consistency_signal", 0.0)) * 100.0
            peak_focus = float(segment.get("peak_focus_signal", 0.0)) * 100.0
            grid = [
                [round(engagement_score, 2), round(attention_score, 2), round(peak_focus, 2)],
                [
                    round(memory_proxy, 2),
                    round(attention_score, 2),
                    round(max(0.0, 100.0 - cognitive_load), 2),
                ],
                [
                    round(consistency, 2),
                    round(temporal_change, 2),
                    round(score_map.get("conversion_proxy", 0.0), 2),
                ],
            ]
            flat_grid = [value for row in grid for value in row]
            max_index = flat_grid.index(max(flat_grid))
            frames.append(
                {
                    "timestamp_ms": int(timeline_row["timestamp_ms"]),
                    "label": f"{presentation['heatmap_prefix']} {len(frames) + 1}",
                    "scene_label": f"{presentation['heatmap_subject']} {index + 1:02d}",
                    "grid_rows": 3,
                    "grid_columns": 3,
                    "intensity_map": grid,
                    "strongest_zone": self.GRID_LABELS[max_index],
                    "caption": presentation["grid_caption"],
                }
            )
        return frames

    def _build_intervals(
        self,
        *,
        timeline_rows: list[dict[str, Any]],
        predicate,
        label: str,
    ) -> list[dict[str, Any]]:
        intervals: list[dict[str, Any]] = []
        active_start: int | None = None
        active_end: int | None = None
        active_scores: list[float] = []

        for index, row in enumerate(timeline_rows):
            timestamp_ms = int(row["timestamp_ms"])
            current_end = (
                int(timeline_rows[index + 1]["timestamp_ms"])
                if index < len(timeline_rows) - 1
                else timestamp_ms + 1000
            )
            if predicate(row):
                if active_start is None:
                    active_start = timestamp_ms
                active_end = current_end
                active_scores.append(float(row["attention_score"]))
                continue
            if active_start is not None and active_end is not None:
                intervals.append(
                    {
                        "label": label,
                        "start_time_ms": active_start,
                        "end_time_ms": active_end,
                        "average_attention_score": round(self._average(active_scores), 2),
                    }
                )
                active_start = None
                active_end = None
                active_scores = []

        if active_start is not None and active_end is not None:
            intervals.append(
                {
                    "label": label,
                    "start_time_ms": active_start,
                    "end_time_ms": active_end,
                    "average_attention_score": round(self._average(active_scores), 2),
                }
            )
        return intervals

    def _build_recommendations(
        self,
        *,
        scoring_bundle: ScoringBundle,
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        for suggestion in scoring_bundle.suggestions[:6]:
            timestamp_ms = suggestion.proposed_change_json.get("timestamp_ms")
            recommendations.append(
                {
                    "title": suggestion.title,
                    "detail": suggestion.rationale,
                    "priority": "medium",
                    "timestamp_ms": int(timestamp_ms)
                    if isinstance(timestamp_ms, (int, float))
                    else None,
                    "confidence": round(self._to_float(suggestion.confidence) * 100.0, 2)
                    if suggestion.confidence is not None
                    else None,
                }
            )

        deduped: list[dict[str, Any]] = []
        seen_titles: set[str] = set()
        for item in recommendations:
            title = str(item["title"]).strip()
            if title in seen_titles:
                continue
            seen_titles.add(title)
            deduped.append(item)
        return deduped[:6]

    def _build_segment_note(self, *, scoring_point) -> str:
        if scoring_point is None:
            return "Segment included in the scored timeline."
        rationale = (
            scoring_point.metadata_json.get("rationale")
            if isinstance(scoring_point.metadata_json, dict)
            else None
        )
        if isinstance(rationale, str) and rationale.strip():
            return rationale.strip()
        return "Segment included in the scored timeline."

    def _build_completeness_score(self, *, segment_count: int, event_row_count: int) -> float:
        base = 45.0
        segment_bonus = min(35.0, segment_count * 5.0)
        event_bonus = min(20.0, event_row_count * 0.4)
        return min(100.0, base + segment_bonus + event_bonus)

    def _average(self, values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _to_float(self, value: Decimal | float | int | None) -> float:
        if value is None:
            return 0.0
        return float(value)

    def _score_confidence(
        self, score_items: dict[str, Any], key: str, *, fallback: float | None
    ) -> float | None:
        score_item = score_items.get(key)
        if score_item is None or score_item.confidence is None:
            return fallback
        return round(self._to_float(score_item.confidence) * 100.0, 2)
