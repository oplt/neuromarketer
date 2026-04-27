from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.base import APIBaseSchema, ORMBaseSchema

# ---------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "neuromarketing-api"
    version: str = "0.3.0"
    dependencies: dict[str, str] = Field(default_factory=dict)


class SignUpRequest(APIBaseSchema):
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class SignInRequest(APIBaseSchema):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class AuthUserRead(BaseModel):
    id: UUID
    email: str
    full_name: str | None = None


class AuthOrganizationRead(BaseModel):
    id: UUID
    name: str
    slug: str


class AuthProjectRead(BaseModel):
    id: UUID
    name: str


class AuthResponse(BaseModel):
    message: str
    user: AuthUserRead
    organization: AuthOrganizationRead | None = None
    default_project: AuthProjectRead | None = None
    session_token: str | None = None
    requires_mfa: bool = False
    mfa_challenge_token: str | None = None
    available_mfa_methods: list[str] = Field(default_factory=list)

    @classmethod
    def from_user_and_org(
        cls,
        *,
        message: str,
        user: Any,
        organization: Any | None,
        default_project: Any | None = None,
        session_token: str | None = None,
    ) -> AuthResponse:
        return cls(
            message=message,
            user=AuthUserRead(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
            ),
            organization=(
                AuthOrganizationRead(
                    id=organization.id,
                    name=organization.name,
                    slug=organization.slug,
                )
                if organization is not None
                else None
            ),
            default_project=(
                AuthProjectRead(
                    id=default_project.id,
                    name=default_project.name,
                )
                if default_project is not None
                else None
            ),
            session_token=session_token,
        )


class MfaChallengeVerifyRequest(APIBaseSchema):
    challenge_token: str = Field(min_length=16)
    code: str | None = Field(default=None, min_length=6, max_length=16)
    recovery_code: str | None = Field(default=None, min_length=6, max_length=32)


class InvitePreviewRead(BaseModel):
    workspace_name: str
    workspace_slug: str
    email: str
    role: Literal["owner", "admin", "member", "viewer"]
    expires_at: datetime


class AcceptInviteRequest(APIBaseSchema):
    invite_token: str = Field(min_length=16)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------------
# Organization / Project / Creative
# ---------------------------------------------------------------------


class ProjectCreate(APIBaseSchema):
    organization_id: UUID
    created_by_user_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    external_ref: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectRead(ORMBaseSchema):
    id: UUID
    organization_id: UUID
    created_by_user_id: UUID | None
    name: str
    description: str | None
    external_ref: str | None
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CreativeCreate(APIBaseSchema):
    project_id: UUID
    created_by_user_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    asset_type: Literal["image", "video", "audio", "text", "html", "url"]
    tags: list[str] = Field(default_factory=list, max_length=50)
    metadata_json: dict[str, Any] = Field(default_factory=dict, max_length=50)


class CreativeRead(ORMBaseSchema):
    id: UUID
    project_id: UUID
    created_by_user_id: UUID | None
    name: str
    asset_type: str
    status: str
    tags: list[Any]
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CreativeVersionCreate(APIBaseSchema):
    creative_id: UUID
    version_number: int = Field(ge=1)
    is_current: bool = True

    source_uri: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = None

    raw_text: str | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    html_snapshot_uri: str | None = None

    duration_ms: int | None = Field(default=None, ge=0)
    width_px: int | None = Field(default=None, ge=0)
    height_px: int | None = Field(default=None, ge=0)
    frame_rate: Decimal | None = None

    extracted_metadata: dict[str, Any] = Field(default_factory=dict, max_length=100)
    preprocessing_summary: dict[str, Any] = Field(default_factory=dict, max_length=100)


class CreativeVersionRead(ORMBaseSchema):
    id: UUID
    creative_id: UUID
    version_number: int
    is_current: bool
    source_uri: str | None
    mime_type: str | None
    file_size_bytes: int | None
    sha256: str | None
    raw_text: str | None
    source_url: str | None
    html_snapshot_uri: str | None
    duration_ms: int | None
    width_px: int | None
    height_px: int | None
    frame_rate: Decimal | None
    extracted_metadata: dict[str, Any]
    preprocessing_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------
# Predict / Compare / Optimize requests
# ---------------------------------------------------------------------


class PredictRequest(APIBaseSchema):
    project_id: UUID
    creative_id: UUID
    creative_version_id: UUID
    created_by_user_id: UUID | None = None
    audience_context: dict[str, Any] = Field(default_factory=dict, max_length=50)
    campaign_context: dict[str, Any] = Field(default_factory=dict, max_length=50)
    runtime_params: dict[str, Any] = Field(default_factory=dict, max_length=100)


class CompareRequest(APIBaseSchema):
    project_id: UUID
    name: str
    creative_version_ids: list[UUID] = Field(min_length=2)
    comparison_context: dict[str, Any] = Field(default_factory=dict, max_length=50)


class OptimizeRequest(APIBaseSchema):
    prediction_result_id: UUID
    max_suggestions: int = Field(default=5, ge=1, le=20)
    constraints: dict[str, Any] = Field(default_factory=dict, max_length=50)


# ---------------------------------------------------------------------
# Scores / visualizations / suggestions
# ---------------------------------------------------------------------


class PredictionScoreRead(ORMBaseSchema):
    id: UUID
    prediction_result_id: UUID
    score_type: str
    normalized_score: Decimal
    raw_value: Decimal | None
    confidence: Decimal | None
    percentile: Decimal | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PredictionVisualizationRead(ORMBaseSchema):
    id: UUID
    prediction_result_id: UUID
    visualization_type: str
    title: str | None
    storage_uri: str | None
    data_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PredictionTimelinePointRead(ORMBaseSchema):
    id: UUID
    prediction_result_id: UUID
    timestamp_ms: int
    attention_score: Decimal | None
    emotion_score: Decimal | None
    memory_score: Decimal | None
    cognitive_load_score: Decimal | None
    conversion_proxy_score: Decimal | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class OptimizationSuggestionRead(ORMBaseSchema):
    id: UUID
    prediction_result_id: UUID
    suggestion_type: str
    status: str
    title: str
    rationale: str
    proposed_change_json: dict[str, Any]
    expected_score_lift_json: dict[str, Any]
    confidence: Decimal | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------
# Prediction result payloads
# ---------------------------------------------------------------------


class PredictionResultRead(ORMBaseSchema):
    id: UUID
    job_id: UUID
    project_id: UUID
    creative_id: UUID
    creative_version_id: UUID
    raw_brain_response_uri: str | None
    raw_brain_response_summary: dict[str, Any]
    reduced_feature_vector: dict[str, Any]
    region_activation_summary: dict[str, Any]
    provenance_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    scores: list[PredictionScoreRead] = Field(default_factory=list)
    visualizations: list[PredictionVisualizationRead] = Field(default_factory=list)
    timeline_points: list[PredictionTimelinePointRead] = Field(default_factory=list)
    suggestions: list[OptimizationSuggestionRead] = Field(default_factory=list)


class JobMetricRead(ORMBaseSchema):
    id: UUID
    job_id: UUID
    metric_name: str
    metric_value: Decimal
    metric_unit: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class InferenceJobRead(ORMBaseSchema):
    id: UUID
    project_id: UUID
    creative_id: UUID
    creative_version_id: UUID
    created_by_user_id: UUID | None
    prediction_type: str
    status: str
    request_payload: dict[str, Any]
    runtime_params: dict[str, Any]
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PredictResponse(BaseModel):
    job: InferenceJobRead
    prediction_result: PredictionResultRead | None = None


class CompareItemResponse(BaseModel):
    creative_version_id: UUID
    overall_rank: int
    scores_json: dict[str, Any]
    rationale: str | None = None


class CompareResponse(BaseModel):
    comparison_id: UUID
    winning_creative_version_id: UUID | None
    summary_json: dict[str, Any]
    items: list[CompareItemResponse]


class OptimizeResponse(BaseModel):
    prediction_result_id: UUID
    suggestions: list[OptimizationSuggestionRead]
