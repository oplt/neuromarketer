export type JobState = 'queued' | 'processing' | 'completed' | 'failed'
export type MediaType = 'video' | 'audio' | 'text'

export type CompareBanner = {
  type: 'error' | 'success' | 'info'
  message: string
}

export type AnalysisAsset = {
  id: string
  media_type: MediaType
  original_filename?: string | null
  object_key: string
  upload_status: string
  created_at: string
}

export type AnalysisJob = {
  id: string
  asset_id: string
  status: JobState
  objective?: string | null
  goal_template?: string | null
  channel?: string | null
  audience_segment?: string | null
  created_at: string
}

export type AnalysisSummary = {
  overall_attention_score: number
  hook_score_first_3_seconds: number
  sustained_engagement_score: number
  memory_proxy_score: number
  cognitive_load_proxy: number
  confidence?: number | null
}

export type AnalysisMetricRow = {
  key: string
  label: string
  value: number
  unit: string
}

export type AnalysisSegmentRow = {
  segment_index: number
  label: string
  start_time_ms: number
  end_time_ms: number
  attention_score: number
  engagement_delta: number
  note: string
}

export type AnalysisRecommendation = {
  title: string
  detail: string
  priority: 'high' | 'medium' | 'low'
}

export type AnalysisResult = {
  job_id: string
  summary_json: AnalysisSummary
  metrics_json: AnalysisMetricRow[]
  segments_json: AnalysisSegmentRow[]
  recommendations_json: AnalysisRecommendation[]
}

export type AnalysisJobListItem = {
  job: AnalysisJob
  asset?: AnalysisAsset | null
  has_result: boolean
}

export type AnalysisJobListResponse = {
  items: AnalysisJobListItem[]
}

export type AnalysisComparisonHistoryItem = {
  id: string
  name: string
  created_at: string
  winning_analysis_job_id?: string | null
  baseline_job_id?: string | null
  candidate_count: number
  summary_json: Record<string, unknown>
  item_labels: string[]
}

export type AnalysisComparisonHistoryResponse = {
  items: AnalysisComparisonHistoryItem[]
}

export type AnalysisComparisonItem = {
  analysis_job_id: string
  job: AnalysisJob
  asset?: AnalysisAsset | null
  result: AnalysisResult
  overall_rank: number
  is_winner: boolean
  is_baseline: boolean
  scores_json: Record<string, number>
  delta_json: Record<string, number>
  rationale?: string | null
  scene_deltas_json: Array<{
    segment_index: number
    label: string
    baseline_window?: string | null
    candidate_window: string
    baseline_attention: number
    candidate_attention: number
    attention_delta: number
    engagement_delta_delta: number
    baseline_note?: string | null
    candidate_note: string
  }>
  recommendation_overlap_json: {
    shared_titles: string[]
    candidate_only_titles: string[]
    baseline_only_titles: string[]
  }
}

export type AnalysisComparison = {
  id: string
  name: string
  created_at: string
  winning_analysis_job_id?: string | null
  baseline_job_id?: string | null
  summary_json: Record<string, unknown>
  comparison_context: Record<string, unknown>
  items: AnalysisComparisonItem[]
}
