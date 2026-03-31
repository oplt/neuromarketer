from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


MediaType = Literal["video", "audio", "text"]
RecommendationPriority = Literal["high", "medium", "low"]


class AnalysisConfigResponse(BaseModel):
    max_file_size_bytes: int
    max_text_characters: int
    allowed_media_types: list[MediaType]
    allowed_mime_types: dict[MediaType, list[str]]


class AnalysisAssetRead(BaseModel):
    id: UUID
    creative_id: UUID | None = None
    creative_version_id: UUID | None = None
    media_type: MediaType
    original_filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    bucket: str
    object_key: str
    object_uri: str
    checksum: str | None = None
    upload_status: str
    created_at: datetime


class AnalysisAssetListResponse(BaseModel):
    items: list[AnalysisAssetRead] = Field(default_factory=list)


class AnalysisUploadSessionRead(BaseModel):
    id: UUID
    upload_token: str
    upload_status: str
    created_at: datetime


class AnalysisUploadCreateRequest(BaseModel):
    media_type: MediaType
    original_filename: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(gt=0)


class AnalysisUploadCreateResponse(BaseModel):
    upload_session: AnalysisUploadSessionRead
    asset: AnalysisAssetRead
    upload_url: str
    upload_headers: dict[str, str] = Field(default_factory=dict)


class AnalysisUploadCompleteRequest(BaseModel):
    upload_token: str = Field(min_length=1, max_length=120)


class AnalysisUploadCompleteResponse(BaseModel):
    upload_session: AnalysisUploadSessionRead
    asset: AnalysisAssetRead


class AnalysisJobCreateRequest(BaseModel):
    asset_id: UUID
    objective: str | None = Field(default=None, max_length=2_000)


class AnalysisJobRead(BaseModel):
    id: UUID
    asset_id: UUID
    status: str
    objective: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime


class AnalysisSummaryPayload(BaseModel):
    modality: MediaType
    overall_attention_score: float
    hook_score_first_3_seconds: float
    sustained_engagement_score: float
    memory_proxy_score: float
    cognitive_load_proxy: float
    confidence: float | None = None
    completeness: float | None = None
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisMetricRowRead(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    source: str
    detail: str | None = None
    confidence: float | None = None


class AnalysisTimelinePointRead(BaseModel):
    timestamp_ms: int
    engagement_score: float
    attention_score: float
    memory_proxy: float


class AnalysisSegmentRowRead(BaseModel):
    segment_index: int
    label: str
    start_time_ms: int
    end_time_ms: int
    attention_score: float
    engagement_delta: float
    note: str


class AnalysisIntervalRead(BaseModel):
    label: str
    start_time_ms: int
    end_time_ms: int
    average_attention_score: float


class AnalysisHeatmapFrameRead(BaseModel):
    timestamp_ms: int
    label: str
    scene_label: str
    grid_rows: int
    grid_columns: int
    intensity_map: list[list[float]]
    strongest_zone: str
    caption: str


class AnalysisVisualizationsPayload(BaseModel):
    visualization_mode: str
    heatmap_frames: list[AnalysisHeatmapFrameRead] = Field(default_factory=list)
    high_attention_intervals: list[AnalysisIntervalRead] = Field(default_factory=list)
    low_attention_intervals: list[AnalysisIntervalRead] = Field(default_factory=list)


class AnalysisRecommendationRead(BaseModel):
    title: str
    detail: str
    priority: RecommendationPriority
    timestamp_ms: int | None = None
    confidence: float | None = None


class AnalysisResultRead(BaseModel):
    job_id: UUID
    summary_json: AnalysisSummaryPayload
    metrics_json: list[AnalysisMetricRowRead]
    timeline_json: list[AnalysisTimelinePointRead]
    segments_json: list[AnalysisSegmentRowRead]
    visualizations_json: AnalysisVisualizationsPayload
    recommendations_json: list[AnalysisRecommendationRead]
    created_at: datetime


class AnalysisJobStatusResponse(BaseModel):
    job: AnalysisJobRead
    result: AnalysisResultRead | None = None


class AnalysisJobListItemRead(BaseModel):
    job: AnalysisJobRead
    asset: AnalysisAssetRead | None = None
    has_result: bool = False
    result_created_at: datetime | None = None


class AnalysisJobListResponse(BaseModel):
    items: list[AnalysisJobListItemRead] = Field(default_factory=list)
