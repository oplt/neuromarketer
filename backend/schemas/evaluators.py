from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvaluationMode(str, enum.Enum):
    EDUCATIONAL = "educational"
    DEFENCE = "defence"
    MARKETING = "marketing"
    SOCIAL_MEDIA = "social_media"


class EvaluationStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StrictSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskItem(StrictSchemaModel):
    severity: Severity
    label: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1_000)
    timestamp_start: float | None = Field(default=None, ge=0)
    timestamp_end: float | None = Field(default=None, ge=0)


class RecommendationItem(StrictSchemaModel):
    priority: Priority
    action: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=1_000)
    timestamp_start: float | None = Field(default=None, ge=0)
    timestamp_end: float | None = Field(default=None, ge=0)


class ScoreReason(StrictSchemaModel):
    score: int = Field(..., ge=0, le=100)
    reason: str = Field(min_length=1, max_length=800)


class Scores(StrictSchemaModel):
    clarity: int = Field(..., ge=0, le=100)
    engagement: int = Field(..., ge=0, le=100)
    retention: int = Field(..., ge=0, le=100)
    fit_for_purpose: int = Field(..., ge=0, le=100)
    risk: int = Field(..., ge=0, le=100)


class Scorecard(StrictSchemaModel):
    hook_or_opening: ScoreReason
    message_clarity: ScoreReason
    pacing: ScoreReason
    attention_alignment: ScoreReason
    domain_effectiveness: ScoreReason


class ModelMetadata(StrictSchemaModel):
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=200)
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)


class BaseEvaluationResult(StrictSchemaModel):
    mode: EvaluationMode
    overall_verdict: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=2_000)
    scores: Scores
    strengths: list[str] = Field(default_factory=list, max_length=8)
    weaknesses: list[str] = Field(default_factory=list, max_length=8)
    risks: list[RiskItem] = Field(default_factory=list, max_length=8)
    recommendations: list[RecommendationItem] = Field(default_factory=list, max_length=8)
    scorecard: Scorecard
    model_metadata: ModelMetadata


class EducationalEvaluationResult(BaseEvaluationResult):
    mode: Literal[EvaluationMode.EDUCATIONAL]
    educational_summary: str | None = Field(default=None, max_length=2_000)
    comprehension_risks: list[str] = Field(default_factory=list, max_length=8)
    pacing_feedback: str | None = Field(default=None, max_length=1_000)
    retention_feedback: str | None = Field(default=None, max_length=1_000)
    accessibility_feedback: str | None = Field(default=None, max_length=1_000)


class DefenceEvaluationResult(BaseEvaluationResult):
    mode: Literal[EvaluationMode.DEFENCE]
    defence_summary: str | None = Field(default=None, max_length=2_000)
    operational_clarity_assessment: str | None = Field(default=None, max_length=1_000)
    ambiguity_risks: list[str] = Field(default_factory=list, max_length=8)
    overload_risks: list[str] = Field(default_factory=list, max_length=8)
    safety_or_misuse_flags: list[str] = Field(default_factory=list, max_length=8)


class MarketingEvaluationResult(BaseEvaluationResult):
    mode: Literal[EvaluationMode.MARKETING]
    marketing_summary: str | None = Field(default=None, max_length=2_000)
    hook_assessment: str | None = Field(default=None, max_length=1_000)
    value_prop_assessment: str | None = Field(default=None, max_length=1_000)
    conversion_friction_points: list[str] = Field(default_factory=list, max_length=8)
    brand_alignment_feedback: str | None = Field(default=None, max_length=1_000)


class SocialMediaEvaluationResult(BaseEvaluationResult):
    mode: Literal[EvaluationMode.SOCIAL_MEDIA]
    social_summary: str | None = Field(default=None, max_length=2_000)
    scroll_stop_assessment: str | None = Field(default=None, max_length=1_000)
    retention_assessment: str | None = Field(default=None, max_length=1_000)
    platform_fit_feedback: str | None = Field(default=None, max_length=1_000)
    shareability_feedback: str | None = Field(default=None, max_length=1_000)


class EvaluationResult(BaseEvaluationResult):
    educational_summary: str | None = Field(default=None, max_length=2_000)
    comprehension_risks: list[str] = Field(default_factory=list, max_length=8)
    pacing_feedback: str | None = Field(default=None, max_length=1_000)
    retention_feedback: str | None = Field(default=None, max_length=1_000)
    accessibility_feedback: str | None = Field(default=None, max_length=1_000)

    defence_summary: str | None = Field(default=None, max_length=2_000)
    operational_clarity_assessment: str | None = Field(default=None, max_length=1_000)
    ambiguity_risks: list[str] = Field(default_factory=list, max_length=8)
    overload_risks: list[str] = Field(default_factory=list, max_length=8)
    safety_or_misuse_flags: list[str] = Field(default_factory=list, max_length=8)

    marketing_summary: str | None = Field(default=None, max_length=2_000)
    hook_assessment: str | None = Field(default=None, max_length=1_000)
    value_prop_assessment: str | None = Field(default=None, max_length=1_000)
    conversion_friction_points: list[str] = Field(default_factory=list, max_length=8)
    brand_alignment_feedback: str | None = Field(default=None, max_length=1_000)

    social_summary: str | None = Field(default=None, max_length=2_000)
    scroll_stop_assessment: str | None = Field(default=None, max_length=1_000)
    retention_assessment: str | None = Field(default=None, max_length=1_000)
    platform_fit_feedback: str | None = Field(default=None, max_length=1_000)
    shareability_feedback: str | None = Field(default=None, max_length=1_000)


class EvaluationDispatchRequest(StrictSchemaModel):
    modes: list[EvaluationMode] = Field(min_length=1, max_length=4)
    force_refresh: bool = False

    @field_validator("modes")
    @classmethod
    def _deduplicate_modes(cls, value: list[EvaluationMode]) -> list[EvaluationMode]:
        deduplicated = list(dict.fromkeys(value))
        if not deduplicated:
            raise ValueError("At least one evaluation mode is required.")
        return deduplicated


class EvaluationRecordRead(StrictSchemaModel):
    id: UUID
    job_id: UUID
    user_id: UUID
    mode: EvaluationMode
    status: EvaluationStatus
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    evaluation_json: EvaluationResult | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class EvaluationListResponse(StrictSchemaModel):
    items: list[EvaluationRecordRead] = Field(default_factory=list)


def evaluation_json_schema(mode: EvaluationMode | None = None) -> dict[str, Any]:
    if mode is None:
        return EvaluationResult.model_json_schema()

    model_by_mode = {
        EvaluationMode.EDUCATIONAL: EducationalEvaluationResult,
        EvaluationMode.DEFENCE: DefenceEvaluationResult,
        EvaluationMode.MARKETING: MarketingEvaluationResult,
        EvaluationMode.SOCIAL_MEDIA: SocialMediaEvaluationResult,
    }
    return model_by_mode[mode].model_json_schema()
