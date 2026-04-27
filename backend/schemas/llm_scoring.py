from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from backend.schemas.base import StrictSchemaModel


class MetricAssessment(StrictSchemaModel):
    score: int = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0, le=1)
    reason: str = Field(min_length=1, max_length=1_000)
    evidence: list[str] = Field(default_factory=list, max_length=4)


class MetricAssessments(StrictSchemaModel):
    attention: MetricAssessment
    emotion: MetricAssessment
    memory: MetricAssessment
    cognitive_load: MetricAssessment
    conversion_proxy: MetricAssessment


class TimelineMetricPoint(StrictSchemaModel):
    segment_index: int = Field(..., ge=0)
    timestamp_ms: int = Field(..., ge=0)
    attention_score: int = Field(..., ge=0, le=100)
    emotion_score: int = Field(..., ge=0, le=100)
    memory_score: int = Field(..., ge=0, le=100)
    cognitive_load_score: int = Field(..., ge=0, le=100)
    conversion_proxy_score: int = Field(..., ge=0, le=100)
    rationale: str | None = Field(default=None, max_length=500)


class ScoringSuggestion(StrictSchemaModel):
    suggestion_type: Literal[
        "copy", "layout", "color", "cta", "framing", "pacing", "thumbnail", "branding"
    ]
    title: str = Field(min_length=1, max_length=180)
    rationale: str = Field(min_length=1, max_length=1_000)
    proposed_change_json: dict[str, Any] = Field(default_factory=dict)
    expected_score_lift_json: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0, le=1)
    timestamp_ms: int | None = Field(default=None, ge=0)

    @field_validator("expected_score_lift_json")
    @classmethod
    def _validate_lift_keys(cls, value: dict[str, float]) -> dict[str, float]:
        allowed = {
            "attention",
            "emotion",
            "memory",
            "cognitive_load",
            "conversion_proxy",
        }
        return {key: float(metric_value) for key, metric_value in value.items() if key in allowed}


class AnalysisScoringResult(StrictSchemaModel):
    overall_summary: str = Field(min_length=1, max_length=2_000)
    notes: list[str] = Field(default_factory=list, max_length=6)
    scores: MetricAssessments
    timeline_points: list[TimelineMetricPoint] = Field(default_factory=list)
    suggestions: list[ScoringSuggestion] = Field(default_factory=list, max_length=6)
