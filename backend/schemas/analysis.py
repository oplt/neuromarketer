from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.services.analysis_goal_taxonomy import AnalysisChannel, GoalTemplate

MediaType = Literal["video", "audio", "text"]
RecommendationPriority = Literal["high", "medium", "low"]


class AnalysisConfigResponse(BaseModel):
    max_file_size_bytes: int
    max_text_characters: int
    allowed_media_types: list[MediaType]
    allowed_mime_types: dict[MediaType, list[str]]


class AnalysisGoalTemplatePresetRead(BaseModel):
    value: GoalTemplate
    label: str
    description: str
    supported_media_types: list[MediaType] = Field(default_factory=list)
    default_channel: AnalysisChannel | None = None
    group_id: str


class AnalysisChannelPresetRead(BaseModel):
    value: AnalysisChannel
    label: str
    supported_media_types: list[MediaType] = Field(default_factory=list)


class AnalysisGoalPresetGroupRead(BaseModel):
    id: str
    label: str
    description: str
    template_values: list[GoalTemplate] = Field(default_factory=list)


class AnalysisGoalSuggestionRead(BaseModel):
    media_type: MediaType
    goal_template: GoalTemplate
    channel: AnalysisChannel
    audience_placeholder: str
    rationale: str


class AnalysisGoalPresetsResponse(BaseModel):
    goal_templates: list[AnalysisGoalTemplatePresetRead] = Field(default_factory=list)
    channels: list[AnalysisChannelPresetRead] = Field(default_factory=list)
    preset_groups: list[AnalysisGoalPresetGroupRead] = Field(default_factory=list)
    suggestions: list[AnalysisGoalSuggestionRead] = Field(default_factory=list)


class AnalysisClientEventRequest(BaseModel):
    event_name: Literal[
        "upload_started",
        "upload_completed",
        "upload_validation_failed",
        "analysis_started",
        "analysis_retry_clicked",
        "analysis_stream_connected",
        "analysis_stream_fallback",
        "first_result_seen",
        "analysis_completed",
        "compare_clicked",
        "quick_compare_opened",
        "quick_compare_loaded",
        "export_clicked",
        "goal_suggestion_applied",
        "analysis_load_failed",
    ]
    media_type: MediaType
    goal_template: GoalTemplate | None = None
    channel: AnalysisChannel | None = None
    audience_segment: str | None = Field(default=None, max_length=255)
    job_id: UUID | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AnalysisComparisonCreateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    analysis_job_ids: list[UUID] = Field(min_length=2, max_length=5)
    baseline_job_id: UUID | None = None
    comparison_context: dict[str, Any] = Field(default_factory=dict)


class AnalysisComparisonListItemRead(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    winning_analysis_job_id: UUID | None = None
    baseline_job_id: UUID | None = None
    candidate_count: int
    summary_json: dict[str, Any] = Field(default_factory=dict)
    item_labels: list[str] = Field(default_factory=list)


class AnalysisComparisonListResponse(BaseModel):
    items: list[AnalysisComparisonListItemRead] = Field(default_factory=list)


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
    goal_template: GoalTemplate | None = None
    channel: AnalysisChannel | None = None
    audience_segment: str | None = Field(default=None, max_length=255)


class AnalysisJobRead(BaseModel):
    id: UUID
    asset_id: UUID
    status: str
    objective: str | None = None
    goal_template: GoalTemplate | None = None
    channel: AnalysisChannel | None = None
    audience_segment: str | None = None
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
    # LLM-evaluated scores
    attention_score: float
    memory_proxy: float = 0.0
    emotion_score: float = 0.0
    cognitive_load: float = 0.0
    conversion_proxy: float = 0.0
    # TRIBE-direct signals
    engagement_score: float = 0.0
    engagement_delta: float
    peak_focus: float = 0.0
    temporal_change: float = 0.0
    consistency: float = 0.0
    hemisphere_balance: float = 0.0
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


class AnalysisJobDiagnosticsRead(BaseModel):
    queue_wait_ms: int | None = None
    processing_duration_ms: int | None = None
    time_to_first_result_ms: int | None = None
    result_delivery_ms: int | None = None
    postprocess_duration_ms: int | None = None


class AnalysisJobProgressRead(BaseModel):
    stage: str
    stage_label: str | None = None
    diagnostics: AnalysisJobDiagnosticsRead = Field(default_factory=AnalysisJobDiagnosticsRead)
    is_partial: bool = False


class AnalysisJobStatusResponse(BaseModel):
    job: AnalysisJobRead
    result: AnalysisResultRead | None = None
    asset: AnalysisAssetRead | None = None
    progress: AnalysisJobProgressRead | None = None


class AnalysisJobListItemRead(BaseModel):
    job: AnalysisJobRead
    asset: AnalysisAssetRead | None = None
    has_result: bool = False
    result_created_at: datetime | None = None


class AnalysisJobListResponse(BaseModel):
    items: list[AnalysisJobListItemRead] = Field(default_factory=list)


class AnalysisComparisonItemRead(BaseModel):
    analysis_job_id: UUID
    job: AnalysisJobRead
    asset: AnalysisAssetRead | None = None
    result: AnalysisResultRead
    overall_rank: int
    is_winner: bool = False
    is_baseline: bool = False
    scores_json: dict[str, Any] = Field(default_factory=dict)
    delta_json: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = None
    scene_deltas_json: list[dict[str, Any]] = Field(default_factory=list)
    recommendation_overlap_json: dict[str, Any] = Field(default_factory=dict)


class AnalysisComparisonRead(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    winning_analysis_job_id: UUID | None = None
    baseline_job_id: UUID | None = None
    summary_json: dict[str, Any] = Field(default_factory=dict)
    comparison_context: dict[str, Any] = Field(default_factory=dict)
    items: list[AnalysisComparisonItemRead] = Field(default_factory=list)


class AnalysisBenchmarkMetricRead(BaseModel):
    key: str
    label: str
    value: float
    percentile: float
    cohort_median: float
    cohort_p75: float
    orientation: Literal["higher", "lower"]
    detail: str


class AnalysisBenchmarkResponse(BaseModel):
    job_id: UUID
    cohort_label: str
    cohort_size: int
    fallback_level: str
    metrics: list[AnalysisBenchmarkMetricRead] = Field(default_factory=list)
    generated_at: datetime


class AnalysisExecutiveVerdictRead(BaseModel):
    job_id: UUID
    status: Literal["ship", "iterate", "high_risk"]
    headline: str
    summary: str
    benchmark_average_percentile: float | None = None
    top_strengths: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    generated_at: datetime


class AnalysisCalibrationObservationRead(BaseModel):
    id: UUID
    metric_type: str
    score_type: str
    predicted_value: float
    actual_value: float
    normalized_actual_value: float | None = None
    delta_value: float | None = None
    observed_at: datetime
    source_system: str | None = None
    source_ref: str | None = None


class AnalysisCalibrationSummaryRead(BaseModel):
    observation_count: int
    metric_types: list[str] = Field(default_factory=list)
    latest_observed_at: datetime | None = None
    average_predicted_value: float | None = None
    average_actual_value: float | None = None
    average_normalized_actual_value: float | None = None
    mean_absolute_error: float | None = None
    mean_signed_error: float | None = None
    over_prediction_rate: float | None = None
    under_prediction_rate: float | None = None
    drift_status: Literal["aligned", "over_predicting", "under_predicting", "insufficient_data"] = (
        "insufficient_data"
    )


class AnalysisCalibrationResponse(BaseModel):
    job_id: UUID
    summary: AnalysisCalibrationSummaryRead
    observations: list[AnalysisCalibrationObservationRead] = Field(default_factory=list)


class AnalysisCalibrationTrendPointRead(BaseModel):
    id: UUID
    analysis_job_id: UUID | None = None
    metric_type: str
    score_type: str
    predicted_value: float
    actual_value: float
    normalized_actual_value: float | None = None
    delta_value: float | None = None
    observed_at: datetime
    source_system: str | None = None
    source_ref: str | None = None


class AnalysisCalibrationMetricSummaryRead(BaseModel):
    metric_type: str
    observation_count: int
    score_types: list[str] = Field(default_factory=list)
    latest_observed_at: datetime | None = None
    average_predicted_value: float | None = None
    average_actual_value: float | None = None
    average_normalized_actual_value: float | None = None
    mean_absolute_error: float | None = None
    mean_signed_error: float | None = None
    over_prediction_rate: float | None = None
    under_prediction_rate: float | None = None
    drift_status: Literal["aligned", "over_predicting", "under_predicting", "insufficient_data"] = (
        "insufficient_data"
    )
    trend_points: list[AnalysisCalibrationTrendPointRead] = Field(default_factory=list)
    over_predictions: list[AnalysisCalibrationTrendPointRead] = Field(default_factory=list)
    under_predictions: list[AnalysisCalibrationTrendPointRead] = Field(default_factory=list)


class AnalysisOutcomeImportHistoryRead(BaseModel):
    id: UUID
    imported_at: datetime
    actor_email: str | None = None
    actor_full_name: str | None = None
    filename: str | None = None
    imported_events: int = 0
    imported_observations: int = 0
    failed_rows: int = 0
    metric_types: list[str] = Field(default_factory=list)
    source_systems: list[str] = Field(default_factory=list)


class AnalysisCalibrationDashboardSummaryRead(BaseModel):
    total_outcome_events: int = 0
    total_calibration_observations: int = 0
    imported_jobs_count: int = 0
    metric_types: list[str] = Field(default_factory=list)
    latest_observed_at: datetime | None = None
    latest_imported_at: datetime | None = None
    average_predicted_value: float | None = None
    average_actual_value: float | None = None
    average_normalized_actual_value: float | None = None
    mean_absolute_error: float | None = None
    mean_signed_error: float | None = None
    over_prediction_rate: float | None = None
    under_prediction_rate: float | None = None
    drift_status: Literal["aligned", "over_predicting", "under_predicting", "insufficient_data"] = (
        "insufficient_data"
    )


class AnalysisCalibrationDashboardResponse(BaseModel):
    project_id: UUID
    summary: AnalysisCalibrationDashboardSummaryRead
    metrics: list[AnalysisCalibrationMetricSummaryRead] = Field(default_factory=list)
    recent_imports: list[AnalysisOutcomeImportHistoryRead] = Field(default_factory=list)


class AnalysisOutcomeImportResponse(BaseModel):
    imported_events: int
    imported_observations: int
    failed_rows: int = 0
    metric_types: list[str] = Field(default_factory=list)
    source_systems: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


AnalysisGeneratedVariantType = Literal[
    "hook_rewrite",
    "cta_rewrite",
    "shorter_script",
    "alternate_thumbnail",
]


class AnalysisGeneratedVariantSectionRead(BaseModel):
    key: str
    label: str
    value: str


class AnalysisGeneratedVariantMetricDeltaRead(BaseModel):
    key: str
    label: str
    original_value: float
    variant_value: float
    delta: float
    unit: str = "/100"


class AnalysisGeneratedVariantRead(BaseModel):
    id: UUID
    job_id: UUID
    parent_creative_version_id: UUID
    variant_type: AnalysisGeneratedVariantType
    title: str
    summary: str
    focus_recommendations: list[str] = Field(default_factory=list)
    source_suggestion_title: str | None = None
    source_suggestion_type: str | None = None
    sections: list[AnalysisGeneratedVariantSectionRead] = Field(default_factory=list)
    expected_score_lift_json: dict[str, float] = Field(default_factory=dict)
    projected_summary_json: AnalysisSummaryPayload
    compare_metrics: list[AnalysisGeneratedVariantMetricDeltaRead] = Field(default_factory=list)
    compare_summary: str
    created_at: datetime
    updated_at: datetime


class AnalysisGeneratedVariantListResponse(BaseModel):
    job_id: UUID
    items: list[AnalysisGeneratedVariantRead] = Field(default_factory=list)


class AnalysisGeneratedVariantCreateRequest(BaseModel):
    variant_types: list[AnalysisGeneratedVariantType] = Field(
        default_factory=lambda: [
            "hook_rewrite",
            "cta_rewrite",
            "shorter_script",
            "alternate_thumbnail",
        ],
        min_length=1,
        max_length=4,
    )
    replace_existing: bool = True
