from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.logging import get_logger, log_event
from backend.db.models import AnalysisResultRecord, CreativeVersion, InferenceJob
from backend.services.analysis_goal_taxonomy import (
    normalize_analysis_channel,
    normalize_goal_template,
)
from backend.services.asset_loader import AssetLoader

logger = get_logger(__name__)


class EvaluationContextBuilder:
    def __init__(self) -> None:
        self.asset_loader = AssetLoader()

    def build(
        self,
        *,
        job: InferenceJob,
        analysis_result: AnalysisResultRecord,
        creative_version: CreativeVersion | None = None,
    ) -> dict[str, Any]:
        summary = analysis_result.summary_json or {}
        metrics = list(analysis_result.metrics_json or [])
        timeline = list(analysis_result.timeline_json or [])
        segments = list(analysis_result.segments_json or [])
        visualizations = analysis_result.visualizations_json or {}
        recommendations = list(analysis_result.recommendations_json or [])
        resolved_creative_version = creative_version

        return {
            "job_metadata": self._build_job_metadata(
                job=job,
                summary=summary,
                creative_version=resolved_creative_version,
                analysis_created_at=analysis_result.created_at.isoformat()
                if analysis_result.created_at is not None
                else None,
            ),
            "summary_metrics": self._build_summary_metrics(summary=summary, metrics=metrics),
            "timeline_highlights": self._build_timeline_highlights(timeline=timeline),
            "best_segments": self._select_segments(segments=segments, reverse=True),
            "worst_segments": self._select_segments(segments=segments, reverse=False),
            "visualization_hints": self._build_visualization_hints(visualizations=visualizations),
            "transcript_excerpt": self._load_text_excerpt(
                creative_version=resolved_creative_version
            ),
            "existing_recommendations": self._build_recommendations(recommendations),
            "analysis_notes": list(summary.get("notes") or []),
        }

    def _build_job_metadata(
        self,
        *,
        job: InferenceJob,
        summary: dict[str, Any],
        creative_version: CreativeVersion | None,
        analysis_created_at: str | None,
    ) -> dict[str, Any]:
        summary_metadata = (
            summary.get("metadata") if isinstance(summary.get("metadata"), dict) else {}
        )
        extracted_metadata = (
            creative_version.extracted_metadata if creative_version is not None else {}
        )
        campaign_context = (job.request_payload or {}).get("campaign_context") or {}
        objective = campaign_context.get("objective")
        title = None
        if extracted_metadata:
            title = extracted_metadata.get("filename")
        if not title and creative_version and creative_version.source_uri:
            title = Path(creative_version.source_uri).name

        return {
            "job_id": str(job.id),
            "creative_version_id": str(job.creative_version_id),
            "objective": objective,
            "goal_template": normalize_goal_template(
                campaign_context.get("goal_template") or summary_metadata.get("goal_template"),
            ),
            "channel": normalize_analysis_channel(
                campaign_context.get("channel") or summary_metadata.get("channel"),
            ),
            "audience_segment": campaign_context.get("audience_segment")
            or summary_metadata.get("audience_segment"),
            "media_type": summary.get("modality")
            or (creative_version.preprocessing_summary or {}).get("modality"),
            "title": title,
            "duration_ms": summary_metadata.get("duration_ms")
            or extracted_metadata.get("duration_ms"),
            "segment_count": summary_metadata.get("segment_count"),
            "source_label": summary_metadata.get("source_label"),
            "language": extracted_metadata.get("language"),
            "mime_type": creative_version.mime_type if creative_version is not None else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "analysis_created_at": analysis_created_at,
        }

    def _build_summary_metrics(
        self, *, summary: dict[str, Any], metrics: list[dict[str, Any]]
    ) -> dict[str, Any]:
        condensed_metrics: list[dict[str, Any]] = []
        for metric in metrics[:10]:
            condensed_metrics.append(
                {
                    "key": metric.get("key"),
                    "label": metric.get("label"),
                    "value": metric.get("value"),
                    "unit": metric.get("unit"),
                    "detail": metric.get("detail"),
                }
            )

        return {
            "overall_attention_score": summary.get("overall_attention_score"),
            "hook_score_first_3_seconds": summary.get("hook_score_first_3_seconds"),
            "sustained_engagement_score": summary.get("sustained_engagement_score"),
            "memory_proxy_score": summary.get("memory_proxy_score"),
            "cognitive_load_proxy": summary.get("cognitive_load_proxy"),
            "confidence": summary.get("confidence"),
            "completeness": summary.get("completeness"),
            "metric_rows": condensed_metrics,
        }

    def _build_timeline_highlights(self, *, timeline: list[dict[str, Any]]) -> dict[str, Any]:
        def _window_average(items: list[dict[str, Any]], key: str) -> float | None:
            values = [float(item.get(key) or 0.0) for item in items if item.get(key) is not None]
            if not values:
                return None
            return round(sum(values) / len(values), 2)

        opening = [item for item in timeline if int(item.get("timestamp_ms") or 0) < 3_000]
        midpoint = timeline[len(timeline) // 3 : (len(timeline) * 2) // 3] if timeline else []
        closing = timeline[-3:] if len(timeline) >= 3 else timeline
        strongest = sorted(
            timeline, key=lambda item: float(item.get("attention_score") or 0.0), reverse=True
        )[:4]
        weakest = sorted(timeline, key=lambda item: float(item.get("attention_score") or 0.0))[:4]

        def _condense(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [
                {
                    "timestamp_ms": item.get("timestamp_ms"),
                    "engagement_score": item.get("engagement_score"),
                    "attention_score": item.get("attention_score"),
                    "memory_proxy": item.get("memory_proxy"),
                }
                for item in items
            ]

        return {
            "opening_window": {
                "avg_attention": _window_average(opening, "attention_score"),
                "avg_engagement": _window_average(opening, "engagement_score"),
            },
            "midpoint_window": {
                "avg_attention": _window_average(midpoint, "attention_score"),
                "avg_engagement": _window_average(midpoint, "engagement_score"),
            },
            "closing_window": {
                "avg_attention": _window_average(closing, "attention_score"),
                "avg_engagement": _window_average(closing, "engagement_score"),
            },
            "peak_attention_points": _condense(strongest),
            "lowest_attention_points": _condense(weakest),
        }

    def _select_segments(
        self, *, segments: list[dict[str, Any]], reverse: bool
    ) -> list[dict[str, Any]]:
        ranked = sorted(
            segments,
            key=lambda item: (
                float(item.get("attention_score") or 0.0),
                float(item.get("engagement_delta") or 0.0),
            ),
            reverse=reverse,
        )
        return [
            {
                "label": segment.get("label"),
                "segment_index": segment.get("segment_index"),
                "timestamp_start": segment.get("start_time_ms"),
                "timestamp_end": segment.get("end_time_ms"),
                "attention_score": segment.get("attention_score"),
                "engagement_delta": segment.get("engagement_delta"),
                "note": segment.get("note"),
            }
            for segment in ranked[:4]
        ]

    def _build_visualization_hints(self, *, visualizations: dict[str, Any]) -> dict[str, Any]:
        return {
            "high_attention_intervals": list(visualizations.get("high_attention_intervals") or [])[
                :4
            ],
            "low_attention_intervals": list(visualizations.get("low_attention_intervals") or [])[
                :4
            ],
            "keyframe_descriptors": [
                {
                    "timestamp_ms": frame.get("timestamp_ms"),
                    "label": frame.get("label"),
                    "scene_label": frame.get("scene_label"),
                    "strongest_zone": frame.get("strongest_zone"),
                    "caption": frame.get("caption"),
                }
                for frame in list(visualizations.get("heatmap_frames") or [])[:4]
            ],
        }

    def _build_recommendations(self, recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "title": recommendation.get("title"),
                "detail": recommendation.get("detail"),
                "priority": recommendation.get("priority"),
                "timestamp_ms": recommendation.get("timestamp_ms"),
                "confidence": recommendation.get("confidence"),
            }
            for recommendation in recommendations[:6]
        ]

    def _load_text_excerpt(self, *, creative_version: CreativeVersion | None) -> str | None:
        if creative_version is None:
            return None
        if creative_version.raw_text and creative_version.raw_text.strip():
            return creative_version.raw_text.strip()[:1_600]

        modality = (creative_version.preprocessing_summary or {}).get("modality")
        mime_type = creative_version.mime_type or ""
        if modality != "text" and not mime_type.startswith("text/"):
            return None
        if not creative_version.source_uri:
            return None

        loaded_asset = None
        try:
            loaded_asset = self.asset_loader.load(
                storage_uri=creative_version.source_uri,
                mime_type=creative_version.mime_type,
            )
            excerpt = (
                Path(loaded_asset.local_path).read_text(encoding="utf-8", errors="ignore").strip()
            )
            return excerpt[:1_600] or None
        except Exception as exc:
            log_event(
                logger,
                "llm_context_text_excerpt_failed",
                level="warning",
                creative_version_id=str(creative_version.id),
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                status="failed",
            )
            return None
        finally:
            if loaded_asset is not None:
                loaded_asset.cleanup()
