from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------

class OrgRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class AssetType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    HTML = "html"
    URL = "url"


class CreativeStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    ARCHIVED = "archived"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class ModelKind(str, enum.Enum):
    FOUNDATION = "foundation"
    SCORING = "scoring"
    CALIBRATION = "calibration"
    OUTCOME = "outcome"
    GENERATIVE = "generative"


class PredictionType(str, enum.Enum):
    SINGLE_ASSET = "single_asset"
    COMPARISON = "comparison"
    OPTIMIZATION = "optimization"
    BATCH = "batch"


class ScoreType(str, enum.Enum):
    ATTENTION = "attention"
    EMOTION = "emotion"
    MEMORY = "memory"
    COGNITIVE_LOAD = "cognitive_load"
    CONVERSION_PROXY = "conversion_proxy"
    BRAND_CLARITY = "brand_clarity"
    CTA_CLARITY = "cta_clarity"
    NOVELTY = "novelty"
    FATIGUE_RISK = "fatigue_risk"


class VisualizationType(str, enum.Enum):
    HEATMAP = "heatmap"
    TIMELINE = "timeline"
    SALIENCY = "saliency"
    FRAME_GRID = "frame_grid"
    BRAIN_REGION_SUMMARY = "brain_region_summary"


class SuggestionType(str, enum.Enum):
    COPY = "copy"
    LAYOUT = "layout"
    COLOR = "color"
    CTA = "cta"
    FRAMING = "framing"
    PACING = "pacing"
    THUMBNAIL = "thumbnail"
    BRANDING = "branding"


class SuggestionStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"


class OutcomeMetricType(str, enum.Enum):
    CTR = "ctr"
    CVR = "cvr"
    CPC = "cpc"
    CPA = "cpa"
    ROAS = "roas"
    WATCH_TIME = "watch_time"
    THUMB_STOP_RATE = "thumb_stop_rate"
    COMPLETION_RATE = "completion_rate"
    BOUNCE_RATE = "bounce_rate"
    SCROLL_DEPTH = "scroll_depth"


class ApiKeyStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


# ---------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


# ---------------------------------------------------------------------
# Core org / auth / tenancy
# ---------------------------------------------------------------------

class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    billing_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    users: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column("hashed_password", String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_projects: Mapped[list["Project"]] = relationship(
        back_populates="created_by_user", foreign_keys="Project.created_by_user_id"
    )
    created_creatives: Mapped[list["Creative"]] = relationship(
        back_populates="created_by_user", foreign_keys="Creative.created_by_user_id"
    )
    created_jobs: Mapped[list["InferenceJob"]] = relationship(
        back_populates="created_by_user", foreign_keys="InferenceJob.created_by_user_id"
    )

    @property
    def full_name(self) -> str | None:
        parts = [part for part in [self.first_name, self.last_name] if part]
        return " ".join(parts) if parts else None


class OrganizationMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_user_membership"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[OrgRole] = mapped_column(
        Enum(OrgRole, name="org_role"), nullable=False
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")
    user: Mapped["User"] = relationship(back_populates="memberships")


class ApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[ApiKeyStatus] = mapped_column(
        Enum(ApiKeyStatus, name="api_key_status"), nullable=False, default=ApiKeyStatus.ACTIVE
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    organization: Mapped["Organization"] = relationship(back_populates="api_keys")


# ---------------------------------------------------------------------
# Project / campaign structure
# ---------------------------------------------------------------------

class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_org_name", "organization_id", "name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    organization: Mapped["Organization"] = relationship(back_populates="projects")
    created_by_user: Mapped[Optional["User"]] = relationship(back_populates="created_projects")
    creatives: Mapped[list["Creative"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    comparisons: Mapped[list["CreativeComparison"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    feedback_events: Mapped[list["OutcomeEvent"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_project_name", "project_id", "name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    audience_definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    project: Mapped["Project"] = relationship()


# ---------------------------------------------------------------------
# Assets / creatives
# ---------------------------------------------------------------------

class Creative(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "creatives"
    __table_args__ = (
        Index("ix_creatives_project_status", "project_id", "status"),
        Index("ix_creatives_project_name", "project_id", "name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type"), nullable=False
    )
    status: Mapped[CreativeStatus] = mapped_column(
        Enum(CreativeStatus, name="creative_status"), nullable=False, default=CreativeStatus.DRAFT
    )
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="creatives")
    created_by_user: Mapped[Optional["User"]] = relationship(back_populates="created_creatives")
    versions: Mapped[list["CreativeVersion"]] = relationship(
        back_populates="creative", cascade="all, delete-orphan", order_by="CreativeVersion.version_number"
    )
    jobs: Mapped[list["InferenceJob"]] = relationship(
        back_populates="creative", cascade="all, delete-orphan"
    )
    outcomes: Mapped[list["OutcomeEvent"]] = relationship(
        back_populates="creative", cascade="all, delete-orphan"
    )


class CreativeVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "creative_versions"
    __table_args__ = (
        UniqueConstraint("creative_id", "version_number", name="uq_creative_version_number"),
        Index("ix_creative_versions_creative_latest", "creative_id", "is_current"),
    )

    creative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creatives.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Storage / content
    source_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Text / URL specific
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    html_snapshot_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Media metadata
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    width_px: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height_px: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    frame_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 3), nullable=True)

    # Flexible structured fields
    extracted_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    preprocessing_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    creative: Mapped["Creative"] = relationship(back_populates="versions")
    precomputed_embeddings: Mapped[list["AssetEmbedding"]] = relationship(
        back_populates="creative_version", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["InferenceJob"]] = relationship(
        back_populates="creative_version", cascade="all, delete-orphan"
    )


class AssetEmbedding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_embeddings"
    __table_args__ = (
        Index("ix_asset_embeddings_version_kind", "creative_version_id", "embedding_kind"),
        UniqueConstraint(
            "creative_version_id", "embedding_kind", "model_name",
            name="uq_asset_embedding_version_kind_model"
        ),
    )

    creative_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_versions.id", ondelete="CASCADE"), nullable=False
    )
    embedding_kind: Mapped[str] = mapped_column(String(50), nullable=False)  # image, video, audio, text, multimodal
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    vector_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vector_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    creative_version: Mapped["CreativeVersion"] = relationship(back_populates="precomputed_embeddings")


# ---------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------

class ModelRegistry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_registry"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_model_name_version"),
        Index("ix_model_registry_kind_active", "kind", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[ModelKind] = mapped_column(
        Enum(ModelKind, name="model_kind"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    artifact_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------
# Inference jobs / predictions
# ---------------------------------------------------------------------

class InferenceJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "inference_jobs"
    __table_args__ = (
        Index("ix_inference_jobs_project_status", "project_id", "status"),
        Index("ix_inference_jobs_creative_status", "creative_id", "status"),
        Index("ix_inference_jobs_created_at", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    creative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creatives.id", ondelete="CASCADE"), nullable=False
    )
    creative_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_versions.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    prediction_type: Mapped[PredictionType] = mapped_column(
        Enum(PredictionType, name="prediction_type"), nullable=False, default=PredictionType.SINGLE_ASSET
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False, default=JobStatus.QUEUED
    )

    tribe_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="SET NULL"), nullable=True
    )
    scoring_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="SET NULL"), nullable=True
    )
    calibration_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_registry.id", ondelete="SET NULL"), nullable=True
    )

    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    runtime_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship()
    creative: Mapped["Creative"] = relationship(back_populates="jobs")
    creative_version: Mapped["CreativeVersion"] = relationship(back_populates="jobs")
    created_by_user: Mapped[Optional["User"]] = relationship(back_populates="created_jobs")
    tribe_model: Mapped[Optional["ModelRegistry"]] = relationship(foreign_keys=[tribe_model_id])
    scoring_model: Mapped[Optional["ModelRegistry"]] = relationship(foreign_keys=[scoring_model_id])
    calibration_model: Mapped[Optional["ModelRegistry"]] = relationship(foreign_keys=[calibration_model_id])

    prediction: Mapped[Optional["PredictionResult"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    analysis_result_record: Mapped[Optional["AnalysisResultRecord"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    llm_evaluations: Mapped[list["LLMEvaluationRecord"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["JobMetric"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_metrics"
    __table_args__ = (
        Index("ix_job_metrics_job_name", "job_id", "metric_name"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inference_jobs.id", ondelete="CASCADE"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    metric_unit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    job: Mapped["InferenceJob"] = relationship(back_populates="metrics")


class PredictionResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prediction_results"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_prediction_result_job"),
        Index("ix_prediction_results_project_created_at", "project_id", "created_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inference_jobs.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    creative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creatives.id", ondelete="CASCADE"), nullable=False
    )
    creative_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_versions.id", ondelete="CASCADE"), nullable=False
    )

    # Raw TRIBE or intermediate outputs
    raw_brain_response_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_brain_response_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reduced_feature_vector: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    region_activation_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Explainability / provenance
    provenance_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    job: Mapped["InferenceJob"] = relationship(back_populates="prediction")
    scores: Mapped[list["PredictionScore"]] = relationship(
        back_populates="prediction_result", cascade="all, delete-orphan"
    )
    visualizations: Mapped[list["PredictionVisualization"]] = relationship(
        back_populates="prediction_result", cascade="all, delete-orphan"
    )
    timeline_points: Mapped[list["PredictionTimelinePoint"]] = relationship(
        back_populates="prediction_result", cascade="all, delete-orphan"
    )
    suggestions: Mapped[list["OptimizationSuggestion"]] = relationship(
        back_populates="prediction_result", cascade="all, delete-orphan"
    )


class AnalysisResultRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_analysis_result_job"),
        Index("ix_analysis_results_job_created_at", "job_id", "created_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inference_jobs.id", ondelete="CASCADE"), nullable=False
    )
    summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    timeline_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    segments_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    visualizations_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    recommendations_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    job: Mapped["InferenceJob"] = relationship(back_populates="analysis_result_record")


class LLMEvaluationRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "llm_evaluations"
    __table_args__ = (
        UniqueConstraint("job_id", "mode", name="uq_llm_evaluations_job_mode"),
        Index("ix_llm_evaluations_job_status", "job_id", "status"),
        Index("ix_llm_evaluations_user_created_at", "user_id", "created_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inference_jobs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    model_provider: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    input_snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evaluation_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job: Mapped["InferenceJob"] = relationship(back_populates="llm_evaluations")


class PredictionScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prediction_scores"
    __table_args__ = (
        UniqueConstraint("prediction_result_id", "score_type", name="uq_prediction_score_type"),
        Index("ix_prediction_scores_type_value", "score_type", "normalized_score"),
    )

    prediction_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_results.id", ondelete="CASCADE"), nullable=False
    )
    score_type: Mapped[ScoreType] = mapped_column(
        Enum(ScoreType, name="score_type"), nullable=False
    )

    # Standardized 0-100 score for UI
    normalized_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)

    # Raw model value before calibration / normalization
    raw_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)

    # Confidence / uncertainty
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    percentile: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)

    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    prediction_result: Mapped["PredictionResult"] = relationship(back_populates="scores")


class PredictionVisualization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prediction_visualizations"
    __table_args__ = (
        Index("ix_prediction_visualizations_type", "prediction_result_id", "visualization_type"),
    )

    prediction_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_results.id", ondelete="CASCADE"), nullable=False
    )
    visualization_type: Mapped[VisualizationType] = mapped_column(
        Enum(VisualizationType, name="visualization_type"), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    storage_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    prediction_result: Mapped["PredictionResult"] = relationship(back_populates="visualizations")


class PredictionTimelinePoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prediction_timeline_points"
    __table_args__ = (
        Index("ix_prediction_timeline_points_result_time", "prediction_result_id", "timestamp_ms"),
    )

    prediction_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_results.id", ondelete="CASCADE"), nullable=False
    )
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    attention_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    emotion_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    memory_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    cognitive_load_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    conversion_proxy_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)

    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    prediction_result: Mapped["PredictionResult"] = relationship(back_populates="timeline_points")


# ---------------------------------------------------------------------
# Optimization / recommendations
# ---------------------------------------------------------------------

class OptimizationSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "optimization_suggestions"
    __table_args__ = (
        Index("ix_optimization_suggestions_result_status", "prediction_result_id", "status"),
    )

    prediction_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_results.id", ondelete="CASCADE"), nullable=False
    )
    suggestion_type: Mapped[SuggestionType] = mapped_column(
        Enum(SuggestionType, name="suggestion_type"), nullable=False
    )
    status: Mapped[SuggestionStatus] = mapped_column(
        Enum(SuggestionStatus, name="suggestion_status"), nullable=False, default=SuggestionStatus.PROPOSED
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_change_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    expected_score_lift_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)

    prediction_result: Mapped["PredictionResult"] = relationship(back_populates="suggestions")


class GeneratedVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generated_variants"
    __table_args__ = (
        Index("ix_generated_variants_parent_version", "parent_creative_version_id"),
    )

    parent_creative_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_versions.id", ondelete="CASCADE"), nullable=False
    )
    optimization_suggestion_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("optimization_suggestions.id", ondelete="SET NULL"), nullable=True
    )

    source_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    was_promoted_to_creative_version: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# ---------------------------------------------------------------------
# A/B and multi-creative comparison
# ---------------------------------------------------------------------

class CreativeComparison(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "creative_comparisons"
    __table_args__ = (
        Index("ix_creative_comparisons_project_name", "project_id", "name"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comparison_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="comparisons")
    items: Mapped[list["CreativeComparisonItem"]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan"
    )
    result: Mapped[Optional["CreativeComparisonResult"]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan", uselist=False
    )


class CreativeComparisonItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "creative_comparison_items"
    __table_args__ = (
        UniqueConstraint(
            "comparison_id", "creative_version_id", name="uq_comparison_version"
        ),
        Index("ix_creative_comparison_items_rank", "comparison_id", "candidate_rank"),
    )

    comparison_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_comparisons.id", ondelete="CASCADE"), nullable=False
    )
    creative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creatives.id", ondelete="CASCADE"), nullable=False
    )
    creative_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_versions.id", ondelete="CASCADE"), nullable=False
    )
    candidate_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    comparison: Mapped["CreativeComparison"] = relationship(back_populates="items")


class CreativeComparisonResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "creative_comparison_results"
    __table_args__ = (
        UniqueConstraint("comparison_id", name="uq_comparison_result_comparison"),
    )

    comparison_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_comparisons.id", ondelete="CASCADE"), nullable=False
    )
    winning_creative_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_versions.id", ondelete="SET NULL"), nullable=True
    )
    summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    comparison: Mapped["CreativeComparison"] = relationship(back_populates="result")
    item_results: Mapped[list["CreativeComparisonItemResult"]] = relationship(
        back_populates="comparison_result", cascade="all, delete-orphan"
    )


class CreativeComparisonItemResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "creative_comparison_item_results"
    __table_args__ = (
        UniqueConstraint(
            "comparison_result_id", "creative_version_id",
            name="uq_comparison_item_result_version"
        ),
    )

    comparison_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_comparison_results.id", ondelete="CASCADE"), nullable=False
    )
    creative_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_versions.id", ondelete="CASCADE"), nullable=False
    )
    overall_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    scores_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    comparison_result: Mapped["CreativeComparisonResult"] = relationship(back_populates="item_results")


# ---------------------------------------------------------------------
# Ground-truth / feedback loop
# ---------------------------------------------------------------------

class OutcomeEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outcome_events"
    __table_args__ = (
        Index("ix_outcome_events_project_metric", "project_id", "metric_type"),
        Index("ix_outcome_events_creative_metric", "creative_id", "metric_type"),
        Index("ix_outcome_events_observed_at", "observed_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    creative_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creatives.id", ondelete="SET NULL"), nullable=True
    )
    creative_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creative_versions.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )

    metric_type: Mapped[OutcomeMetricType] = mapped_column(
        Enum(OutcomeMetricType, name="outcome_metric_type"), nullable=False
    )
    metric_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    metric_unit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source_system: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    source_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dimensions_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="feedback_events")
    creative: Mapped[Optional["Creative"]] = relationship(back_populates="outcomes")


class CalibrationObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "calibration_observations"
    __table_args__ = (
        Index("ix_calibration_observations_score_type", "score_type"),
        Index("ix_calibration_observations_metric_type", "metric_type"),
    )

    prediction_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_results.id", ondelete="CASCADE"), nullable=False
    )
    outcome_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outcome_events.id", ondelete="CASCADE"), nullable=False
    )
    score_type: Mapped[ScoreType] = mapped_column(
        Enum(ScoreType, name="calibration_score_type"), nullable=False
    )
    predicted_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    metric_type: Mapped[OutcomeMetricType] = mapped_column(
        Enum(OutcomeMetricType, name="calibration_metric_type"), nullable=False
    )
    actual_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


# ---------------------------------------------------------------------
# Optional audit / webhook support
# ---------------------------------------------------------------------

class WebhookEndpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        Index("ix_webhook_endpoints_org_active", "organization_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    subscribed_events: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created_at", "organization_id", "created_at"),
        Index("ix_audit_logs_actor_created_at", "actor_user_id", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


# ---------------------------------------------------------------------
# Upload sessions / stored artifacts
# ---------------------------------------------------------------------

class UploadStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    STORED = "stored"
    FAILED = "failed"


class StoredArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stored_artifacts"
    __table_args__ = (
        Index("ix_stored_artifacts_project_kind", "project_id", "artifact_kind"),
        Index("ix_stored_artifacts_user_status", "created_by_user_id", "upload_status"),
        Index("ix_stored_artifacts_storage_key", "storage_key"),
        UniqueConstraint("bucket_name", "storage_key", name="uq_artifact_bucket_key"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    creative_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creatives.id", ondelete="SET NULL"),
        nullable=True,
    )
    creative_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creative_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    artifact_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    bucket_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)

    original_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    upload_status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status"),
        nullable=False,
        default=UploadStatus.PENDING,
    )

    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class UploadSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        Index("ix_upload_sessions_project_status", "project_id", "status"),
        Index("ix_upload_sessions_user_status", "created_by_user_id", "status"),
        UniqueConstraint("upload_token", name="uq_upload_sessions_token"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    creative_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creatives.id", ondelete="SET NULL"),
        nullable=True,
    )
    creative_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creative_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    upload_token: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status"),
        nullable=False,
        default=UploadStatus.PENDING,
    )

    bucket_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    expected_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    uploaded_artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stored_artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
