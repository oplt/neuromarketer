export type MediaType = 'video' | 'audio' | 'text'
export type JobState = 'queued' | 'processing' | 'completed' | 'failed'
export type UploadStage = 'idle' | 'validating' | 'uploading' | 'uploaded' | 'failed'
export type RecommendationPriority = 'high' | 'medium' | 'low'
export type AnalysisFlowStepId = 'asset' | 'goal' | 'results'
export type AnalysisSelectionMode = 'auto' | 'asset' | 'job'
export type HistoryDrawerMode = 'resume' | 'compare'

export type AnalysisConfigResponse = {
  max_file_size_bytes: number
  max_text_characters: number
  allowed_media_types: MediaType[]
  allowed_mime_types: Record<MediaType, string[]>
}

export type AnalysisAsset = {
  id: string
  creative_id?: string | null
  creative_version_id?: string | null
  media_type: MediaType
  original_filename?: string | null
  mime_type?: string | null
  size_bytes?: number | null
  bucket: string
  object_key: string
  object_uri: string
  checksum?: string | null
  upload_status: string
  created_at: string
}

export type AnalysisAssetListResponse = {
  items: AnalysisAsset[]
}

export type AnalysisBulkDeleteResponse = {
  deleted_count: number
  deleted_ids: string[]
}

export type AnalysisUploadSession = {
  id: string
  upload_token: string
  upload_status: string
  created_at: string
}

export type AnalysisUploadCreateResponse = {
  upload_session: AnalysisUploadSession
  asset: AnalysisAsset
  upload_url: string
  upload_headers: Record<string, string>
}

export type AnalysisUploadCompleteResponse = {
  upload_session: AnalysisUploadSession
  asset: AnalysisAsset
}

export type AnalysisJob = {
  id: string
  asset_id: string
  status: JobState
  objective?: string | null
  goal_template?: string | null
  channel?: string | null
  audience_segment?: string | null
  started_at?: string | null
  finished_at?: string | null
  error_message?: string | null
  created_at: string
}

export type AnalysisSummary = {
  modality: MediaType
  overall_attention_score: number
  hook_score_first_3_seconds: number
  sustained_engagement_score: number
  memory_proxy_score: number
  cognitive_load_proxy: number
  confidence?: number | null
  completeness?: number | null
  notes?: string[]
  metadata?: {
    objective?: string | null
    goal_template?: string | null
    channel?: string | null
    audience_segment?: string | null
    source_label?: string | null
    segment_count?: number | null
    duration_ms?: number | null
  }
}

export type AnalysisMetricRow = {
  key: string
  label: string
  value: number
  unit: string
  source: string
  detail?: string | null
  confidence?: number | null
}

export type AnalysisTimelinePoint = {
  timestamp_ms: number
  engagement_score: number
  attention_score: number
  memory_proxy: number
}

export type AnalysisSegmentRow = {
  segment_index: number
  label: string
  start_time_ms: number
  end_time_ms: number
  attention_score: number
  memory_proxy: number
  emotion_score: number
  cognitive_load: number
  conversion_proxy: number
  engagement_score: number
  engagement_delta: number
  peak_focus: number
  temporal_change: number
  consistency: number
  hemisphere_balance: number
  note: string
}

export type AnalysisInterval = {
  label: string
  start_time_ms: number
  end_time_ms: number
  average_attention_score: number
}

export type AnalysisHeatmapFrame = {
  timestamp_ms: number
  label: string
  scene_label: string
  grid_rows: number
  grid_columns: number
  intensity_map: number[][]
  strongest_zone: string
  caption: string
}

export type AnalysisVisualizationPresentation = {
  segment_prefix?: string
  segment_plural?: string
  heatmap_prefix?: string
  heatmap_subject?: string
  timeline_label?: string
  visualization_mode?: string
  grid_caption?: string
}

export type AnalysisFrameBreakdownItem = {
  timestamp_ms: number
  label: string
  scene_label: string
  strongest_zone?: string | null
  attention_score: number
  engagement_score: number
  memory_proxy: number
}

export type AnalysisRecommendation = {
  title: string
  detail: string
  priority: RecommendationPriority
  timestamp_ms?: number | null
  confidence?: number | null
}

export type AnalysisResult = {
  job_id: string
  summary_json: AnalysisSummary
  metrics_json: AnalysisMetricRow[]
  timeline_json: AnalysisTimelinePoint[]
  segments_json: AnalysisSegmentRow[]
  visualizations_json: {
    visualization_mode: string
    heatmap_frames: AnalysisHeatmapFrame[]
    high_attention_intervals: AnalysisInterval[]
    low_attention_intervals: AnalysisInterval[]
    presentation?: AnalysisVisualizationPresentation | null
  }
  recommendations_json: AnalysisRecommendation[]
  created_at: string
}

export type AnalysisJobStatusResponse = {
  job: AnalysisJob
  result?: AnalysisResult | null
  asset?: AnalysisAsset | null
  progress?: {
    stage: string
    stage_label?: string | null
    diagnostics?: {
      queue_wait_ms?: number | null
      processing_duration_ms?: number | null
      time_to_first_result_ms?: number | null
      result_delivery_ms?: number | null
      postprocess_duration_ms?: number | null
    }
    is_partial?: boolean
  } | null
}
export type AnalysisProgressEvent = {
  job: AnalysisJob
  result?: AnalysisResult | null
  asset?: AnalysisAsset | null
  stage?: string | null
  stage_label?: string | null
  diagnostics?: {
    queue_wait_ms?: number | null
    processing_duration_ms?: number | null
    time_to_first_result_ms?: number | null
    result_delivery_ms?: number | null
    postprocess_duration_ms?: number | null
  }
  is_partial?: boolean
}

export type AnalysisJobListItem = {
  job: AnalysisJob
  asset?: AnalysisAsset | null
  has_result: boolean
  result_created_at?: string | null
}

export type AnalysisJobListResponse = {
  items: AnalysisJobListItem[]
}

export type LoadAnalysisJobOptions = {
  historyItem?: AnalysisJobListItem | null
  announceSelection?: boolean
  showSelectionLoading?: boolean
}

export type UploadState = {
  stage: UploadStage
  progressPercent: number
  validationErrors: string[]
  errorMessage?: string
  asset?: AnalysisAsset
  uploadSession?: AnalysisUploadSession
}

export type BannerMessage = {
  type: 'error' | 'success' | 'info'
  message: string
}

export type AnalysisProgressState = {
  jobId: string
  stage: string
  stageLabel: string | null
  diagnostics?: {
    queueWaitMs?: number | null
    processingDurationMs?: number | null
    timeToFirstResultMs?: number | null
    resultDeliveryMs?: number | null
    postprocessDurationMs?: number | null
  }
}

export type AnalysisClientEventName =
  | 'upload_started'
  | 'upload_completed'
  | 'upload_validation_failed'
  | 'analysis_started'
  | 'analysis_retry_clicked'
  | 'analysis_stream_connected'
  | 'analysis_stream_fallback'
  | 'first_result_seen'
  | 'analysis_completed'
  | 'compare_clicked'
  | 'quick_compare_opened'
  | 'quick_compare_loaded'
  | 'export_clicked'
  | 'goal_suggestion_applied'
  | 'analysis_load_failed'

export type UploadSource = {
  file: Blob
  fileName: string
  mimeType: string
  sizeBytes: number
}

export type SummaryCard = {
  key: string
  label: string
  value: number
  helper: string
}

export type AnalysisWizardSnapshot = {
  mediaType: MediaType
  objective: string
  goalTemplate: string
  channel: string
  audienceSegment: string
  selectionMode: AnalysisSelectionMode
}

export type GoalTemplateOption = {
  value: string
  label: string
  description: string
  supported_media_types: MediaType[]
  default_channel?: string | null
  group_id: string
}

export type ChannelOption = {
  value: string
  label: string
  supported_media_types: MediaType[]
}

export type GoalPresetGroup = {
  id: string
  label: string
  description: string
  template_values: string[]
}

export type GoalSuggestion = {
  media_type: MediaType
  goal_template: string
  channel: string
  audience_placeholder: string
  rationale: string
}

export type AnalysisBenchmarkMetric = {
  key: string
  label: string
  value: number
  percentile: number
  cohort_median: number
  cohort_p75: number
  orientation: 'higher' | 'lower'
  detail: string
}

export type AnalysisBenchmarkResponse = {
  job_id: string
  cohort_label: string
  cohort_size: number
  fallback_level: string
  metrics: AnalysisBenchmarkMetric[]
  generated_at: string
}

export type AnalysisExecutiveVerdict = {
  job_id: string
  status: 'ship' | 'iterate' | 'high_risk'
  headline: string
  summary: string
  benchmark_average_percentile?: number | null
  top_strengths: string[]
  top_risks: string[]
  recommended_actions: string[]
  generated_at: string
}

export type AnalysisCalibrationObservation = {
  id: string
  metric_type: string
  score_type: string
  predicted_value: number
  actual_value: number
  observed_at: string
  source_system?: string | null
  source_ref?: string | null
}

export type AnalysisCalibrationResponse = {
  job_id: string
  summary: {
    observation_count: number
    metric_types: string[]
    latest_observed_at?: string | null
    average_predicted_value?: number | null
    average_actual_value?: number | null
  }
  observations: AnalysisCalibrationObservation[]
}

export type AnalysisGeneratedVariantType = 'hook_rewrite' | 'cta_rewrite' | 'shorter_script' | 'alternate_thumbnail'

export type AnalysisGeneratedVariantSection = {
  key: string
  label: string
  value: string
}

export type AnalysisGeneratedVariantMetricDelta = {
  key: string
  label: string
  original_value: number
  variant_value: number
  delta: number
  unit: string
}

export type AnalysisGeneratedVariant = {
  id: string
  job_id: string
  parent_creative_version_id: string
  variant_type: AnalysisGeneratedVariantType
  title: string
  summary: string
  focus_recommendations: string[]
  source_suggestion_title?: string | null
  source_suggestion_type?: string | null
  sections: AnalysisGeneratedVariantSection[]
  expected_score_lift_json: Record<string, number>
  projected_summary_json: AnalysisSummary
  compare_metrics: AnalysisGeneratedVariantMetricDelta[]
  compare_summary: string
  created_at: string
  updated_at: string
}

export type AnalysisGeneratedVariantListResponse = {
  job_id: string
  items: AnalysisGeneratedVariant[]
}

export type AnalysisOutcomeImportResponse = {
  imported_events: number
  imported_observations: number
  failed_rows: number
  errors: string[]
}

export type AnalysisTransportDiagnostics = {
  mode: 'stream' | 'polling'
  isConnected: boolean
  reconnectCount: number
  lastError: string | null
  lastConnectedAt: string | null
  lastHeartbeatAt: string | null
}

export type AnalysisGoalPresetsResponse = {
  goal_templates: GoalTemplateOption[]
  channels: ChannelOption[]
  preset_groups: GoalPresetGroup[]
  suggestions: GoalSuggestion[]
}