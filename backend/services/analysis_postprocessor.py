from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
        score_map = {score.score_type: self._to_float(score.normalized_score) for score in scoring_bundle.scores}
        confidence_values = [
            self._to_float(score.confidence)
            for score in scoring_bundle.scores
            if score.confidence is not None
        ]
        completeness_score = self._build_completeness_score(
            segment_count=len(segment_features),
            event_row_count=int(reduced_feature_vector.get("event_row_count", 0)),
        )
        confidence_score = round(
            sum(confidence_values) / len(confidence_values) * 100.0,
            2,
        ) if confidence_values else round(completeness_score, 2)

        timeline_rows = self._build_timeline_rows(
            segment_features=segment_features,
            scoring_bundle=scoring_bundle,
            score_map=score_map,
        )
        segment_rows = self._build_segment_rows(timeline_rows=timeline_rows, segment_features=segment_features)
        total_duration_ms = max(
            (
                int(row["end_time_ms"])
                for row in segment_rows
            ),
            default=max((int(row["timestamp_ms"]) for row in timeline_rows), default=0),
        )

        summary_json = self._build_summary_json(
            modality=modality,
            score_map=score_map,
            timeline_rows=timeline_rows,
            confidence_score=confidence_score,
            completeness_score=completeness_score,
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
            timeline_rows=timeline_rows,
            total_duration_ms=total_duration_ms,
        )
        high_attention_intervals = self._build_intervals(
            timeline_rows=timeline_rows,
            predicate=lambda row: row["attention_score"] >= 72.0 or row["engagement_score"] >= 75.0,
            label="High attention",
        )
        low_attention_intervals = self._build_intervals(
            timeline_rows=timeline_rows,
            predicate=lambda row: row["attention_score"] <= 45.0 or row["engagement_score"] <= 42.0,
            label="Low attention",
        )
        visualizations_json = {
            "heatmap_frames": self._build_heatmap_frames(
                timeline_rows=timeline_rows,
                segment_features=segment_features,
                score_map=score_map,
            ),
            "high_attention_intervals": high_attention_intervals,
            "low_attention_intervals": low_attention_intervals,
            "visualization_mode": "frame_grid_fallback",
        }
        recommendations_json = (
            self._build_recommendations(
                summary_json=summary_json,
                timeline_rows=timeline_rows,
                segment_rows=segment_rows,
                high_attention_intervals=high_attention_intervals,
                low_attention_intervals=low_attention_intervals,
                scoring_bundle=scoring_bundle,
                total_duration_ms=total_duration_ms,
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
        timeline_rows = self._build_scene_extraction_timeline_rows(segment_features=segment_features)
        segment_rows = self._build_segment_rows(timeline_rows=timeline_rows, segment_features=segment_features)
        total_duration_ms = max(
            (
                int(row["end_time_ms"])
                for row in segment_rows
            ),
            default=max((int(row["timestamp_ms"]) for row in timeline_rows), default=0),
        )

        for row in segment_rows:
            row["attention_score"] = 0.0
            row["engagement_delta"] = 0.0
            row["note"] = "Scene extraction is ready. Primary scoring is still generating the attention profile."

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
            ),
            "high_attention_intervals": [],
            "low_attention_intervals": [],
            "visualization_mode": "frame_grid_fallback",
        }

        return AnalysisDashboardPayload(
            summary_json=summary_json,
            metrics_json=[],
            timeline_json=timeline_rows,
            segments_json=segment_rows,
            visualizations_json=visualizations_json,
            recommendations_json=[],
        )

    def build_result_payload(
        self,
        *,
        job_id: UUID,
        dashboard_payload: AnalysisDashboardPayload,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = created_at or datetime.now(timezone.utc)
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

    def _build_summary_json(
        self,
        *,
        modality: str,
        score_map: dict[str, float],
        timeline_rows: list[dict[str, Any]],
        confidence_score: float,
        completeness_score: float,
        objective: str | None,
        goal_template: str | None,
        channel: str | None,
        audience_segment: str | None,
        source_label: str | None,
        total_duration_ms: int,
        segment_count: int,
    ) -> dict[str, Any]:
        overall_attention_score = round(score_map.get("attention", 0.0), 2)
        hook_score = round(
            self._average(
                [
                    (row["engagement_score"] * 0.55) + (row["attention_score"] * 0.45)
                    for row in timeline_rows
                    if row["timestamp_ms"] < 3_000
                ]
            ),
            2,
        ) if timeline_rows else 0.0
        sustained_engagement_score = round(
            self._average(
                [
                    row["engagement_score"]
                    for row in timeline_rows
                    if row["timestamp_ms"] >= 3_000
                ]
            ) or self._average([row["engagement_score"] for row in timeline_rows]),
            2,
        )
        return {
            "modality": modality,
            "overall_attention_score": overall_attention_score,
            "hook_score_first_3_seconds": hook_score,
            "sustained_engagement_score": sustained_engagement_score,
            "memory_proxy_score": round(score_map.get("memory", 0.0), 2),
            "cognitive_load_proxy": round(score_map.get("cognitive_load", 0.0), 2),
            "confidence": round(confidence_score, 2),
            "completeness": round(completeness_score, 2),
            "notes": self._build_summary_notes(
                overall_attention_score=overall_attention_score,
                hook_score=hook_score,
                sustained_engagement_score=sustained_engagement_score,
                cognitive_load_proxy=round(score_map.get("cognitive_load", 0.0), 2),
            ),
            "metadata": {
                "objective": objective,
                "goal_template": goal_template,
                "channel": channel,
                "audience_segment": audience_segment,
                "source_label": source_label,
                "segment_count": segment_count,
                "duration_ms": total_duration_ms,
            },
        }

    def _build_metrics_json(
        self,
        *,
        summary_json: dict[str, Any],
        score_map: dict[str, float],
        timeline_rows: list[dict[str, Any]],
        total_duration_ms: int,
    ) -> list[dict[str, Any]]:
        values = [
            {
                "key": "overall_attention_score",
                "label": "Overall Attention",
                "value": summary_json["overall_attention_score"],
                "unit": "/100",
                "source": "analysis_postprocessor",
                "detail": "Overall audience attention proxy derived from TRIBE segment outputs.",
                "confidence": summary_json["confidence"],
            },
            {
                "key": "hook_score_first_3_seconds",
                "label": "Hook Score First 3 Seconds",
                "value": summary_json["hook_score_first_3_seconds"],
                "unit": "/100",
                "source": "analysis_postprocessor",
                "detail": "Blend of early engagement and attention signals.",
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
                "source": "analysis_postprocessor",
                "detail": "Recall-oriented proxy derived from temporal consistency.",
                "confidence": summary_json["confidence"],
            },
            {
                "key": "cognitive_load_proxy",
                "label": "Cognitive Load Proxy",
                "value": summary_json["cognitive_load_proxy"],
                "unit": "/100",
                "source": "analysis_postprocessor",
                "detail": "Higher values indicate more processing friction.",
                "confidence": summary_json["confidence"],
            },
            {
                "key": "conversion_proxy_score",
                "label": "Conversion Proxy",
                "value": round(score_map.get("conversion_proxy", 0.0), 2),
                "unit": "/100",
                "source": "analysis_postprocessor",
                "detail": "Composite CTA readiness proxy.",
                "confidence": summary_json["confidence"],
            },
            {
                "key": "average_engagement",
                "label": "Average Engagement",
                "value": round(self._average([row["engagement_score"] for row in timeline_rows]), 2),
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
            int(point.timestamp_ms): point
            for point in scoring_bundle.timeline_points
        }
        rows: list[dict[str, Any]] = []
        for index, segment in enumerate(segment_features):
            timestamp_ms = int(segment.get("start_ms", index * 1000))
            scoring_point = point_by_timestamp.get(timestamp_ms)
            engagement_score = round(float(segment.get("engagement_signal", 0.0)) * 100.0, 2)
            attention_score = round(
                self._to_float(getattr(scoring_point, "attention_score", None)) or score_map.get("attention", 0.0),
                2,
            )
            memory_proxy = round(
                self._to_float(getattr(scoring_point, "memory_score", None)) or score_map.get("memory", 0.0),
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
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        previous_engagement: float | None = None
        for index, timeline_row in enumerate(timeline_rows):
            segment = segment_features[index] if index < len(segment_features) else {}
            duration_ms = int(segment.get("duration_ms", 1000))
            engagement_score = float(timeline_row["engagement_score"])
            attention_score = float(timeline_row["attention_score"])
            engagement_delta = round(
                engagement_score - previous_engagement,
                2,
            ) if previous_engagement is not None else 0.0
            note = self._build_segment_note(
                attention_score=attention_score,
                engagement_delta=engagement_delta,
                event_count=int(segment.get("event_count", 0)),
            )
            rows.append(
                {
                    "segment_index": index,
                    "label": f"Scene {index + 1:02d}",
                    "start_time_ms": int(timeline_row["timestamp_ms"]),
                    "end_time_ms": int(timeline_row["timestamp_ms"]) + duration_ms,
                    "attention_score": round(attention_score, 2),
                    "engagement_delta": engagement_delta,
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
                [round(engagement_score * 0.74, 2), round(attention_score * 0.88, 2), round(peak_focus, 2)],
                [round(memory_proxy * 0.68, 2), round(attention_score, 2), round(max(0.0, 100.0 - cognitive_load), 2)],
                [round(consistency, 2), round(max(0.0, 55.0 + temporal_change * 0.45), 2), round(score_map.get("conversion_proxy", 0.0) * 0.9, 2)],
            ]
            flat_grid = [value for row in grid for value in row]
            max_index = flat_grid.index(max(flat_grid))
            frames.append(
                {
                    "timestamp_ms": int(timeline_row["timestamp_ms"]),
                    "label": f"Keyframe {len(frames) + 1}",
                    "scene_label": f"Scene {index + 1:02d}",
                    "grid_rows": 3,
                    "grid_columns": 3,
                    "intensity_map": grid,
                    "strongest_zone": self.GRID_LABELS[max_index],
                    "caption": (
                        "Fallback frame-grid heatmap derived from TRIBE segment signals. "
                        "Use with real thumbnails later without changing the JSON contract."
                    ),
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
        summary_json: dict[str, Any],
        timeline_rows: list[dict[str, Any]],
        segment_rows: list[dict[str, Any]],
        high_attention_intervals: list[dict[str, Any]],
        low_attention_intervals: list[dict[str, Any]],
        scoring_bundle: ScoringBundle,
        total_duration_ms: int,
    ) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []

        if summary_json["hook_score_first_3_seconds"] < 60.0:
            recommendations.append(
                {
                    "title": "Stronger first 2 seconds needed",
                    "detail": "Early attention is trailing. Bring the main payoff or strongest visual cue into the opening beat.",
                    "priority": "high",
                    "timestamp_ms": 0,
                    "confidence": 82.0,
                }
            )

        highest_load_segment = max(
            segment_rows,
            key=lambda row: row["engagement_delta"],
            default=None,
        )
        if highest_load_segment is not None and summary_json["cognitive_load_proxy"] > 58.0:
            recommendations.append(
                {
                    "title": f"Text density likely too high in {highest_load_segment['label'].lower()}",
                    "detail": "Reduce simultaneous message layers or compress copy in the segment where effort spikes.",
                    "priority": "medium",
                    "timestamp_ms": highest_load_segment["start_time_ms"],
                    "confidence": 76.0,
                }
            )

        if high_attention_intervals:
            strongest_interval = max(
                high_attention_intervals,
                key=lambda interval: float(interval["average_attention_score"]),
            )
            recommendations.append(
                {
                    "title": f"Strongest retention moment occurs near {self._format_ms(strongest_interval['start_time_ms'])}",
                    "detail": "Use this peak as the reference point for CTA placement, product proof, or brand reinforcement.",
                    "priority": "medium",
                    "timestamp_ms": strongest_interval["start_time_ms"],
                    "confidence": round(strongest_interval["average_attention_score"], 2),
                }
            )
            if total_duration_ms > 0 and strongest_interval["start_time_ms"] > total_duration_ms * 0.65:
                recommendations.append(
                    {
                        "title": "CTA appears too late",
                        "detail": "The strongest attention window lands near the end. Test bringing the CTA or offer forward.",
                        "priority": "high",
                        "timestamp_ms": strongest_interval["start_time_ms"],
                        "confidence": 79.0,
                    }
                )

        if low_attention_intervals:
            weakest_interval = low_attention_intervals[0]
            recommendations.append(
                {
                    "title": f"Attention drops around {self._format_ms(weakest_interval['start_time_ms'])}",
                    "detail": "Rework pacing or reduce friction in this interval to prevent mid-stream falloff.",
                    "priority": "medium",
                    "timestamp_ms": weakest_interval["start_time_ms"],
                    "confidence": round(100.0 - weakest_interval["average_attention_score"], 2),
                }
            )

        for suggestion in scoring_bundle.suggestions[:2]:
            recommendations.append(
                {
                    "title": suggestion.title,
                    "detail": suggestion.rationale,
                    "priority": "medium",
                    "timestamp_ms": None,
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

    def _build_segment_note(self, *, attention_score: float, engagement_delta: float, event_count: int) -> str:
        if attention_score >= 75.0:
            return "High-attention moment. Use this section for proof, offer framing, or CTA reinforcement."
        if engagement_delta <= -12.0:
            return "Engagement falls off here. Tighten pacing or simplify competing signals."
        if event_count >= 12:
            return "Dense event cluster detected. Watch for overload or visual clutter."
        return "Stable segment suitable for comparison against adjacent scenes."

    def _build_summary_notes(
        self,
        *,
        overall_attention_score: float,
        hook_score: float,
        sustained_engagement_score: float,
        cognitive_load_proxy: float,
    ) -> list[str]:
        notes: list[str] = []
        if hook_score < 60.0:
            notes.append("Opening hook is weaker than target for the first 3 seconds.")
        if sustained_engagement_score >= 70.0:
            notes.append("Mid-to-late timeline holds attention well after the opening beat.")
        if overall_attention_score >= 75.0:
            notes.append("Overall attention profile is strong enough to support earlier CTA testing.")
        if cognitive_load_proxy > 58.0:
            notes.append("Cognitive load is elevated. Simplifying message density may improve retention.")
        return notes

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

    def _format_ms(self, value: int) -> str:
        seconds = max(0, int(value // 1000))
        minutes = seconds // 60
        remainder = seconds % 60
        return f"{minutes}:{remainder:02d}"
