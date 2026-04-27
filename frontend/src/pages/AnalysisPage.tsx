import { Suspense, lazy } from 'react'
import AudiotrackRounded from '@mui/icons-material/AudiotrackRounded'
import AutoGraphRounded from '@mui/icons-material/AutoGraphRounded'
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded'
import CompareArrowsRounded from '@mui/icons-material/CompareArrowsRounded'
import DownloadRounded from '@mui/icons-material/DownloadRounded'
import CloudUploadRounded from '@mui/icons-material/CloudUploadRounded'
import HistoryRounded from '@mui/icons-material/HistoryRounded'
import DescriptionRounded from '@mui/icons-material/DescriptionRounded'
import FileUploadRounded from '@mui/icons-material/FileUploadRounded'
import PlayCircleRounded from '@mui/icons-material/PlayCircleRounded'
import VideoLibraryRounded from '@mui/icons-material/VideoLibraryRounded'
import {
  Alert,
  Box,
  Button,
  ButtonBase,
  Chip,
  Drawer,
  LinearProgress,
  MenuItem,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import {
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  type ChangeEvent,
  type Dispatch,
  type DragEvent,
  type ReactElement,
  type SetStateAction,
} from 'react'
import { apiFetch, apiRequest, subscribeToEventStream, uploadToApi, uploadToSignedUrl } from '../lib/api'
import { buildCompareWorkspaceStorageKey, storeCompareWorkspaceSnapshot } from '../lib/compareWorkspace'
import { runWhenIdle } from '../lib/defer'
import type { AuthSession } from '../lib/session'
import MetricsRadarCard from '../components/analysis/MetricsRadarCard'
import HelpTooltip from '../components/layout/HelpTooltip'

const AnalysisEvaluationSection = lazy(() => import('../components/analysis/AnalysisEvaluationSection'))
const CollaborationPanel = lazy(() => import('../components/collaboration/CollaborationPanel'))
type AnalysisEvaluationProgressSnapshot =
  import('../components/analysis/AnalysisEvaluationSection').AnalysisEvaluationProgressSnapshot

type AnalysisPageProps = {
  session: AuthSession
  onOpenCompareWorkspace?: () => void
}

type MediaType = 'video' | 'audio' | 'text'
type JobState = 'queued' | 'processing' | 'completed' | 'failed'
type UploadStage = 'idle' | 'validating' | 'uploading' | 'uploaded' | 'failed'
type RecommendationPriority = 'high' | 'medium' | 'low'
type AnalysisFlowStepId = 'asset' | 'goal' | 'results'
type AnalysisSelectionMode = 'auto' | 'asset' | 'job'
type HistoryDrawerMode = 'resume' | 'compare'

type AnalysisConfigResponse = {
  max_file_size_bytes: number
  max_text_characters: number
  allowed_media_types: MediaType[]
  allowed_mime_types: Record<MediaType, string[]>
}

type AnalysisAsset = {
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

type AnalysisAssetListResponse = {
  items: AnalysisAsset[]
}

type AnalysisUploadSession = {
  id: string
  upload_token: string
  upload_status: string
  created_at: string
}

type AnalysisUploadCreateResponse = {
  upload_session: AnalysisUploadSession
  asset: AnalysisAsset
  upload_url: string
  upload_headers: Record<string, string>
}

type AnalysisUploadCompleteResponse = {
  upload_session: AnalysisUploadSession
  asset: AnalysisAsset
}

type AnalysisJob = {
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

type AnalysisSummary = {
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

type AnalysisMetricRow = {
  key: string
  label: string
  value: number
  unit: string
  source: string
  detail?: string | null
  confidence?: number | null
}

type AnalysisTimelinePoint = {
  timestamp_ms: number
  engagement_score: number
  attention_score: number
  memory_proxy: number
}

type AnalysisSegmentRow = {
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

type AnalysisInterval = {
  label: string
  start_time_ms: number
  end_time_ms: number
  average_attention_score: number
}

type AnalysisHeatmapFrame = {
  timestamp_ms: number
  label: string
  scene_label: string
  grid_rows: number
  grid_columns: number
  intensity_map: number[][]
  strongest_zone: string
  caption: string
}

type AnalysisFrameBreakdownItem = {
  timestamp_ms: number
  label: string
  scene_label: string
  strongest_zone?: string | null
  attention_score: number
  engagement_score: number
  memory_proxy: number
}

type AnalysisRecommendation = {
  title: string
  detail: string
  priority: RecommendationPriority
  timestamp_ms?: number | null
  confidence?: number | null
}

type AnalysisResult = {
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
  }
  recommendations_json: AnalysisRecommendation[]
  created_at: string
}

type AnalysisJobStatusResponse = {
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

const TEXT_DOCUMENT_MIME_BY_EXTENSION: Record<string, string> = {
  '.csv': 'text/csv',
  '.doc': 'application/msword',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.htm': 'text/html',
  '.html': 'text/html',
  '.json': 'application/json',
  '.markdown': 'text/markdown',
  '.md': 'text/markdown',
  '.odt': 'application/vnd.oasis.opendocument.text',
  '.pdf': 'application/pdf',
  '.rtf': 'application/rtf',
  '.tsv': 'text/tab-separated-values',
  '.txt': 'text/plain',
  '.xml': 'application/xml',
}

const TEXT_DOCUMENT_EXTENSIONS = Object.keys(TEXT_DOCUMENT_MIME_BY_EXTENSION)

type AnalysisProgressEvent = {
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

type AnalysisJobListItem = {
  job: AnalysisJob
  asset?: AnalysisAsset | null
  has_result: boolean
  result_created_at?: string | null
}

type AnalysisJobListResponse = {
  items: AnalysisJobListItem[]
}

type LoadAnalysisJobOptions = {
  historyItem?: AnalysisJobListItem | null
  announceSelection?: boolean
  showSelectionLoading?: boolean
}

type UploadState = {
  stage: UploadStage
  progressPercent: number
  validationErrors: string[]
  errorMessage?: string
  asset?: AnalysisAsset
  uploadSession?: AnalysisUploadSession
}

type BannerMessage = {
  type: 'error' | 'success' | 'info'
  message: string
}

type AnalysisProgressState = {
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

type AnalysisClientEventName =
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

type UploadSource = {
  file: Blob
  fileName: string
  mimeType: string
  sizeBytes: number
}

type SummaryCard = {
  key: string
  label: string
  value: number
  helper: string
}

type AnalysisWizardSnapshot = {
  mediaType: MediaType
  objective: string
  goalTemplate: string
  channel: string
  audienceSegment: string
  selectionMode: AnalysisSelectionMode
}

type GoalTemplateOption = {
  value: string
  label: string
  description: string
  supported_media_types: MediaType[]
  default_channel?: string | null
  group_id: string
}

type ChannelOption = {
  value: string
  label: string
  supported_media_types: MediaType[]
}

type GoalPresetGroup = {
  id: string
  label: string
  description: string
  template_values: string[]
}

type GoalSuggestion = {
  media_type: MediaType
  goal_template: string
  channel: string
  audience_placeholder: string
  rationale: string
}

type AnalysisBenchmarkMetric = {
  key: string
  label: string
  value: number
  percentile: number
  cohort_median: number
  cohort_p75: number
  orientation: 'higher' | 'lower'
  detail: string
}

type AnalysisBenchmarkResponse = {
  job_id: string
  cohort_label: string
  cohort_size: number
  fallback_level: string
  metrics: AnalysisBenchmarkMetric[]
  generated_at: string
}

type AnalysisExecutiveVerdict = {
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

type AnalysisCalibrationObservation = {
  id: string
  metric_type: string
  score_type: string
  predicted_value: number
  actual_value: number
  observed_at: string
  source_system?: string | null
  source_ref?: string | null
}

type AnalysisCalibrationResponse = {
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

type AnalysisGeneratedVariantType = 'hook_rewrite' | 'cta_rewrite' | 'shorter_script' | 'alternate_thumbnail'

type AnalysisGeneratedVariantSection = {
  key: string
  label: string
  value: string
}

type AnalysisGeneratedVariantMetricDelta = {
  key: string
  label: string
  original_value: number
  variant_value: number
  delta: number
  unit: string
}

type AnalysisGeneratedVariant = {
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

type AnalysisGeneratedVariantListResponse = {
  job_id: string
  items: AnalysisGeneratedVariant[]
}

type AnalysisOutcomeImportResponse = {
  imported_events: number
  imported_observations: number
  failed_rows: number
  errors: string[]
}

type AnalysisTransportDiagnostics = {
  mode: 'stream' | 'polling'
  isConnected: boolean
  reconnectCount: number
  lastError: string | null
  lastConnectedAt: string | null
  lastHeartbeatAt: string | null
}

type AnalysisGoalPresetsResponse = {
  goal_templates: GoalTemplateOption[]
  channels: ChannelOption[]
  preset_groups: GoalPresetGroup[]
  suggestions: GoalSuggestion[]
}

const defaultGoalTemplateOptions: GoalTemplateOption[] = [
  {
    value: 'paid_social_hook',
    label: 'Paid social hook',
    description: 'Front-loaded hold strength, pacing, and CTA readiness.',
    supported_media_types: ['video', 'audio'],
    default_channel: 'meta_feed',
    group_id: 'paid_social',
  },
  {
    value: 'ugc_native_social',
    label: 'UGC / native social',
    description: 'Authenticity, creator pacing, and native platform fit.',
    supported_media_types: ['video'],
    default_channel: 'tiktok',
    group_id: 'paid_social',
  },
  {
    value: 'landing_page_clarity',
    label: 'Landing page hero',
    description: 'Message clarity, cognitive load, and conversion friction above the fold.',
    supported_media_types: ['video', 'text'],
    default_channel: 'landing_page',
    group_id: 'web_conversion',
  },
  {
    value: 'email_clickthrough',
    label: 'Email clickthrough',
    description: 'Subject-to-body continuity, scanning flow, and CTA intent.',
    supported_media_types: ['text'],
    default_channel: 'email',
    group_id: 'web_conversion',
  },
  {
    value: 'education_explainer',
    label: 'Education / explainer',
    description: 'Comprehension, retention, and overload risk.',
    supported_media_types: ['video', 'audio', 'text'],
    default_channel: 'youtube_pre_roll',
    group_id: 'education',
  },
  {
    value: 'brand_story_film',
    label: 'Brand film',
    description: 'Memory lift, emotional continuity, and brand anchoring.',
    supported_media_types: ['video', 'audio'],
    default_channel: 'youtube_pre_roll',
    group_id: 'storytelling',
  },
] as const

const defaultChannelOptions: ChannelOption[] = [
  { value: 'meta_feed', label: 'Meta feed', supported_media_types: ['video', 'audio'] },
  { value: 'instagram_reels', label: 'Instagram Reels', supported_media_types: ['video'] },
  { value: 'tiktok', label: 'TikTok', supported_media_types: ['video'] },
  { value: 'youtube_pre_roll', label: 'YouTube pre-roll', supported_media_types: ['video', 'audio'] },
  { value: 'landing_page', label: 'Landing page', supported_media_types: ['video', 'text'] },
  { value: 'email', label: 'Email', supported_media_types: ['text'] },
] as const

const defaultGoalPresetGroups: GoalPresetGroup[] = [
  {
    id: 'paid_social',
    label: 'Paid social',
    description: 'Fast hook and native-feed review modes for short-form launches.',
    template_values: ['paid_social_hook', 'ugc_native_social'],
  },
  {
    id: 'web_conversion',
    label: 'Web conversion',
    description: 'Message clarity and clickthrough workflows for owned surfaces.',
    template_values: ['landing_page_clarity', 'email_clickthrough'],
  },
  {
    id: 'education',
    label: 'Education',
    description: 'Teaching-oriented review modes for demos, onboarding, and explainers.',
    template_values: ['education_explainer'],
  },
  {
    id: 'storytelling',
    label: 'Storytelling',
    description: 'Brand-memory and emotional continuity review for longer campaign cuts.',
    template_values: ['brand_story_film'],
  },
]

const defaultGoalSuggestions: GoalSuggestion[] = [
  {
    media_type: 'video',
    goal_template: 'paid_social_hook',
    channel: 'meta_feed',
    audience_placeholder: 'Cold prospecting, retargeting, creator-led lookalikes',
    rationale: 'Video uploads usually benefit from a short-form hook review first.',
  },
  {
    media_type: 'audio',
    goal_template: 'education_explainer',
    channel: 'youtube_pre_roll',
    audience_placeholder: 'Podcast listeners, webinar registrants, warm audio audiences',
    rationale: 'Audio assets usually need pacing and comprehension checks before channel-specific polish.',
  },
  {
    media_type: 'text',
    goal_template: 'landing_page_clarity',
    channel: 'landing_page',
    audience_placeholder: 'New visitors, ICP accounts, lifecycle email segments',
    rationale: 'Text uploads usually start with clarity and conversion-friction review.',
  },
]

const defaultGoalPresets: AnalysisGoalPresetsResponse = {
  goal_templates: [...defaultGoalTemplateOptions],
  channels: [...defaultChannelOptions],
  preset_groups: [...defaultGoalPresetGroups],
  suggestions: [...defaultGoalSuggestions],
}

const mediaTypeOptions: Array<{
  kind: MediaType
  title: string
  subtitle: string
  icon: typeof VideoLibraryRounded
  tone: string
}> = [
  {
    kind: 'video',
    title: 'Video',
    subtitle: 'MP4, MOV, or WebM source footage for timestamped creative analysis.',
    icon: VideoLibraryRounded,
    tone: '#3b5bdb',
  },
  {
    kind: 'audio',
    title: 'Audio',
    subtitle: 'Voiceovers and audio-led assets for retention and pacing analysis.',
    icon: AudiotrackRounded,
    tone: '#0f766e',
  },
  {
    kind: 'text',
    title: 'Text',
    subtitle: 'Paste copy or upload PDFs, DOC/DOCX, and common text documents for TRIBE-compatible analysis.',
    icon: DescriptionRounded,
    tone: '#f97316',
  },
]

const placeholderSummary: AnalysisSummary = {
  modality: 'video',
  overall_attention_score: 0,
  hook_score_first_3_seconds: 0,
  sustained_engagement_score: 0,
  memory_proxy_score: 0,
  cognitive_load_proxy: 0,
  confidence: null,
  completeness: null,
  notes: [],
  metadata: {
    objective: null,
    goal_template: null,
    channel: null,
    audience_segment: null,
    source_label: null,
    segment_count: 0,
    duration_ms: 0,
  },
}

const placeholderMetrics: AnalysisMetricRow[] = [
  {
    key: 'overall_attention_score',
    label: 'Overall Attention',
    value: 0,
    unit: '/100',
    source: 'pending',
    detail: 'Waiting for processed output.',
  },
  {
    key: 'hook_score_first_3_seconds',
    label: 'Hook Score First 3 Seconds',
    value: 0,
    unit: '/100',
    source: 'pending',
    detail: 'Waiting for processed output.',
  },
  {
    key: 'memory_proxy_score',
    label: 'Memory Proxy',
    value: 0,
    unit: '/100',
    source: 'pending',
    detail: 'Waiting for processed output.',
  },
]

const placeholderTimeline: AnalysisTimelinePoint[] = [
  { timestamp_ms: 0, engagement_score: 0, attention_score: 0, memory_proxy: 0 },
  { timestamp_ms: 1500, engagement_score: 0, attention_score: 0, memory_proxy: 0 },
  { timestamp_ms: 3000, engagement_score: 0, attention_score: 0, memory_proxy: 0 },
]

const placeholderSegments: AnalysisSegmentRow[] = [
  {
    segment_index: 0,
    label: 'Scene 01',
    start_time_ms: 0,
    end_time_ms: 1500,
    attention_score: 0,
    memory_proxy: 0,
    emotion_score: 0,
    cognitive_load: 0,
    conversion_proxy: 0,
    engagement_score: 0,
    engagement_delta: 0,
    peak_focus: 0,
    temporal_change: 0,
    consistency: 0,
    hemisphere_balance: 0,
    note: 'Upload and queue an analysis job to populate segment notes.',
  },
]

const placeholderHeatmapFrames: AnalysisHeatmapFrame[] = [
  {
    timestamp_ms: 0,
    label: 'Keyframe 1',
    scene_label: 'Scene 01',
    grid_rows: 3,
    grid_columns: 3,
    intensity_map: [
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
    ],
    strongest_zone: 'middle_center',
    caption: 'Fallback 2D grid overlay will appear here after inference.',
  },
]

const ANALYSIS_HISTORY_LIMIT = 12

function AnalysisPage({ onOpenCompareWorkspace, session }: AnalysisPageProps) {
  const storageScope = session.defaultProjectId || session.email
  const selectedAssetStorageKey = buildSelectedAssetStorageKey(storageScope)
  const selectedJobStorageKey = buildSelectedJobStorageKey(storageScope)
  const wizardStorageKey = buildAnalysisWizardStorageKey(storageScope)
  const compareWorkspaceStorageKey = buildCompareWorkspaceStorageKey(storageScope)
  const storedWizardSnapshot = readAnalysisWizardSnapshot(wizardStorageKey)
  const [config, setConfig] = useState<AnalysisConfigResponse | null>(null)
  const [goalPresets, setGoalPresets] = useState<AnalysisGoalPresetsResponse>(defaultGoalPresets)
  const [configError, setConfigError] = useState<string | null>(null)
  const [goalPresetsError, setGoalPresetsError] = useState<string | null>(null)
  const [selectedMediaType, setSelectedMediaType] = useState<MediaType>(storedWizardSnapshot?.mediaType ?? 'video')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [textContent, setTextContent] = useState('')
  const [textFilename, setTextFilename] = useState('analysis-notes.txt')
  const [objective, setObjective] = useState(storedWizardSnapshot?.objective ?? '')
  const [goalTemplate, setGoalTemplate] = useState(storedWizardSnapshot?.goalTemplate ?? '')
  const [channel, setChannel] = useState(storedWizardSnapshot?.channel ?? '')
  const [audienceSegment, setAudienceSegment] = useState(storedWizardSnapshot?.audienceSegment ?? '')
  const [isDragActive, setIsDragActive] = useState(false)
  const [isLoadingConfig, setIsLoadingConfig] = useState(true)
  const [isLoadingGoalPresets, setIsLoadingGoalPresets] = useState(true)
  const [bannerMessage, setBannerMessage] = useState<BannerMessage | null>(null)
  const [uploadState, setUploadState] = useState<UploadState>({
    stage: 'idle',
    progressPercent: 0,
    validationErrors: [],
  })
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null)
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [analysisPreviewResult, setAnalysisPreviewResult] = useState<AnalysisResult | null>(null)
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgressState | null>(null)
  const [evaluationProgress, setEvaluationProgress] = useState<AnalysisProgressState | null>(null)
  const [assetLibrary, setAssetLibrary] = useState<AnalysisAsset[]>([])
  const [isLoadingAssetLibrary, setIsLoadingAssetLibrary] = useState(false)
  const [hasLoadedAssetLibrary, setHasLoadedAssetLibrary] = useState(false)
  const [assetLibraryError, setAssetLibraryError] = useState<string | null>(null)
  const [assetLibraryRefreshNonce, setAssetLibraryRefreshNonce] = useState(0)
  const [analysisHistory, setAnalysisHistory] = useState<AnalysisJobListItem[]>([])
  const [isLoadingAnalysisHistory, setIsLoadingAnalysisHistory] = useState(false)
  const [hasLoadedAnalysisHistory, setHasLoadedAnalysisHistory] = useState(false)
  const [analysisHistoryError, setAnalysisHistoryError] = useState<string | null>(null)
  const [analysisHistoryRefreshNonce, setAnalysisHistoryRefreshNonce] = useState(0)
  const [activeLibraryAssetId, setActiveLibraryAssetId] = useState<string | null>(() =>
    readSelectedAnalysisAssetId(selectedAssetStorageKey),
  )
  const [activeHistoryJobId, setActiveHistoryJobId] = useState<string | null>(() =>
    readSelectedAnalysisJobId(selectedJobStorageKey),
  )
  const [selectionMode, setSelectionMode] = useState<AnalysisSelectionMode>(storedWizardSnapshot?.selectionMode ?? 'auto')
  const [loadingHistoryJobId, setLoadingHistoryJobId] = useState<string | null>(null)
  const [pendingHistorySelection, setPendingHistorySelection] = useState<AnalysisJobListItem | null>(null)
  const [analysisTransportMode, setAnalysisTransportMode] = useState<'stream' | 'polling'>('stream')
  const [analysisTransportDiagnostics, setAnalysisTransportDiagnostics] = useState<AnalysisTransportDiagnostics>({
    mode: 'stream',
    isConnected: false,
    reconnectCount: 0,
    lastError: null,
    lastConnectedAt: null,
    lastHeartbeatAt: null,
  })
  const [isHistoryDrawerOpen, setIsHistoryDrawerOpen] = useState(false)
  const [historyDrawerMode, setHistoryDrawerMode] = useState<HistoryDrawerMode>('resume')
  const [comparisonTarget, setComparisonTarget] = useState<AnalysisJobStatusResponse | null>(null)
  const [comparisonLoadingJobId, setComparisonLoadingJobId] = useState<string | null>(null)
  const [benchmarkResponse, setBenchmarkResponse] = useState<AnalysisBenchmarkResponse | null>(null)
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null)
  const [isLoadingBenchmark, setIsLoadingBenchmark] = useState(false)
  const [executiveVerdict, setExecutiveVerdict] = useState<AnalysisExecutiveVerdict | null>(null)
  const [executiveVerdictError, setExecutiveVerdictError] = useState<string | null>(null)
  const [isLoadingExecutiveVerdict, setIsLoadingExecutiveVerdict] = useState(false)
  const [calibrationResponse, setCalibrationResponse] = useState<AnalysisCalibrationResponse | null>(null)
  const [calibrationError, setCalibrationError] = useState<string | null>(null)
  const [isLoadingCalibration, setIsLoadingCalibration] = useState(false)
  const [generatedVariantsResponse, setGeneratedVariantsResponse] = useState<AnalysisGeneratedVariantListResponse | null>(null)
  const [generatedVariantsError, setGeneratedVariantsError] = useState<string | null>(null)
  const [isLoadingGeneratedVariants, setIsLoadingGeneratedVariants] = useState(false)
  const [isGeneratingVariants, setIsGeneratingVariants] = useState(false)
  const [isImportingOutcomes, setIsImportingOutcomes] = useState(false)
  const firstVisibleResultJobIdRef = useRef<string | null>(null)
  const completedResultJobIdRef = useRef<string | null>(null)
  const streamConnectedJobIdRef = useRef<string | null>(null)
  const streamFallbackJobIdRef = useRef<string | null>(null)
  const autoLoadedInsightsJobIdRef = useRef<string | null>(null)
  const latestInsightsRequestIdRef = useRef(0)
  const autoAppliedGoalAssetIdRef = useRef<string | null>(null)

  const clearGeneratedVariantsState = () => {
    setGeneratedVariantsResponse(null)
    setGeneratedVariantsError(null)
    setIsLoadingGeneratedVariants(false)
    setIsGeneratingVariants(false)
  }

  const sessionToken = session.sessionToken
  const currentMediaOption = mediaTypeOptions.find((option) => option.kind === selectedMediaType) ?? mediaTypeOptions[0]
  const availableGoalTemplates = goalPresets.goal_templates.filter((option) =>
    option.supported_media_types.includes(selectedMediaType),
  )
  const availableChannels = goalPresets.channels.filter((option) =>
    option.supported_media_types.includes(selectedMediaType),
  )
  const groupedGoalTemplates = goalPresets.preset_groups
    .map((group) => ({
      ...group,
      templates: availableGoalTemplates.filter((option) => group.template_values.includes(option.value)),
    }))
    .filter((group) => group.templates.length > 0)
  const suggestedGoalContext = resolveSuggestedGoalContext({
    suggestions: goalPresets.suggestions,
    mediaType: selectedMediaType,
    selectedAsset: uploadState.asset,
    selectedFile,
    textFilename,
  })
  const goalValidationErrors = validateGoalContext({
    channel,
    goalTemplate,
    mediaType: selectedMediaType,
    objective,
    availableChannels,
    availableGoalTemplates,
  })
  const CurrentMediaIcon = currentMediaOption.icon
  const visibleProgress = resolveVisibleProgressState(analysisProgress, evaluationProgress)
  const currentStage = resolveCurrentStage(visibleProgress?.stage, uploadState.stage, analysisJob?.status)
  const hasLocalDraft = selectedMediaType === 'text' ? Boolean(selectedFile || textContent.trim()) : Boolean(selectedFile)
  const hasGoalContext = Boolean(goalTemplate || channel || audienceSegment.trim() || objective.trim())
  const currentFlowStep = resolveAnalysisFlowStep({
    hasDraft: hasLocalDraft || uploadState.stage === 'uploaded',
    hasGoalContext,
    analysisJob,
    analysisResult,
  })
  const canUpload = Boolean(config && sessionToken && uploadState.stage !== 'uploading')
  const canStartAnalysis =
    Boolean(sessionToken) &&
    uploadState.stage === 'uploaded' &&
    Boolean(uploadState.asset) &&
    goalValidationErrors.length === 0 &&
    analysisJob?.status !== 'queued' &&
    analysisJob?.status !== 'processing'
  const selectedHistoryItem = analysisHistory.find((item) => item.job.id === activeHistoryJobId) ?? null
  const completedComparisonCandidates = analysisHistory.filter(
    (item) => item.has_result && item.job.id !== (analysisJob?.id ?? ''),
  )
  const resultsAsset = analysisResult || analysisJob ? uploadState.asset || selectedHistoryItem?.asset || null : null

  const applyAnalysisSnapshot = useEffectEvent(
    (
      statusResponse: AnalysisJobStatusResponse,
      options?: {
        historyItem?: AnalysisJobListItem | null
        announceSelection?: boolean
      },
    ) => {
      const historyItem = options?.historyItem ?? analysisHistory.find((item) => item.job.id === statusResponse.job.id) ?? null
      const nextAsset =
        statusResponse.asset ??
        historyItem?.asset ??
        (uploadState.asset?.id === statusResponse.job.asset_id ? uploadState.asset : null)
      const nextProgress = normalizeAnalysisProgressState(statusResponse.job.id, statusResponse.progress)

      if (nextAsset) {
        setActiveLibraryAssetId(nextAsset.id)
        storeSelectedAnalysisAssetId(selectedAssetStorageKey, nextAsset.id)
        setAssetLibrary((current) => mergeLatestAnalysisAsset(current, nextAsset))
        setUploadState((current) => {
          if (
            current.stage === 'uploaded' &&
            current.progressPercent === 100 &&
            current.validationErrors.length === 0 &&
            current.asset?.id === nextAsset.id
          ) {
            return current
          }
          return {
            stage: 'uploaded',
            progressPercent: 100,
            validationErrors: [],
            asset: nextAsset,
          }
        })
      }

      if (nextAsset && nextAsset.media_type !== selectedMediaType) {
        setSelectedMediaType(nextAsset.media_type)
      }
      if (nextAsset?.media_type === 'text' && nextAsset.original_filename) {
        setTextFilename(ensureTextFilename(nextAsset.original_filename))
      }

      setAnalysisJob((current) => (areAnalysisJobsEqual(current, statusResponse.job) ? current : statusResponse.job))
      if (statusResponse.result) {
        setAnalysisPreviewResult((current) => (current === null ? current : null))
      } else {
        if (analysisPreviewResult?.job_id && analysisPreviewResult.job_id !== statusResponse.job.id) {
          setAnalysisPreviewResult(null)
        }
      }
      if (nextProgress) {
        setAnalysisProgress((current) => (areAnalysisProgressStatesEqual(current, nextProgress) ? current : nextProgress))
      } else if (analysisProgress?.jobId && analysisProgress.jobId !== statusResponse.job.id) {
        setAnalysisProgress(null)
      } else if (statusResponse.job.status === 'failed') {
        setAnalysisProgress(null)
      }
      if (statusResponse.job.status === 'failed') {
        setAnalysisPreviewResult((current) => (current === null ? current : null))
      }
      setAnalysisResult((current) => (areAnalysisResultsEqual(current, statusResponse.result || null) ? current : statusResponse.result || null))
      setObjective((current) => {
        const nextObjective = statusResponse.job.objective || ''
        return current === nextObjective ? current : nextObjective
      })
      setGoalTemplate((current) => {
        const nextGoalTemplate =
          statusResponse.job.goal_template ||
          statusResponse.result?.summary_json.metadata?.goal_template ||
          ''
        return current === nextGoalTemplate ? current : nextGoalTemplate
      })
      setChannel((current) => {
        const nextChannel =
          statusResponse.job.channel ||
          statusResponse.result?.summary_json.metadata?.channel ||
          ''
        return current === nextChannel ? current : nextChannel
      })
      setAudienceSegment((current) => {
        const nextAudienceSegment =
          statusResponse.job.audience_segment ||
          statusResponse.result?.summary_json.metadata?.audience_segment ||
          ''
        return current === nextAudienceSegment ? current : nextAudienceSegment
      })
      setActiveHistoryJobId(statusResponse.job.id)
      storeSelectedAnalysisJobId(selectedJobStorageKey, statusResponse.job.id)
      setAnalysisHistory((current) =>
        upsertAnalysisHistoryItem(
          current,
          {
            job: statusResponse.job,
            asset: nextAsset,
            has_result: Boolean(statusResponse.result),
            result_created_at: statusResponse.result?.created_at ?? historyItem?.result_created_at ?? null,
          },
          ANALYSIS_HISTORY_LIMIT,
        ),
      )
      setSelectionMode('job')

      if (statusResponse.job.status === 'failed' && statusResponse.job.error_message) {
        setBannerMessage({
          type: 'error',
          message: statusResponse.job.error_message,
        })
        return
      }

      if (options?.announceSelection) {
        setBannerMessage({
          type: 'info',
          message: `Loaded ${nextAsset?.original_filename || 'analysis run'} from ${formatTimestamp(statusResponse.job.created_at)}.`,
        })
      }
    },
  )

  const applyAnalysisProgress = useEffectEvent((progressEvent: AnalysisProgressEvent) => {
    setAnalysisJob((current) => (areAnalysisJobsEqual(current, progressEvent.job) ? current : progressEvent.job))

    const nextAsset = progressEvent.asset ?? null
    if (nextAsset) {
      setActiveLibraryAssetId(nextAsset.id)
      storeSelectedAnalysisAssetId(selectedAssetStorageKey, nextAsset.id)
      setAssetLibrary((current) => mergeLatestAnalysisAsset(current, nextAsset))
      setUploadState((current) => {
        if (
          current.stage === 'uploaded' &&
          current.progressPercent === 100 &&
          current.validationErrors.length === 0 &&
          current.asset?.id === nextAsset.id
        ) {
          return current
        }
        return {
          stage: 'uploaded',
          progressPercent: 100,
          validationErrors: [],
          asset: nextAsset,
        }
      })
    }
    setActiveHistoryJobId((current) => (current === progressEvent.job.id ? current : progressEvent.job.id))
    storeSelectedAnalysisJobId(selectedJobStorageKey, progressEvent.job.id)
    setAnalysisHistory((current) =>
      upsertAnalysisHistoryItem(
        current,
        {
          job: progressEvent.job,
          asset: nextAsset ?? (uploadState.asset?.id === progressEvent.job.asset_id ? uploadState.asset : null),
          has_result: false,
          result_created_at: null,
        },
        ANALYSIS_HISTORY_LIMIT,
      ),
    )
    setSelectionMode((current) => (current === 'job' ? current : 'job'))

    const previewResult = progressEvent.result ?? null
    if (previewResult) {
      setAnalysisPreviewResult((current) =>
        areAnalysisResultsEqual(current, previewResult) ? current : previewResult,
      )
    }

    const nextProgress = normalizeAnalysisProgressState(progressEvent.job.id, progressEvent)
    if (nextProgress) {
      setAnalysisProgress((current) => (areAnalysisProgressStatesEqual(current, nextProgress) ? current : nextProgress))
    }
  })

  const handleEvaluationProgressSnapshot = useEffectEvent((progressSnapshot: AnalysisEvaluationProgressSnapshot | null) => {
    if (!progressSnapshot) {
      setEvaluationProgress(null)
      return
    }

    setEvaluationProgress((current) => {
      if (
        current?.jobId === progressSnapshot.jobId &&
        current.stage === progressSnapshot.stage &&
        current.stageLabel === progressSnapshot.stageLabel
      ) {
        return current
      }

      return {
        jobId: progressSnapshot.jobId,
        stage: progressSnapshot.stage,
        stageLabel: progressSnapshot.stageLabel,
        diagnostics:
          analysisProgress?.jobId === progressSnapshot.jobId
            ? analysisProgress.diagnostics
            : current?.diagnostics,
      }
    })
  })

  const loadAnalysisJob = useEffectEvent(async (jobId: string, options?: LoadAnalysisJobOptions) => {
    if (!sessionToken) {
      return
    }

    const historyItem = options?.historyItem ?? analysisHistory.find((item) => item.job.id === jobId) ?? null

    if (options?.showSelectionLoading) {
      setLoadingHistoryJobId(jobId)
    }

    try {
      const statusResponse = await fetchAnalysisJobDetails({
        jobId,
        sessionToken,
      })
      applyAnalysisSnapshot(statusResponse, {
        historyItem,
        announceSelection: options?.announceSelection,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load the selected analysis.',
      })
      void trackAnalysisClientEvent({
        eventName: 'analysis_load_failed',
        goalTemplateValue: historyItem?.job.goal_template || goalTemplate || null,
        channelValue: historyItem?.job.channel || channel || null,
        jobId,
        metadata: {
          source: options?.historyItem ? 'history' : 'direct',
        },
      })
    } finally {
      if (options?.showSelectionLoading) {
        setLoadingHistoryJobId((current) => (current === jobId ? null : current))
      }
    }
  })

  const loadAssetLibrary = useEffectEvent(async () => {
    if (!sessionToken) {
      setAssetLibrary([])
      setAssetLibraryError(null)
      setIsLoadingAssetLibrary(false)
      setHasLoadedAssetLibrary(true)
      return
    }

    setIsLoadingAssetLibrary(true)
    try {
      const response = await apiRequest<AnalysisAssetListResponse>(
        `/api/v1/analysis/assets?media_type=${encodeURIComponent(selectedMediaType)}&limit=12`,
        {
          sessionToken,
        },
      )
      setAssetLibrary(response.items)
      setAssetLibraryError(null)

      const storedAssetId = readSelectedAnalysisAssetId(selectedAssetStorageKey)
      const preferredAssetId =
        activeLibraryAssetId || (selectionMode === 'asset' ? storedAssetId : null)
      const preferredAsset =
        preferredAssetId != null
          ? response.items.find((asset) => asset.id === preferredAssetId && asset.upload_status === 'uploaded')
          : null
      const hasLocalDraft = selectedMediaType === 'text' ? Boolean(selectedFile || textContent.trim()) : Boolean(selectedFile)

      if (
        preferredAsset &&
        !hasLocalDraft &&
        uploadState.stage !== 'uploading' &&
        analysisJob == null &&
        selectionMode === 'asset'
      ) {
        setActiveLibraryAssetId(preferredAsset.id)
        setUploadState((current) =>
          current.asset?.id === preferredAsset.id && current.stage === 'uploaded'
            ? current
            : {
                stage: 'uploaded',
                progressPercent: 100,
                validationErrors: [],
                asset: preferredAsset,
              },
        )
      }
      setHasLoadedAssetLibrary(true)
    } catch (error) {
      setAssetLibraryError(error instanceof Error ? error.message : 'Unable to load uploaded analysis assets.')
      setHasLoadedAssetLibrary(true)
    } finally {
      setIsLoadingAssetLibrary(false)
    }
  })

  const loadAnalysisHistory = useEffectEvent(async () => {
    if (!sessionToken) {
      setAnalysisHistory([])
      setAnalysisHistoryError(null)
      setIsLoadingAnalysisHistory(false)
      setHasLoadedAnalysisHistory(true)
      return
    }

    setIsLoadingAnalysisHistory(true)
    try {
      const response = await apiRequest<AnalysisJobListResponse>(
        `/api/v1/analysis/jobs?media_type=${encodeURIComponent(selectedMediaType)}&limit=${ANALYSIS_HISTORY_LIMIT}`,
        {
          sessionToken,
        },
      )
      setAnalysisHistory(response.items)
      setAnalysisHistoryError(null)
      setHasLoadedAnalysisHistory(true)

      const storedJobId = readSelectedAnalysisJobId(selectedJobStorageKey)
      const preferredJobId =
        activeHistoryJobId || (selectionMode === 'job' ? storedJobId : null)
      const preferredHistoryItem =
        (analysisJob ? response.items.find((item) => item.job.id === analysisJob.id) : null) ||
        (preferredJobId ? response.items.find((item) => item.job.id === preferredJobId) : null) ||
        null

      if (!preferredHistoryItem) {
        setActiveHistoryJobId(null)
        if (selectionMode === 'job') {
          clearSelectedAnalysisJobId(selectedJobStorageKey)
        }
        return
      }

      if (
        selectionMode === 'job' &&
        !analysisJob &&
        !analysisResult &&
        uploadState.stage !== 'uploading' &&
        !hasLocalDraft
      ) {
        await loadAnalysisJob(preferredHistoryItem.job.id, {
          historyItem: preferredHistoryItem,
        })
        return
      }

      setActiveHistoryJobId(preferredHistoryItem.job.id)
      storeSelectedAnalysisJobId(selectedJobStorageKey, preferredHistoryItem.job.id)
    } catch (error) {
      setAnalysisHistoryError(error instanceof Error ? error.message : 'Unable to load recent analyses.')
      setHasLoadedAnalysisHistory(true)
    } finally {
      setIsLoadingAnalysisHistory(false)
    }
  })

  const trackAnalysisClientEvent = useEffectEvent(
    async ({
      eventName,
      goalTemplateValue,
      channelValue,
      jobId,
      metadata,
    }: {
      eventName: AnalysisClientEventName
      goalTemplateValue?: string | null
      channelValue?: string | null
      jobId?: string | null
      metadata?: Record<string, unknown>
    }) => {
      if (!sessionToken) {
        return
      }

      try {
        await apiRequest('/api/v1/analysis/events', {
          method: 'POST',
          sessionToken,
          body: {
            event_name: eventName,
            media_type: selectedMediaType,
            goal_template: goalTemplateValue || null,
            channel: channelValue || null,
            audience_segment: audienceSegment.trim() || null,
            job_id: jobId || null,
            metadata_json: {
              selection_mode: selectionMode,
              transport_mode: analysisTransportMode,
              ...metadata,
            },
          },
        })
      } catch {
        // Client analytics events should never block the analysis workflow.
      }
    },
  )

  const loadAnalysisInsights = useEffectEvent(async (jobId: string) => {
    if (!sessionToken) {
      return
    }

    const requestId = latestInsightsRequestIdRef.current + 1
    latestInsightsRequestIdRef.current = requestId

    setIsLoadingBenchmark(true)
    setIsLoadingExecutiveVerdict(true)
    setIsLoadingCalibration(true)
    setIsLoadingGeneratedVariants(true)
    setBenchmarkError(null)
    setExecutiveVerdictError(null)
    setCalibrationError(null)
    setGeneratedVariantsError(null)

    const [benchmarkResult, verdictResult, calibrationResult, variantsResult] = await Promise.allSettled([
      apiRequest<AnalysisBenchmarkResponse>(`/api/v1/analysis/jobs/${jobId}/benchmarks`, { sessionToken }),
      apiRequest<AnalysisExecutiveVerdict>(`/api/v1/analysis/jobs/${jobId}/verdict`, { sessionToken }),
      apiRequest<AnalysisCalibrationResponse>(`/api/v1/analysis/jobs/${jobId}/calibration`, { sessionToken }),
      apiRequest<AnalysisGeneratedVariantListResponse>(`/api/v1/analysis/jobs/${jobId}/variants`, { sessionToken }),
    ])

    if (latestInsightsRequestIdRef.current !== requestId) {
      return
    }

    if (benchmarkResult.status === 'fulfilled') {
      setBenchmarkResponse(benchmarkResult.value)
    } else {
      setBenchmarkResponse(null)
      setBenchmarkError(
        benchmarkResult.reason instanceof Error
          ? benchmarkResult.reason.message
          : 'Unable to load benchmark context.',
      )
    }

    if (verdictResult.status === 'fulfilled') {
      setExecutiveVerdict(verdictResult.value)
    } else {
      setExecutiveVerdict(null)
      setExecutiveVerdictError(
        verdictResult.reason instanceof Error
          ? verdictResult.reason.message
          : 'Unable to load the executive verdict.',
      )
    }

    if (calibrationResult.status === 'fulfilled') {
      setCalibrationResponse(calibrationResult.value)
    } else {
      setCalibrationResponse(null)
      setCalibrationError(
        calibrationResult.reason instanceof Error
          ? calibrationResult.reason.message
          : 'Unable to load calibration observations.',
      )
    }

    if (variantsResult.status === 'fulfilled') {
      setGeneratedVariantsResponse(variantsResult.value)
    } else {
      setGeneratedVariantsResponse(null)
      setGeneratedVariantsError(
        variantsResult.reason instanceof Error
          ? variantsResult.reason.message
          : 'Unable to load generated variants.',
      )
    }

    setIsLoadingBenchmark(false)
    setIsLoadingExecutiveVerdict(false)
    setIsLoadingCalibration(false)
    setIsLoadingGeneratedVariants(false)
  })

  useEffect(() => {
    storeAnalysisWizardSnapshot(wizardStorageKey, {
      mediaType: selectedMediaType,
      objective,
      goalTemplate,
      channel,
      audienceSegment,
      selectionMode,
    })
  }, [audienceSegment, channel, goalTemplate, objective, selectedMediaType, selectionMode, wizardStorageKey])

  useEffect(() => {
    const availableTemplateValues = new Set(availableGoalTemplates.map((option) => option.value))
    const availableChannelValues = new Set(availableChannels.map((option) => option.value))

    if (goalTemplate && !availableTemplateValues.has(goalTemplate)) {
      setGoalTemplate('')
    }
    if (channel && !availableChannelValues.has(channel)) {
      setChannel('')
    }
  }, [availableChannels, availableGoalTemplates, channel, goalTemplate])

  useEffect(() => {
    if (uploadState.stage !== 'uploaded' || !uploadState.asset) {
      autoAppliedGoalAssetIdRef.current = null
      return
    }

    const assetId = uploadState.asset.id
    if (autoAppliedGoalAssetIdRef.current === assetId) {
      return
    }

    const hasValidGoalTemplate = availableGoalTemplates.some((option) => option.value === goalTemplate)
    const hasValidChannel = availableChannels.some((option) => option.value === channel)
    if (hasValidGoalTemplate && hasValidChannel) {
      autoAppliedGoalAssetIdRef.current = assetId
      return
    }

    const suggestedContext = resolveSuggestedGoalContext({
      suggestions: goalPresets.suggestions,
      mediaType: selectedMediaType,
      selectedAsset: uploadState.asset,
      selectedFile,
      textFilename,
    })
    if (!suggestedContext) {
      return
    }

    const suggestedTemplateSupported = availableGoalTemplates.some(
      (option) => option.value === suggestedContext.goal_template,
    )
    const suggestedChannelSupported = availableChannels.some(
      (option) => option.value === suggestedContext.channel,
    )
    if (!suggestedTemplateSupported || !suggestedChannelSupported) {
      return
    }

    if (!hasValidGoalTemplate) {
      setGoalTemplate(suggestedContext.goal_template)
    }
    if (!hasValidChannel) {
      setChannel(suggestedContext.channel)
    }
    autoAppliedGoalAssetIdRef.current = assetId
  }, [
    availableChannels,
    availableGoalTemplates,
    channel,
    goalPresets.suggestions,
    goalTemplate,
    selectedFile,
    selectedMediaType,
    textFilename,
    uploadState.asset,
    uploadState.stage,
  ])

  useEffect(() => {
    const loadConfig = async () => {
      if (!sessionToken) {
        setConfigError('Sign out and sign in again to enable uploads for this workspace.')
        setIsLoadingConfig(false)
        return
      }

      try {
        const nextConfig = await apiRequest<AnalysisConfigResponse>('/api/v1/analysis/config', {
          sessionToken,
        })
        setConfig(nextConfig)
        setConfigError(null)
      } catch (error) {
        setConfigError(error instanceof Error ? error.message : 'Unable to load analysis upload settings.')
      } finally {
        setIsLoadingConfig(false)
      }
    }

    void loadConfig()
  }, [sessionToken])

  useEffect(() => {
    const loadGoalPresets = async () => {
      if (!sessionToken) {
        setGoalPresets(defaultGoalPresets)
        setGoalPresetsError('Sign out and sign in again to load goal presets for this workspace.')
        setIsLoadingGoalPresets(false)
        return
      }

      try {
        const response = await apiRequest<AnalysisGoalPresetsResponse>('/api/v1/analysis/goal-presets', {
          sessionToken,
        })
        setGoalPresets(response)
        setGoalPresetsError(null)
      } catch (error) {
        setGoalPresets(defaultGoalPresets)
        setGoalPresetsError(error instanceof Error ? error.message : 'Unable to load goal presets. Using local defaults.')
      } finally {
        setIsLoadingGoalPresets(false)
      }
    }

    void loadGoalPresets()
  }, [sessionToken])

  useEffect(() => {
    void loadAssetLibrary()
  }, [assetLibraryRefreshNonce, selectedMediaType, sessionToken])

  useEffect(() => {
    if (hasLoadedAnalysisHistory && analysisHistoryRefreshNonce === 0) {
      return
    }
    const cancelDeferredLoad = runWhenIdle(() => {
      void loadAnalysisHistory()
    })
    return cancelDeferredLoad
  }, [analysisHistoryRefreshNonce, hasLoadedAnalysisHistory, loadAnalysisHistory, selectedMediaType, sessionToken])

  useEffect(() => {
    if (!isHistoryDrawerOpen || isLoadingAnalysisHistory || hasLoadedAnalysisHistory) {
      return
    }
    void loadAnalysisHistory()
  }, [hasLoadedAnalysisHistory, isHistoryDrawerOpen, isLoadingAnalysisHistory, loadAnalysisHistory])

  useEffect(() => {
    setAnalysisTransportMode('stream')
    setAnalysisTransportDiagnostics({
      mode: 'stream',
      isConnected: false,
      reconnectCount: 0,
      lastError: null,
      lastConnectedAt: null,
      lastHeartbeatAt: null,
    })
    streamConnectedJobIdRef.current = null
    streamFallbackJobIdRef.current = null
  }, [analysisJob?.id])

  useEffect(() => {
    setEvaluationProgress(null)
  }, [analysisJob?.id])

  useEffect(() => {
    const resultJobId = analysisResult?.job_id ?? null

    if (!analysisJob?.id || analysisJob.status !== 'completed' || !resultJobId) {
      autoLoadedInsightsJobIdRef.current = null
      latestInsightsRequestIdRef.current += 1
      setBenchmarkResponse(null)
      setExecutiveVerdict(null)
      setCalibrationResponse(null)
      setGeneratedVariantsResponse(null)
      setBenchmarkError(null)
      setExecutiveVerdictError(null)
      setCalibrationError(null)
      setGeneratedVariantsError(null)
      setIsLoadingGeneratedVariants(false)
      setIsGeneratingVariants(false)
      return
    }

    if (autoLoadedInsightsJobIdRef.current === resultJobId) {
      return
    }

    autoLoadedInsightsJobIdRef.current = resultJobId
    void loadAnalysisInsights(resultJobId)
  }, [analysisJob?.id, analysisJob?.status, analysisResult?.job_id])

  useEffect(() => {
    if (!analysisJob || !sessionToken) {
      return
    }
    if (analysisJob.status === 'completed' || analysisJob.status === 'failed') {
      return
    }

    if (analysisTransportMode === 'polling') {
      const intervalId = window.setInterval(() => {
        void loadAnalysisJob(analysisJob.id)
      }, 4_000)

      return () => {
        window.clearInterval(intervalId)
      }
    }

    const unsubscribe = subscribeToEventStream<AnalysisJobStatusResponse | AnalysisProgressEvent>({
      path: `/api/v1/analysis/jobs/${analysisJob.id}/events`,
      sessionToken,
      onMessage: ({ event, data }) => {
        if (streamConnectedJobIdRef.current !== analysisJob.id) {
          streamConnectedJobIdRef.current = analysisJob.id
          setAnalysisTransportDiagnostics((current) => ({
            ...current,
            mode: 'stream',
            isConnected: true,
            lastError: null,
            lastConnectedAt: new Date().toISOString(),
            lastHeartbeatAt: current.lastHeartbeatAt,
          }))
          void trackAnalysisClientEvent({
            eventName: 'analysis_stream_connected',
            goalTemplateValue: analysisJob.goal_template || goalTemplate || null,
            channelValue: analysisJob.channel || channel || null,
            jobId: analysisJob.id,
            metadata: {
              transport_mode: 'stream',
            },
          })
        }
        if (event === 'heartbeat') {
          setAnalysisTransportDiagnostics((current) => ({
            ...current,
            mode: 'stream',
            isConnected: true,
            lastError: null,
            lastHeartbeatAt: new Date().toISOString(),
          }))
          return
        }
        if (event === 'progress') {
          applyAnalysisProgress(data as AnalysisProgressEvent)
          return
        }
        applyAnalysisSnapshot(data as AnalysisJobStatusResponse)
      },
      onError: (error) => {
        setAnalysisTransportMode('polling')
        setAnalysisTransportDiagnostics((current) => ({
          mode: 'polling',
          isConnected: false,
          reconnectCount: current.reconnectCount + 1,
          lastError: error.message,
          lastConnectedAt: current.lastConnectedAt,
          lastHeartbeatAt: current.lastHeartbeatAt,
        }))
        streamConnectedJobIdRef.current = null
        if (streamFallbackJobIdRef.current !== analysisJob.id) {
          streamFallbackJobIdRef.current = analysisJob.id
          void trackAnalysisClientEvent({
            eventName: 'analysis_stream_fallback',
            goalTemplateValue: analysisJob.goal_template || goalTemplate || null,
            channelValue: analysisJob.channel || channel || null,
            jobId: analysisJob.id,
            metadata: {
              transport_mode: 'polling',
              stream_error: error.message,
            },
          })
        }
      },
    })

    return () => {
      unsubscribe()
    }
  // Use primitive deps (id + status) instead of the full object so that progress
  // events — which replace `analysisJob` with a new object of the same id/status —
  // do NOT tear down and re-open the stream on every message.
  }, [analysisJob?.id, analysisJob?.status, analysisTransportMode, sessionToken])

  useEffect(() => {
    if (!pendingHistorySelection) {
      return
    }

    const selectedHistoryItem = pendingHistorySelection
    void loadAnalysisJob(selectedHistoryItem.job.id, {
      historyItem: selectedHistoryItem,
      announceSelection: true,
      showSelectionLoading: true,
    }).finally(() => {
      setPendingHistorySelection((current) =>
        current?.job.id === selectedHistoryItem.job.id ? null : current,
      )
    })
  }, [pendingHistorySelection])

  const visibleAnalysisResult = analysisResult ?? analysisPreviewResult
  const stageAvailability = resolveAnalysisStageAvailability({
    analysisResult,
    analysisPreviewResult,
    currentStage,
  })

  useEffect(() => {
    if (!visibleAnalysisResult) {
      return
    }

    const jobId = visibleAnalysisResult.job_id
    if (firstVisibleResultJobIdRef.current === jobId) {
      return
    }

    firstVisibleResultJobIdRef.current = jobId
    void trackAnalysisClientEvent({
      eventName: 'first_result_seen',
      goalTemplateValue:
        analysisJob?.goal_template || visibleAnalysisResult.summary_json.metadata?.goal_template || goalTemplate || null,
      channelValue:
        analysisJob?.channel || visibleAnalysisResult.summary_json.metadata?.channel || channel || null,
      jobId,
      metadata: {
        result_kind: analysisResult?.job_id === jobId ? 'final' : 'partial',
        progress_stage: analysisProgress?.stage || null,
        recommendation_count: visibleAnalysisResult.recommendations_json.length,
        time_to_first_result_ms:
          analysisProgress?.diagnostics?.timeToFirstResultMs ??
          calculateElapsedMs(analysisJob?.created_at ?? null, visibleAnalysisResult.created_at),
        queue_wait_ms: analysisProgress?.diagnostics?.queueWaitMs ?? null,
        processing_duration_ms: analysisProgress?.diagnostics?.processingDurationMs ?? null,
      },
    })
  }, [
    analysisJob?.channel,
    analysisJob?.goal_template,
    analysisProgress?.diagnostics?.processingDurationMs,
    analysisProgress?.stage,
    analysisResult?.job_id,
    channel,
    goalTemplate,
    trackAnalysisClientEvent,
    visibleAnalysisResult,
  ])

  useEffect(() => {
    if (!analysisResult || analysisJob?.status !== 'completed') {
      return
    }

    const jobId = analysisResult.job_id
    if (completedResultJobIdRef.current === jobId) {
      return
    }

    completedResultJobIdRef.current = jobId
    void trackAnalysisClientEvent({
      eventName: 'analysis_completed',
      goalTemplateValue:
        analysisJob.goal_template || analysisResult.summary_json.metadata?.goal_template || goalTemplate || null,
      channelValue:
        analysisJob.channel || analysisResult.summary_json.metadata?.channel || channel || null,
      jobId,
      metadata: {
        recommendation_count: analysisResult.recommendations_json.length,
        timeline_points: analysisResult.timeline_json.length,
        result_delivery_ms:
          analysisProgress?.diagnostics?.resultDeliveryMs ??
          calculateElapsedMs(analysisJob.created_at, analysisResult.created_at),
        queue_wait_ms: analysisProgress?.diagnostics?.queueWaitMs ?? null,
        processing_duration_ms:
          analysisProgress?.diagnostics?.processingDurationMs ??
          calculateElapsedMs(analysisJob.started_at ?? null, analysisResult.created_at),
      },
    })
  }, [analysisJob, analysisProgress?.diagnostics?.processingDurationMs, analysisProgress?.diagnostics?.queueWaitMs, analysisProgress?.diagnostics?.resultDeliveryMs, analysisResult, channel, goalTemplate, trackAnalysisClientEvent])

  const handleMediaTypeChange = (nextMediaType: MediaType) => {
    if (nextMediaType === selectedMediaType) {
      return
    }

    setSelectedMediaType(nextMediaType)
    setSelectionMode('auto')
    setSelectedFile(null)
    setTextContent('')
    setTextFilename('analysis-notes.txt')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    resetWorkflowState(
      setUploadState,
      setAnalysisJob,
      setAnalysisResult,
      setAnalysisPreviewResult,
      setAnalysisProgress,
      setBannerMessage,
    )
  }

  const handleBinaryFileSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    event.target.value = ''
    setSelectedFile(file)
    setSelectionMode('asset')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    resetWorkflowState(
      setUploadState,
      setAnalysisJob,
      setAnalysisResult,
      setAnalysisPreviewResult,
      setAnalysisProgress,
      setBannerMessage,
    )
  }

  const handleTextFileSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    event.target.value = ''

    setSelectedFile(file)
    setTextContent('')
    setTextFilename(ensureTextFilename(file.name))
    setSelectionMode('asset')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    resetWorkflowState(
      setUploadState,
      setAnalysisJob,
      setAnalysisResult,
      setAnalysisPreviewResult,
      setAnalysisProgress,
      setBannerMessage,
    )
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragActive(false)

    const file = event.dataTransfer.files?.[0]
    if (!file) {
      return
    }

    setSelectedFile(file)
    setSelectionMode('asset')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    resetWorkflowState(
      setUploadState,
      setAnalysisJob,
      setAnalysisResult,
      setAnalysisPreviewResult,
      setAnalysisProgress,
      setBannerMessage,
    )
  }

  const handleSelectUploadedAsset = (asset: AnalysisAsset) => {
    if (asset.upload_status !== 'uploaded') {
      return
    }

    setSelectedFile(null)
    setTextContent('')
    setTextFilename(ensureTextFilename(asset.original_filename || 'analysis-notes.txt'))
    setAnalysisJob(null)
    setAnalysisResult(null)
    setAnalysisPreviewResult(null)
    setAnalysisProgress(null)
    setSelectionMode('asset')
    setActiveLibraryAssetId(asset.id)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    storeSelectedAnalysisAssetId(selectedAssetStorageKey, asset.id)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    setUploadState({
      stage: 'uploaded',
      progressPercent: 100,
      validationErrors: [],
      asset,
    })
    setBannerMessage({
      type: 'info',
      message: `${asset.original_filename || 'Uploaded asset'} is selected from your stored media library.`,
    })
  }

  const handleUpload = async () => {
    if (!config || !sessionToken) {
      return
    }

    setUploadState({
      stage: 'validating',
      progressPercent: 0,
      validationErrors: [],
    })

    const validationErrors = validateCurrentInput({
      config,
      mediaType: selectedMediaType,
      selectedFile,
      textContent,
    })
    if (validationErrors.length > 0) {
      void trackAnalysisClientEvent({
        eventName: 'upload_validation_failed',
        goalTemplateValue: goalTemplate || null,
        channelValue: channel || null,
        metadata: {
          validation_error_count: validationErrors.length,
          validation_errors: validationErrors,
        },
      })
      setUploadState({
        stage: 'failed',
        progressPercent: 0,
        validationErrors,
        errorMessage: validationErrors[0],
      })
      return
    }

    const uploadSource = buildUploadSource({
      mediaType: selectedMediaType,
      selectedFile,
      textContent,
      textFilename,
    })
    if (!uploadSource) {
      return
    }

    setBannerMessage(null)
    setAnalysisJob(null)
    setAnalysisResult(null)
    setAnalysisPreviewResult(null)
    setAnalysisProgress(null)
    setSelectionMode('asset')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    setUploadState({
      stage: 'uploading',
      progressPercent: 0,
      validationErrors: [],
    })
    void trackAnalysisClientEvent({
      eventName: 'upload_started',
      goalTemplateValue: goalTemplate || null,
      channelValue: channel || null,
      metadata: {
        file_name: uploadSource.fileName,
        mime_type: uploadSource.mimeType,
        size_bytes: uploadSource.sizeBytes,
        source_kind:
          selectedMediaType === 'text' ? (selectedFile ? 'uploaded_document' : 'draft_text') : 'local_file',
      },
    })

    try {
      const initResponse = await apiRequest<AnalysisUploadCreateResponse>('/api/v1/analysis/uploads', {
        method: 'POST',
        sessionToken,
        body: {
          media_type: selectedMediaType,
          original_filename: uploadSource.fileName,
          mime_type: uploadSource.mimeType,
          size_bytes: uploadSource.sizeBytes,
        },
      })

      let completedResponse: AnalysisUploadCompleteResponse
      let usedBackendFallback = false

      try {
        await uploadToSignedUrl({
          file: uploadSource.file,
          url: initResponse.upload_url,
          contentType: uploadSource.mimeType,
          onProgress: (progressPercent) => {
            setUploadState((current) => ({
              ...current,
              stage: 'uploading',
              progressPercent,
              validationErrors: [],
            }))
          },
        })

        completedResponse = await apiRequest<AnalysisUploadCompleteResponse>(
          `/api/v1/analysis/uploads/${initResponse.upload_session.id}/complete`,
          {
            method: 'POST',
            sessionToken,
            body: {
              upload_token: initResponse.upload_session.upload_token,
            },
          },
        )
      } catch (directUploadError) {
        usedBackendFallback = true
        setBannerMessage({
          type: 'info',
          message: 'Direct browser upload was blocked. Retrying through the backend upload proxy.',
        })
        completedResponse = await uploadToApi<AnalysisUploadCompleteResponse>({
          path: `/api/v1/analysis/uploads/${initResponse.upload_session.id}/fallback`,
          sessionToken,
          file: uploadSource.file,
          fileName: uploadSource.fileName,
          fields: {
            upload_token: initResponse.upload_session.upload_token,
          },
          onProgress: (progressPercent) => {
            setUploadState((current) => ({
              ...current,
              stage: 'uploading',
              progressPercent,
              validationErrors: [],
            }))
          },
        }).catch((fallbackError) => {
          const directMessage =
            directUploadError instanceof Error ? directUploadError.message : 'Direct upload failed.'
          const fallbackMessage =
            fallbackError instanceof Error ? fallbackError.message : 'Backend upload failed.'
          throw new Error(`${directMessage} Fallback upload also failed: ${fallbackMessage}`)
        })
      }

      setUploadState({
        stage: 'uploaded',
        progressPercent: 100,
        validationErrors: [],
        asset: completedResponse.asset,
        uploadSession: completedResponse.upload_session,
      })
      setSelectionMode('asset')
      setActiveLibraryAssetId(completedResponse.asset.id)
      storeSelectedAnalysisAssetId(selectedAssetStorageKey, completedResponse.asset.id)
      setAssetLibrary((current) => mergeLatestAnalysisAsset(current, completedResponse.asset))
      setBannerMessage({
        type: usedBackendFallback ? 'info' : 'success',
        message: usedBackendFallback
          ? 'Upload completed through the backend proxy. The asset is ready to queue for analysis.'
          : 'Upload completed. The asset is ready to queue for analysis.',
      })
      void trackAnalysisClientEvent({
        eventName: 'upload_completed',
        goalTemplateValue: goalTemplate || null,
        channelValue: channel || null,
        metadata: {
          asset_id: completedResponse.asset.id,
          upload_session_id: completedResponse.upload_session.id,
          used_backend_fallback: usedBackendFallback,
        },
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Upload failed.'
      setUploadState({
        stage: 'failed',
        progressPercent: 0,
        validationErrors: [message],
        errorMessage: message,
      })
      setBannerMessage({
        type: 'error',
        message,
      })
    }
  }

  const handleStartAnalysis = async () => {
    if (!sessionToken || !uploadState.asset) {
      return
    }

    const isRetry = analysisJob?.status === 'failed'
    setBannerMessage(null)
    clearGeneratedVariantsState()
    setAnalysisPreviewResult(null)
    setAnalysisProgress(null)
    try {
      const response = await apiRequest<AnalysisJobStatusResponse>('/api/v1/analysis/jobs', {
        method: 'POST',
        sessionToken,
        body: {
          asset_id: uploadState.asset.id,
          objective: objective.trim() || null,
          goal_template: goalTemplate || null,
          channel: channel || null,
          audience_segment: audienceSegment.trim() || null,
        },
      })
      setAnalysisJob(response.job)
      setAnalysisResult(response.result || null)
      if (response.asset) {
        setUploadState((current) => ({
          ...current,
          stage: 'uploaded',
          progressPercent: 100,
          validationErrors: [],
          asset: response.asset || current.asset,
        }))
      }
      setSelectionMode('job')
      setActiveHistoryJobId(response.job.id)
      storeSelectedAnalysisJobId(selectedJobStorageKey, response.job.id)
      setAnalysisHistory((current) =>
        upsertAnalysisHistoryItem(
          current,
          {
            job: response.job,
            asset: uploadState.asset || null,
            has_result: Boolean(response.result),
            result_created_at: response.result?.created_at ?? null,
          },
          ANALYSIS_HISTORY_LIMIT,
        ),
      )
      void trackAnalysisClientEvent({
        eventName: isRetry ? 'analysis_retry_clicked' : 'analysis_started',
        goalTemplateValue: response.job.goal_template || goalTemplate || null,
        channelValue: response.job.channel || channel || null,
        jobId: response.job.id,
        metadata: {
          asset_id: uploadState.asset.id,
          objective_length: objective.trim().length,
        },
      })
      setBannerMessage({
        type: 'info',
        message:
          response.job.status === 'queued'
            ? 'Analysis job queued. Status will update automatically.'
            : 'Analysis job started.',
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to queue the analysis job.',
      })
    }
  }

  const handleSelectAnalysisHistoryItem = (item: AnalysisJobListItem) => {
    setSelectedFile(null)
    setTextContent('')
    setSelectionMode('job')
    if (item.asset?.media_type === 'text' && item.asset.original_filename) {
      setTextFilename(ensureTextFilename(item.asset.original_filename))
    }
    setIsHistoryDrawerOpen(false)
    setPendingHistorySelection(item)
  }

  const openHistoryDrawer = (mode: HistoryDrawerMode = 'resume') => {
    setHistoryDrawerMode(mode)
    setIsHistoryDrawerOpen(true)
    if (mode === 'compare') {
      void trackAnalysisClientEvent({
        eventName: 'quick_compare_opened',
        goalTemplateValue: goalTemplate || analysisJob?.goal_template || null,
        channelValue: channel || analysisJob?.channel || null,
        jobId: analysisJob?.id ?? null,
      })
    }
  }

  const handleSelectComparisonTarget = async (item: AnalysisJobListItem) => {
    if (!sessionToken || item.job.id === analysisJob?.id) {
      return
    }

    setComparisonLoadingJobId(item.job.id)
    try {
      const statusResponse = await fetchAnalysisJobDetails({
        jobId: item.job.id,
        sessionToken,
      })
      setComparisonTarget({
        ...statusResponse,
        asset: statusResponse.asset ?? item.asset ?? null,
      })
      setIsHistoryDrawerOpen(false)
      setBannerMessage({
        type: 'info',
        message: `Prepared a quick comparison against ${item.asset?.original_filename || shortenId(item.job.id)}.`,
      })
      void trackAnalysisClientEvent({
        eventName: 'quick_compare_loaded',
        goalTemplateValue: goalTemplate || analysisJob?.goal_template || statusResponse.job.goal_template || null,
        channelValue: channel || analysisJob?.channel || statusResponse.job.channel || null,
        jobId: statusResponse.job.id,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load the comparison target.',
      })
    } finally {
      setComparisonLoadingJobId((current) => (current === item.job.id ? null : current))
    }
  }

  const handleExportCurrentAnalysis = () => {
    if (!analysisJob || !analysisResult) {
      return
    }

    void trackAnalysisClientEvent({
      eventName: 'export_clicked',
      goalTemplateValue: analysisJob.goal_template || goalTemplate || null,
      channelValue: analysisJob.channel || channel || null,
      jobId: analysisJob.id,
      metadata: {
        recommendation_count: analysisResult.recommendations_json.length,
      },
    })

    const fileStem = sanitizeDownloadFilename(resultsAsset?.original_filename || `analysis-${analysisJob.id}`)
    downloadBlob({
      filename: `${fileStem}-report.json`,
      mimeType: 'application/json',
      content: JSON.stringify(
        {
          exported_at: new Date().toISOString(),
          workspace: session.organizationName || 'Primary workspace',
          project: session.defaultProjectName || 'Default Analysis Project',
          job: analysisJob,
          asset: resultsAsset,
          result: analysisResult,
        },
        null,
        2,
      ),
    })
    setBannerMessage({
      type: 'success',
      message: 'Downloaded the current analysis report as JSON.',
    })
  }

  const handleGenerateVariants = async () => {
    if (!analysisJob || !analysisResult || !sessionToken) {
      return
    }

    setIsGeneratingVariants(true)
    setGeneratedVariantsError(null)
    try {
      const response = await apiRequest<AnalysisGeneratedVariantListResponse>(
        `/api/v1/analysis/jobs/${analysisJob.id}/variants`,
        {
          method: 'POST',
          sessionToken,
          body: {
            variant_types: ['hook_rewrite', 'cta_rewrite', 'shorter_script', 'alternate_thumbnail'],
            replace_existing: true,
          },
        },
      )
      setGeneratedVariantsResponse(response)
      setBannerMessage({
        type: 'success',
        message: `Generated ${response.items.length} action-ready variant${response.items.length === 1 ? '' : 's'} from the current analysis.`,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to generate action-ready variants.'
      setGeneratedVariantsError(message)
      setBannerMessage({
        type: 'error',
        message,
      })
    } finally {
      setIsGeneratingVariants(false)
    }
  }

  const handleDownloadGeneratedVariant = (variant: AnalysisGeneratedVariant) => {
    if (!analysisJob) {
      return
    }

    const fileStem = sanitizeDownloadFilename(resultsAsset?.original_filename || `analysis-${analysisJob.id}`)
    downloadBlob({
      filename: `${fileStem}-${variant.variant_type}.txt`,
      mimeType: 'text/plain;charset=utf-8',
      content: buildGeneratedVariantText({
        asset: resultsAsset,
        job: analysisJob,
        variant,
      }),
    })
  }

  const handleCopyGeneratedVariant = async (variant: AnalysisGeneratedVariant) => {
    if (!analysisJob || !navigator.clipboard) {
      return
    }

    try {
      await navigator.clipboard.writeText(
        buildGeneratedVariantText({
          asset: resultsAsset,
          job: analysisJob,
          variant,
        }),
      )
      setBannerMessage({
        type: 'success',
        message: `Copied the ${readableGeneratedVariantType(variant.variant_type)} to the clipboard.`,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to copy the generated variant.',
      })
    }
  }

  const handleImportOutcomeFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !sessionToken || !analysisJob) {
      return
    }

    setIsImportingOutcomes(true)
    try {
      const response = await uploadToApi<AnalysisOutcomeImportResponse>({
        path: '/api/v1/analysis/outcomes/import',
        sessionToken,
        file,
        fileName: file.name,
      })
      await loadAnalysisInsights(analysisJob.id)
      setBannerMessage({
        type: response.failed_rows > 0 ? 'info' : 'success',
        message:
          response.failed_rows > 0
            ? `Imported ${response.imported_events} outcomes and ${response.imported_observations} calibration observations. ${response.failed_rows} rows were skipped.`
            : `Imported ${response.imported_events} outcomes and ${response.imported_observations} calibration observations.`,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to import the CSV outcome file.',
      })
    } finally {
      setIsImportingOutcomes(false)
    }
  }

  const handleApplySuggestedGoalContext = () => {
    if (!suggestedGoalContext) {
      return
    }

    setGoalTemplate(suggestedGoalContext.goal_template)
    setChannel(suggestedGoalContext.channel)
    setBannerMessage({
      type: 'info',
      message: `Applied the recommended ${readableGoalTemplate(suggestedGoalContext.goal_template)} setup for this ${selectedMediaType} asset.`,
    })
    void trackAnalysisClientEvent({
      eventName: 'goal_suggestion_applied',
      goalTemplateValue: suggestedGoalContext.goal_template,
      channelValue: suggestedGoalContext.channel,
      jobId: analysisJob?.id ?? null,
    })
  }

  const summary = visibleAnalysisResult?.summary_json ?? placeholderSummary
  const metricsRows = visibleAnalysisResult?.metrics_json ?? placeholderMetrics
  const timelinePoints = visibleAnalysisResult?.timeline_json ?? placeholderTimeline
  const segmentsRows = visibleAnalysisResult?.segments_json ?? placeholderSegments
  const heatmapFrames = visibleAnalysisResult?.visualizations_json.heatmap_frames ?? placeholderHeatmapFrames
  const frameBreakdownItems = buildFrameBreakdownItems({
    timelinePoints,
    segmentsRows,
    heatmapFrames,
  })
  const highAttentionIntervals = visibleAnalysisResult?.visualizations_json.high_attention_intervals ?? []
  const lowAttentionIntervals = visibleAnalysisResult?.visualizations_json.low_attention_intervals ?? []
  const recommendations = visibleAnalysisResult?.recommendations_json ?? []
  const summaryCards = buildSummaryCards(summary)
  const resultState = resolveResultState({
    analysisJob,
    analysisResult,
    analysisPreviewResult,
    uploadState,
  })
  const analysisCompleted = Boolean(analysisResult && (!analysisJob || analysisJob.status === 'completed'))
  const evaluationJobId = analysisResult?.job_id ?? analysisJob?.id ?? null
  const summarySectionMessage = buildScoringPendingMessage(stageAvailability, currentStage)
  const sceneSectionMessage = buildScenePendingMessage(stageAvailability, currentStage)
  const recommendationsSectionMessage = buildRecommendationsPendingMessage(stageAvailability, currentStage)

  return (
    <Stack spacing={3}>
      <Box className="dashboard-grid dashboard-grid--analysis">
        <Stack spacing={3}>
          <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
            <Stack spacing={2.5}>
              <Stack alignItems="center" direction="row" spacing={1}>
                <Chip color="primary" label="Analysis workspace" />
                <HelpTooltip
                  ariaLabel="How analysis works"
                  title="Uploads go directly to object storage. The worker resolves assets from R2-compatible storage and converts model output into charts, segments, heatmaps, and recommendations."
                />
              </Stack>
              <Typography variant="h4">Upload media, define a goal, run analysis.</Typography>
              <Typography color="text.secondary" variant="body2">
                Pick an asset, set the goal, and review the result. Diagnostics and raw payloads stay in the advanced details below.
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                {mediaTypeOptions.map((option) => {
                  const Icon = option.icon
                  const isSelected = option.kind === selectedMediaType
                  return (
                    <Button
                      color="inherit"
                      key={option.kind}
                      onClick={() => handleMediaTypeChange(option.kind)}
                      sx={{
                        borderRadius: 999,
                        border: `1px solid ${isSelected ? option.tone : 'rgba(24, 34, 48, 0.08)'}`,
                        bgcolor: isSelected ? `${option.tone}12` : 'transparent',
                        color: isSelected ? option.tone : 'text.primary',
                        px: 2,
                      }}
                      variant="text"
                    >
                      <Stack alignItems="center" direction="row" spacing={1}>
                        <Icon fontSize="small" />
                        <span>{option.title}</span>
                      </Stack>
                    </Button>
                  )
                })}
              </Stack>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Button onClick={() => openHistoryDrawer('resume')} startIcon={<HistoryRounded />} variant="outlined">
                  Recent analyses
                </Button>
              </Stack>
              <AnalysisFlowOverview
                currentStep={currentFlowStep}
                hasGoalContext={hasGoalContext}
                hasResults={Boolean(analysisResult || analysisJob)}
                hasStoredAsset={uploadState.stage === 'uploaded' || hasLocalDraft}
              />
            </Stack>
          </Paper>

          <Paper className="dashboard-card analysis-upload-card" elevation={0} id="analysis-step-1">
            <Stack spacing={2.5}>
              <Stack direction="row" spacing={1.5}>
                <Box
                  className="analysis-upload-card__icon"
                  sx={{ bgcolor: `${currentMediaOption.tone}1a`, color: currentMediaOption.tone }}
                >
                  <CurrentMediaIcon />
                </Box>
                <Box>
                  <Typography variant="h6">Step 1: {currentMediaOption.title} input</Typography>
                  <Typography color="text.secondary" variant="body2">
                    {currentMediaOption.subtitle}
                  </Typography>
                </Box>
              </Stack>

              {selectedMediaType === 'text' ? (
                <Stack spacing={2}>
                  <TextField
                    minRows={8}
                    multiline
                    onChange={(event) => {
                      setSelectedFile(null)
                      setTextContent(event.target.value)
                      setTextFilename('analysis-notes.txt')
                      setSelectionMode(event.target.value.trim() ? 'asset' : 'auto')
                      setActiveHistoryJobId(null)
                      setComparisonTarget(null)
                      clearGeneratedVariantsState()
                      clearSelectedAnalysisAssetId(selectedAssetStorageKey)
                      clearSelectedAnalysisJobId(selectedJobStorageKey)
                      resetWorkflowState(
                        setUploadState,
                        setAnalysisJob,
                        setAnalysisResult,
                        setAnalysisPreviewResult,
                        setAnalysisProgress,
                        setBannerMessage,
                      )
                    }}
                    placeholder="Paste transcript copy, concept notes, or product narrative here."
                    value={textContent}
                  />
                  <Stack
                    alignItems={{ xs: 'stretch', sm: 'center' }}
                    direction={{ xs: 'column', sm: 'row' }}
                    justifyContent="space-between"
                    spacing={2}
                  >
                    <Typography color="text.secondary" variant="body2">
                      {textContent.length} / {config?.max_text_characters ?? '...'} characters
                    </Typography>
                    <Stack
                      alignItems={{ xs: 'stretch', sm: 'center' }}
                      direction={{ xs: 'column', sm: 'row' }}
                      spacing={1}
                    >
                      <Typography color="text.secondary" variant="body2">
                        Supported: PDF, DOC, DOCX, ODT, RTF, TXT, MD, CSV, JSON, HTML, XML
                      </Typography>
                      <Button component="label" startIcon={<FileUploadRounded />} variant="outlined">
                        Upload document
                        <input
                          accept={buildTextUploadAccept(config ? config.allowed_mime_types.text : [])}
                          hidden
                          onChange={handleTextFileSelection}
                          type="file"
                        />
                      </Button>
                    </Stack>
                  </Stack>
                </Stack>
              ) : (
                <Box
                  className={`analysis-dropzone ${isDragActive ? 'is-active' : ''}`}
                  onDragEnter={(event) => {
                    event.preventDefault()
                    setIsDragActive(true)
                  }}
                  onDragLeave={(event) => {
                    event.preventDefault()
                    setIsDragActive(false)
                  }}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={handleDrop}
                >
                  <Stack alignItems="center" spacing={1.5}>
                    <CloudUploadRounded color="primary" />
                    <Typography variant="h6">Drop a {selectedMediaType} file here</Typography>
                    <Typography color="text.secondary" sx={{ textAlign: 'center' }} variant="body2">
                      Accepted mime types: {(config?.allowed_mime_types[selectedMediaType] || []).join(', ')}
                    </Typography>
                    <Button component="label" startIcon={<FileUploadRounded />} variant="outlined">
                      Choose file
                      <input
                        accept={(config?.allowed_mime_types[selectedMediaType] || []).join(',')}
                        hidden
                        onChange={handleBinaryFileSelection}
                        type="file"
                      />
                    </Button>
                  </Stack>
                </Box>
              )}

              <SelectedSourceSummary
                mediaType={selectedMediaType}
                selectedAsset={uploadState.asset}
                selectedFile={selectedFile}
                textContent={textContent}
                textFilename={textFilename}
              />

              <UploadedMediaLibrary
                activeAssetId={activeLibraryAssetId}
                assets={assetLibrary}
                errorMessage={assetLibraryError}
                hasLoaded={hasLoadedAssetLibrary}
                isLoading={isLoadingAssetLibrary}
                onReload={() => setAssetLibraryRefreshNonce((current) => current + 1)}
                onSelectAsset={handleSelectUploadedAsset}
              />

              {uploadState.stage === 'uploading' ? (
                <Stack spacing={1}>
                  <LinearProgress value={uploadState.progressPercent} variant="determinate" />
                  <Typography color="text.secondary" variant="body2">
                    Uploading directly to object storage: {uploadState.progressPercent}%
                  </Typography>
                </Stack>
              ) : null}

              {uploadState.validationErrors.length > 0 ? (
                <Alert severity="error">
                  {uploadState.validationErrors.map((errorMessage) => (
                    <span key={errorMessage}>{errorMessage}</span>
                  ))}
                </Alert>
              ) : null}

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                <Button
                  disabled={!canUpload}
                  onClick={handleUpload}
                  startIcon={<CloudUploadRounded />}
                  variant="contained"
                >
                  {uploadState.stage === 'uploaded' ? 'Upload replacement' : 'Upload media'}
                </Button>
                <Button
                  disabled={!canStartAnalysis}
                  onClick={handleStartAnalysis}
                  startIcon={<PlayCircleRounded />}
                  variant="outlined"
                >
                  {analysisJob?.status === 'failed' ? 'Retry analysis' : 'Start analysis'}
                </Button>
              </Stack>
            </Stack>
          </Paper>

          <Paper className="dashboard-card" elevation={0} id="analysis-step-2">
            <Stack spacing={2}>
              <Typography variant="h6">Step 2: Set the review goal</Typography>
              <Typography color="text.secondary" variant="body2">
                Structured goal fields make future compare, benchmark, and reporting views much more useful than a
                freeform objective alone.
              </Typography>
              {isLoadingGoalPresets ? <Alert severity="info">Loading goal presets…</Alert> : null}
              {goalPresetsError ? <Alert severity="warning">{goalPresetsError}</Alert> : null}
              {suggestedGoalContext ? (
                <Alert
                  action={
                    <Button onClick={handleApplySuggestedGoalContext} size="small" variant="outlined">
                      Apply suggestion
                    </Button>
                  }
                  severity="info"
                >
                  Recommended for this {selectedMediaType} input: {readableGoalTemplate(suggestedGoalContext.goal_template)} on{' '}
                  {readableChannel(suggestedGoalContext.channel)}. {suggestedGoalContext.rationale}
                </Alert>
              ) : null}
              {groupedGoalTemplates.map((group) => (
                <Stack key={group.id} spacing={1.25}>
                  <Box>
                    <Typography variant="subtitle2">{group.label}</Typography>
                    <Typography color="text.secondary" variant="body2">
                      {group.description}
                    </Typography>
                  </Box>
                  <Box className="analysis-goal-template-grid">
                    {group.templates.map((option) => {
                      const isSelected = goalTemplate === option.value
                      return (
                        <Button
                          color="inherit"
                          key={option.value}
                          onClick={() => {
                            setGoalTemplate((current) => (current === option.value ? '' : option.value))
                            if (option.default_channel && availableChannels.some((channelOption) => channelOption.value === option.default_channel)) {
                              setChannel((current) => current || option.default_channel || '')
                            }
                          }}
                          sx={{
                            alignItems: 'flex-start',
                            justifyContent: 'flex-start',
                            borderRadius: '20px',
                            border: `1px solid ${isSelected ? 'rgba(59, 91, 219, 0.38)' : 'rgba(24, 34, 48, 0.08)'}`,
                            bgcolor: isSelected ? 'rgba(59, 91, 219, 0.08)' : 'rgba(248, 250, 252, 0.7)',
                            px: 2,
                            py: 1.5,
                            textAlign: 'left',
                          }}
                          variant="text"
                        >
                          <Stack spacing={0.75}>
                            <Typography variant="subtitle2">{option.label}</Typography>
                            <Typography color="text.secondary" variant="body2">
                              {option.description}
                            </Typography>
                            {option.default_channel ? (
                              <Chip
                                label={`Default channel: ${readableChannel(option.default_channel)}`}
                                size="small"
                                sx={{ alignSelf: 'flex-start' }}
                                variant="outlined"
                              />
                            ) : null}
                          </Stack>
                        </Button>
                      )
                    })}
                  </Box>
                </Stack>
              ))}
              <Box className="analysis-goal-grid">
                <TextField
                  label="Channel"
                  onChange={(event) => setChannel(event.target.value)}
                  select
                  value={channel}
                >
                  <MenuItem value="">Select a channel</MenuItem>
                  {availableChannels.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="Audience segment"
                  onChange={(event) => setAudienceSegment(event.target.value)}
                  placeholder={
                    suggestedGoalContext?.audience_placeholder ||
                    'Example: Returning customers, first-time founders, Gen Z shoppers'
                  }
                  value={audienceSegment}
                />
              </Box>
              <TextField
                label="Objective"
                minRows={4}
                multiline
                onChange={(event) => setObjective(event.target.value)}
                placeholder="Example: Evaluate whether the opening hook is strong enough for a paid social launch."
                value={objective}
              />
              {goalValidationErrors.length > 0 && uploadState.stage === 'uploaded' ? (
                <Alert severity="warning">
                  {goalValidationErrors.join(' ')}
                </Alert>
              ) : null}
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Chip
                  label={goalTemplate ? readableGoalTemplate(goalTemplate) : 'Template not set'}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  label={channel ? readableChannel(channel) : 'Channel not set'}
                  size="small"
                  variant="outlined"
                />
                <Chip
                  label={audienceSegment.trim() ? audienceSegment.trim() : 'Audience not set'}
                  size="small"
                  variant="outlined"
                />
              </Stack>
            </Stack>
          </Paper>
        </Stack>

        <Stack spacing={3}>
          {bannerMessage ? <Alert severity={bannerMessage.type}>{bannerMessage.message}</Alert> : null}
          {configError ? <Alert severity="error">{configError}</Alert> : null}
          {isLoadingConfig ? <Alert severity="info">Loading analysis upload settings…</Alert> : null}

          <Paper className="dashboard-card" elevation={0}>
            <Stack spacing={2}>
              <Typography variant="h6">Flow status</Typography>
              <Chip
                className={`analysis-status-chip is-${currentStage}`}
                label={readableProgressStage(currentStage)}
                sx={{ alignSelf: 'flex-start' }}
              />
              {visibleProgress?.stageLabel ? (
                <Typography color="text.secondary" variant="body2">
                  {visibleProgress.stageLabel}
                </Typography>
              ) : null}
              {stageRows(currentStage).map((row) => (
                <Box className={`analysis-stage-row ${row.isActive ? 'is-active' : ''}`} key={row.label}>
                  <Typography variant="subtitle2">{row.label}</Typography>
                  <Typography color="text.secondary" variant="body2">
                    {row.detail}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </Paper>

          <Paper className="dashboard-card" elevation={0}>
            <Stack spacing={2}>
              <Typography variant="h6">Current payload</Typography>
              <DetailRow label="Workspace" value={session.organizationName || 'Primary workspace'} />
              <DetailRow label="Project" value={session.defaultProjectName || 'Default Analysis Project'} />
              <DetailRow label="Selected media" value={currentMediaOption.title} />
              <DetailRow
                label="Goal template"
                value={goalTemplate ? readableGoalTemplate(goalTemplate) : 'Not specified'}
              />
              <DetailRow label="Channel" value={channel ? readableChannel(channel) : 'Not specified'} />
              <DetailRow
                label="Audience segment"
                value={audienceSegment.trim() ? audienceSegment.trim() : 'Not specified'}
              />
              <DetailRow label="Objective" value={objective.trim() || 'Not specified'} />
              <DetailRow
                label="Selected asset"
                value={uploadState.asset?.original_filename || uploadState.asset?.object_key || 'No stored asset selected'}
              />
              <DetailRow label="Upload status" value={uploadState.asset?.upload_status || uploadState.stage} />
              <DetailRow
                label="Stored object"
                value={uploadState.asset?.object_key ? uploadState.asset.object_key : 'Not uploaded'}
              />
              <DetailRow
                label="Queued job"
                value={analysisJob ? `${shortenId(analysisJob.id)} (${analysisJob.status})` : 'Not started'}
              />
            </Stack>
          </Paper>

          <RecentAnalysesLauncher
            activeJob={selectedHistoryItem}
            currentFlowStep={currentFlowStep}
            hasLoaded={hasLoadedAnalysisHistory}
            isLoading={isLoadingAnalysisHistory}
            itemCount={analysisHistory.length}
            onJumpToAssetStep={() => scrollToSection('analysis-step-1')}
            onOpenHistory={() => openHistoryDrawer('resume')}
          />

          <Paper className="dashboard-card" elevation={0}>
            <Stack spacing={2}>
              <Typography variant="h6">Storage validation</Typography>
              <Typography color="text.secondary" variant="body2">
                The upload session is only marked ready after the backend confirms the object exists in storage
                and creates a version reference for the async TRIBE worker.
              </Typography>
              <Stack spacing={1.25}>
                <ValidationRow label="Session token" value={sessionToken ? 'Attached' : 'Sign in again'} />
                <ValidationRow
                  label="Max file size"
                  value={config ? formatFileSize(config.max_file_size_bytes) : 'Loading…'}
                />
                <ValidationRow
                  label="Allowed mime types"
                  value={config ? config.allowed_mime_types[selectedMediaType].join(', ') : 'Loading…'}
                />
              </Stack>
            </Stack>
          </Paper>
        </Stack>
      </Box>

      <ResultStateBanner
        analysisJob={analysisJob}
        diagnostics={analysisTransportDiagnostics}
        progressLabel={analysisProgress?.stageLabel ?? null}
        resultState={resultState}
        sessionToken={sessionToken}
        onRerunSuccess={(updatedJob) => {
          setAnalysisJob(updatedJob)
        }}
      />

      <ResultsActionHub
        analysisJob={analysisJob}
        analysisResult={analysisResult}
        compareCandidateCount={completedComparisonCandidates.length}
        generatedVariantCount={generatedVariantsResponse?.items.length ?? 0}
        isGeneratingVariants={isGeneratingVariants}
        onCompare={() => {
          void trackAnalysisClientEvent({
            eventName: 'compare_clicked',
            goalTemplateValue: analysisJob?.goal_template || goalTemplate || null,
            channelValue: analysisJob?.channel || channel || null,
            jobId: analysisJob?.id ?? null,
            metadata: {
              compare_candidate_count: completedComparisonCandidates.length,
              comparison_entry_point: onOpenCompareWorkspace ? 'workspace' : 'quick_compare',
            },
          })
          if (analysisJob?.id && onOpenCompareWorkspace) {
            storeCompareWorkspaceSnapshot(compareWorkspaceStorageKey, {
              selectedJobIds: [analysisJob.id],
              baselineJobId: analysisJob.id,
              activeComparisonId: null,
            })
            onOpenCompareWorkspace()
            return
          }
          openHistoryDrawer('compare')
        }}
        onExport={handleExportCurrentAnalysis}
        onGenerate={handleGenerateVariants}
      />

      {comparisonTarget?.result && analysisResult ? (
        <QuickComparisonCard
          baselineAsset={resultsAsset}
          baselineJob={analysisJob}
          baselineResult={analysisResult}
          comparisonAsset={comparisonTarget.asset ?? null}
          comparisonJob={comparisonTarget.job}
          comparisonResult={comparisonTarget.result}
          onClear={() => setComparisonTarget(null)}
        />
      ) : null}

      <GeneratedVariantsPanel
        asset={resultsAsset}
        errorMessage={generatedVariantsError}
        hasResults={Boolean(analysisResult)}
        isGenerating={isGeneratingVariants}
        isLoading={isLoadingGeneratedVariants}
        items={generatedVariantsResponse?.items ?? []}
        job={analysisJob}
        onCopy={handleCopyGeneratedVariant}
        onDownload={handleDownloadGeneratedVariant}
        onGenerate={handleGenerateVariants}
      />

      <Box className="dashboard-grid dashboard-grid--content">
        <AnalysisTransportDiagnosticsCard
          analysisJob={analysisJob}
          diagnostics={analysisTransportDiagnostics}
          progress={visibleProgress}
        />

        <ExecutiveVerdictCard
          benchmark={benchmarkResponse}
          benchmarkError={benchmarkError}
          executiveVerdict={executiveVerdict}
          executiveVerdictError={executiveVerdictError}
          isLoadingBenchmark={isLoadingBenchmark}
          isLoadingExecutiveVerdict={isLoadingExecutiveVerdict}
          hasResults={Boolean(analysisResult)}
        />
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <BenchmarkPercentilesCard
          benchmark={benchmarkResponse}
          errorMessage={benchmarkError}
          hasResults={Boolean(analysisResult)}
          isLoading={isLoadingBenchmark}
        />

        <CalibrationPanel
          calibration={calibrationResponse}
          errorMessage={calibrationError}
          hasResults={Boolean(analysisResult)}
          isImporting={isImportingOutcomes}
          isLoading={isLoadingCalibration}
          onImportCsv={handleImportOutcomeFile}
        />
      </Box>

      <Suspense fallback={<DeferredPanelFallback title="Review ops" />}>
        <CollaborationPanel
          allowTimestampComments
          entityId={analysisJob?.id ?? null}
          entityType="analysis_job"
          session={session}
          subtitle="Keep review status, assignee handoff, and timestamp comments attached to this analysis run."
          title="Review ops"
        />
      </Suspense>

      <Box className="dashboard-grid dashboard-grid--metrics analysis-summary-grid">
        {summaryCards.map((card) => (
          <Paper className="dashboard-card dashboard-card--metric" elevation={0} key={card.key}>
            <Stack spacing={1.5}>
              <Typography color="text.secondary" variant="overline">
                {card.label}
              </Typography>
              <ScoreGauge isReady={stageAvailability.primaryScoringReady} label="" size={80} value={card.value} />
              <Typography color="text.secondary" variant="body2">
                {stageAvailability.primaryScoringReady ? card.helper : summarySectionMessage}
              </Typography>
            </Stack>
          </Paper>
        ))}
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <MetricsRadarCard
          description="A radial view of the same dashboard metrics shown in the table, scaled per metric for faster pattern scanning."
          series={[
            {
              label: 'Current result',
              metrics: metricsRows,
            },
          ]}
          testId="analysis-metrics-radar"
          title="Metrics radar"
        />

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={1.5}>
            <Typography variant="h6">Metrics overview</Typography>
            <Stack spacing={1}>
              {stageAvailability.primaryScoringReady
                ? metricsRows.map((metric) => (
                    <Box
                      key={metric.key}
                      sx={{
                        border: '1px solid rgba(148, 163, 184, 0.18)',
                        borderRadius: 3,
                        px: 1.5,
                        py: 1.25,
                      }}
                    >
                      <Stack alignItems="flex-start" direction="row" justifyContent="space-between" spacing={1.5}>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography sx={{ lineHeight: 1.25 }} variant="subtitle2">
                            {metric.label}
                          </Typography>
                          <Typography color="text.secondary" sx={{ lineHeight: 1.4, mt: 0.35 }} variant="caption">
                            {metric.detail || 'Derived dashboard metric'}
                          </Typography>
                        </Box>
                        <Typography sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} variant="subtitle2">
                          {metric.value.toFixed(metric.unit === 'seconds' ? 2 : 1)} {metric.unit}
                        </Typography>
                      </Stack>

                      <Stack
                        direction="row"
                        flexWrap="wrap"
                        spacing={0.75}
                        sx={{ columnGap: 0.75, mt: 1 }}
                        useFlexGap
                      >
                        <Chip
                          label={`Confidence ${formatOptionalScore(metric.confidence)}`}
                          size="small"
                          variant="outlined"
                        />
                        <Chip label={metric.source} size="small" variant="outlined" />
                      </Stack>
                    </Box>
                  ))
                : Array.from({ length: 5 }).map((_, index) => (
                    <Box
                      key={`metric-skeleton-${index}`}
                      sx={{
                        border: '1px solid rgba(148, 163, 184, 0.18)',
                        borderRadius: 3,
                        px: 1.5,
                        py: 1.25,
                      }}
                    >
                      <Skeleton height={20} sx={{ transform: 'none' }} width="48%" />
                      <Skeleton height={18} sx={{ mt: 0.5, transform: 'none' }} width="90%" />
                      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                        <Skeleton height={28} sx={{ transform: 'none' }} width={110} />
                        <Skeleton height={28} sx={{ transform: 'none' }} width={86} />
                      </Stack>
                    </Box>
                  ))}
            </Stack>
            {!stageAvailability.primaryScoringReady ? (
              <Typography color="text.secondary" variant="body2">
                {summarySectionMessage}
              </Typography>
            ) : null}
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Timeline chart</Typography>
            <Typography color="text.secondary" variant="body2">
              Attention, engagement, and memory proxies aligned to processed timestamps.
            </Typography>
            {stageAvailability.primaryScoringReady ? (
              <TimelineChart
                points={timelinePoints}
                highAttentionIntervals={highAttentionIntervals}
                lowAttentionIntervals={lowAttentionIntervals}
              />
            ) : (
              <TimelineChartSkeleton label={summarySectionMessage} />
            )}
          </Stack>
        </Paper>
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Scene / segment table</Typography>
            <SegmentHeatstrip
              segments={segmentsRows}
              isReady={stageAvailability.sceneStructureReady && stageAvailability.primaryScoringReady}
            />
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Scene</TableCell>
                  <TableCell>Window</TableCell>
                  <TableCell align="right">Attention</TableCell>
                  <TableCell align="right">Delta</TableCell>
                  <TableCell>Note</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {stageAvailability.sceneStructureReady
                  ? segmentsRows.map((segment) => (
                      <TableRow key={`${segment.label}-${segment.start_time_ms}`}>
                        <TableCell>{segment.label}</TableCell>
                        <TableCell>
                          {formatDuration(segment.start_time_ms)} - {formatDuration(segment.end_time_ms)}
                        </TableCell>
                        <TableCell align="right">
                          {stageAvailability.primaryScoringReady ? (
                            Math.round(segment.attention_score)
                          ) : (
                            <Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={44} />
                          )}
                        </TableCell>
                        <TableCell align="right">
                          {stageAvailability.primaryScoringReady ? (
                            formatSignedValue(segment.engagement_delta)
                          ) : (
                            <Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={58} />
                          )}
                        </TableCell>
                        <TableCell>{segment.note || sceneSectionMessage}</TableCell>
                      </TableRow>
                    ))
                  : Array.from({ length: 4 }).map((_, index) => (
                      <TableRow key={`segment-skeleton-${index}`}>
                        <TableCell><Skeleton height={22} sx={{ transform: 'none' }} width="64%" /></TableCell>
                        <TableCell><Skeleton height={22} sx={{ transform: 'none' }} width="78%" /></TableCell>
                        <TableCell align="right"><Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={44} /></TableCell>
                        <TableCell align="right"><Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={58} /></TableCell>
                        <TableCell><Skeleton height={22} sx={{ transform: 'none' }} width="90%" /></TableCell>
                      </TableRow>
                    ))}
              </TableBody>
            </Table>
            {!stageAvailability.sceneStructureReady ? (
              <Typography color="text.secondary" variant="body2">
                {sceneSectionMessage}
              </Typography>
            ) : null}
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Multi-signal scene matrix</Typography>
            <Typography color="text.secondary" variant="body2">
              Per-scene breakdown across all 10 neural &amp; behavioural signals. Cognitive Load is shown inverted (green = low load).
            </Typography>
            <SignalMatrixCard
              segments={segmentsRows}
              isReady={stageAvailability.sceneStructureReady && stageAvailability.primaryScoringReady}
            />
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Attention heatmap overlays</Typography>
            <Typography color="text.secondary" variant="body2">
              Brain plots are intentionally replaced with grid-based timestamp overlays derived from the processed timeline.
            </Typography>
            <HeatmapFramesCard
              frames={heatmapFrames}
              isSceneReady={stageAvailability.sceneStructureReady}
              isScoringReady={stageAvailability.primaryScoringReady}
              loadingLabel={sceneSectionMessage}
            />
          </Stack>
        </Paper>
      </Box>

      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Typography variant="h6">Frame-by-frame breakdown</Typography>
          <Typography color="text.secondary" variant="body2">
            Extracted frames at each analysis timestamp with attention zone and scene data.
          </Typography>
          <VideoFrameStrip
            frames={frameBreakdownItems}
            hasResults={stageAvailability.sceneStructureReady}
            isScoringReady={stageAvailability.primaryScoringReady}
            asset={resultsAsset}
            sessionToken={sessionToken || null}
          />
        </Stack>
      </Paper>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">High and low attention intervals</Typography>
            <AttentionIntervalsCard
              hasResults={stageAvailability.primaryScoringReady}
              highAttentionIntervals={highAttentionIntervals}
              lowAttentionIntervals={lowAttentionIntervals}
              loadingLabel={summarySectionMessage}
            />
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Recommendations</Typography>
            <RecommendationsCard
              hasResults={Boolean(analysisResult)}
              isPartial={!analysisResult && Boolean(analysisPreviewResult)}
              isReady={stageAvailability.recommendationsReady}
              loadingLabel={recommendationsSectionMessage}
              recommendations={recommendations}
              summary={summary}
            />
          </Stack>
        </Paper>
      </Box>

      <Suspense fallback={<DeferredPanelFallback title="LLM evaluations" />}>
        <AnalysisEvaluationSection
          analysisCompleted={analysisCompleted}
          jobId={evaluationJobId}
          onProgressSnapshot={handleEvaluationProgressSnapshot}
          sessionToken={sessionToken || null}
        />
      </Suspense>

      <Drawer
        PaperProps={{
          className: 'analysis-history-drawer',
        }}
        anchor="right"
        onClose={() => setIsHistoryDrawerOpen(false)}
        open={isHistoryDrawerOpen}
      >
        <RecentAnalysesPanel
          activeJobId={activeHistoryJobId}
          drawerMode={historyDrawerMode}
          errorMessage={analysisHistoryError}
          hasLoaded={hasLoadedAnalysisHistory}
          isLoading={isLoadingAnalysisHistory}
          items={analysisHistory}
          loadingJobId={historyDrawerMode === 'compare' ? comparisonLoadingJobId : loadingHistoryJobId}
          onClose={() => setIsHistoryDrawerOpen(false)}
          onJumpToAssetStep={() => {
            setIsHistoryDrawerOpen(false)
            scrollToSection('analysis-step-1')
          }}
          onReload={() => setAnalysisHistoryRefreshNonce((current) => current + 1)}
          onSelectCompareTarget={handleSelectComparisonTarget}
          onSelectJob={handleSelectAnalysisHistoryItem}
        />
      </Drawer>
    </Stack>
  )
}

function SelectedSourceSummary({
  mediaType,
  selectedAsset,
  selectedFile,
  textContent,
  textFilename,
}: {
  mediaType: MediaType
  selectedAsset?: AnalysisAsset
  selectedFile: File | null
  textContent: string
  textFilename: string
}) {
  if (selectedAsset && mediaType === selectedAsset.media_type && !selectedFile && !textContent.trim()) {
    return (
      <Box className="analysis-upload-card__file">
        <Box>
          <Typography variant="subtitle2">{selectedAsset.original_filename || 'Stored analysis asset'}</Typography>
          <Typography color="text.secondary" variant="body2">
            Ready from uploaded media library
            {selectedAsset.size_bytes ? ` · ${formatFileSize(selectedAsset.size_bytes)}` : ''}
          </Typography>
        </Box>
        <Chip color="success" label="Uploaded asset" size="small" variant="outlined" />
      </Box>
    )
  }

  if (mediaType === 'text') {
    return (
      <Box className="analysis-upload-card__file">
        <Box>
          <Typography variant="subtitle2">{selectedFile?.name || textFilename}</Typography>
          <Typography color="text.secondary" variant="body2">
            {selectedFile
              ? `${formatFileSize(selectedFile.size)} ready for upload`
              : textContent.trim()
                ? `${textContent.length} characters prepared for upload`
                : 'Paste text or choose a document to continue.'}
          </Typography>
        </Box>
        <Chip label={selectedFile?.type || 'Text'} size="small" variant="outlined" />
      </Box>
    )
  }

  return (
    <Box className="analysis-upload-card__file">
      <Box>
        <Typography variant="subtitle2">{selectedFile?.name || 'No file selected yet.'}</Typography>
        <Typography color="text.secondary" variant="body2">
          {selectedFile ? formatFileSize(selectedFile.size) : 'Pick or drop a file to continue.'}
        </Typography>
      </Box>
      <Chip label={selectedFile?.type || mediaType.toUpperCase()} size="small" variant="outlined" />
    </Box>
  )
}

function DeferredPanelFallback({ title }: { title: string }) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Typography variant="h6">{title}</Typography>
        <LinearProgress sx={{ borderRadius: 999, height: 8 }} />
        <Typography color="text.secondary" variant="body2">
          Loading this section on demand to keep the primary analysis view responsive.
        </Typography>
      </Stack>
    </Paper>
  )
}

function UploadedMediaLibrary({
  activeAssetId,
  assets,
  errorMessage,
  hasLoaded,
  isLoading,
  onReload,
  onSelectAsset,
}: {
  activeAssetId: string | null
  assets: AnalysisAsset[]
  errorMessage: string | null
  hasLoaded: boolean
  isLoading: boolean
  onReload: () => void
  onSelectAsset: (asset: AnalysisAsset) => void
}) {
  return (
    <Stack spacing={1.5}>
      <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
        <Box>
          <Typography variant="subtitle2">Uploaded media</Typography>
          <Typography color="text.secondary" variant="body2">
            `Choose file` can only browse your local device. Reuse anything already stored in Cloudflare R2 from this list.
          </Typography>
        </Box>
        <Button onClick={onReload} size="small" variant="text">
          Refresh list
        </Button>
      </Stack>

      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

      {isLoading && assets.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            Loading uploaded assets…
          </Typography>
        </Box>
      ) : null}

      {!isLoading && hasLoaded && assets.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            No uploaded media is available for this input type yet.
          </Typography>
        </Box>
      ) : null}

      {assets.length > 0 ? (
        <Box className="analysis-asset-library">
          {assets.map((asset) => {
            const isSelected = asset.id === activeAssetId
            const isReady = asset.upload_status === 'uploaded'
            return (
              <Box className={`analysis-asset-library__item ${isSelected ? 'is-selected' : ''}`} key={asset.id}>
                <Stack
                  alignItems={{ xs: 'stretch', md: 'center' }}
                  direction={{ xs: 'column', md: 'row' }}
                  justifyContent="space-between"
                  spacing={1.5}
                >
                  <Box sx={{ minWidth: 0 }}>
                    <Typography sx={{ wordBreak: 'break-word' }} variant="subtitle2">
                      {asset.original_filename || asset.object_key}
                    </Typography>
                    <Typography color="text.secondary" sx={{ wordBreak: 'break-word' }} variant="body2">
                      {formatFileSize(asset.size_bytes || 0)} · uploaded {formatTimestamp(asset.created_at)}
                    </Typography>
                    <Typography color="text.secondary" sx={{ wordBreak: 'break-word' }} variant="caption">
                      {asset.object_key}
                    </Typography>
                  </Box>
                  <Stack alignItems={{ xs: 'stretch', md: 'center' }} direction={{ xs: 'column', md: 'row' }} spacing={1}>
                    <Button
                      disabled={!isReady}
                      onClick={() => onSelectAsset(asset)}
                      size="small"
                      variant={isSelected ? 'contained' : 'outlined'}
                    >
                      {isSelected ? 'Selected' : 'Use asset'}
                    </Button>
                  </Stack>
                </Stack>
              </Box>
            )
          })}
        </Box>
      ) : null}
    </Stack>
  )
}

function RecentAnalysesLauncher({
  activeJob,
  currentFlowStep,
  hasLoaded,
  isLoading,
  itemCount,
  onJumpToAssetStep,
  onOpenHistory,
}: {
  activeJob: AnalysisJobListItem | null
  currentFlowStep: AnalysisFlowStepId
  hasLoaded: boolean
  isLoading: boolean
  itemCount: number
  onJumpToAssetStep: () => void
  onOpenHistory: () => void
}) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">Recent analyses</Typography>
            <Typography color="text.secondary" variant="body2">
              Stored runs are available from a secondary panel so setup stays focused on the current review.
            </Typography>
          </Box>
          <Button data-testid="open-analysis-history" onClick={onOpenHistory} size="small" startIcon={<HistoryRounded />} variant="outlined">
            Open
          </Button>
        </Stack>

        {isLoading && itemCount === 0 ? (
          <Box className="analysis-empty-state">
            <Typography color="text.secondary" variant="body2">
              Loading recent analyses…
            </Typography>
          </Box>
        ) : null}

        {!isLoading && hasLoaded && itemCount === 0 ? (
          <Box className="analysis-empty-state">
            <Stack spacing={1.5}>
              <Typography color="text.secondary" variant="body2">
                No saved runs are available for this media type yet. Start at Step 1, upload or select media, then queue the first analysis.
              </Typography>
              <Button onClick={onJumpToAssetStep} size="small" variant="contained">
                Go to Step 1
              </Button>
            </Stack>
          </Box>
        ) : null}

        {itemCount > 0 && activeJob ? (
          <Box className="analysis-inline-summary">
            <Typography variant="subtitle2">
              {activeJob.asset?.original_filename || activeJob.asset?.object_key || `Analysis ${shortenId(activeJob.job.id)}`}
            </Typography>
            <Typography color="text.secondary" variant="body2">
              {formatTimestamp(activeJob.job.created_at)}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip className={`analysis-status-chip is-${activeJob.job.status}`} label={activeJob.job.status} size="small" variant="outlined" />
              <Chip
                color={activeJob.has_result ? 'success' : 'default'}
                label={activeJob.has_result ? 'Results ready' : 'In progress'}
                size="small"
                variant="outlined"
              />
            </Stack>
          </Box>
        ) : null}

        {itemCount > 0 && !activeJob ? (
          <Box className="analysis-empty-state">
            <Typography color="text.secondary" variant="body2">
              {currentFlowStep === 'results'
                ? 'Open the recent analyses panel to resume a previous run or compare it against the current result.'
                : 'Open the recent analyses panel any time you want to resume an earlier run without interrupting setup.'}
            </Typography>
          </Box>
        ) : null}
      </Stack>
    </Paper>
  )
}

function RecentAnalysesPanel({
  activeJobId,
  drawerMode,
  errorMessage,
  hasLoaded,
  isLoading,
  items,
  loadingJobId,
  onClose,
  onJumpToAssetStep,
  onReload,
  onSelectCompareTarget,
  onSelectJob,
}: {
  activeJobId: string | null
  drawerMode: HistoryDrawerMode
  errorMessage: string | null
  hasLoaded: boolean
  isLoading: boolean
  items: AnalysisJobListItem[]
  loadingJobId: string | null
  onClose: () => void
  onJumpToAssetStep: () => void
  onReload: () => void
  onSelectCompareTarget: (item: AnalysisJobListItem) => void
  onSelectJob: (item: AnalysisJobListItem) => void
}) {
  const isCompareMode = drawerMode === 'compare'

  return (
    <Stack className="analysis-history-drawer__content" spacing={2.5}>
      <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
        <Box>
          <Typography variant="h6">{isCompareMode ? 'Choose a comparison target' : 'Recent analyses'}</Typography>
          <Typography color="text.secondary" variant="body2">
            {isCompareMode
              ? 'Pick another completed run to create a quick side-by-side comparison without leaving the analysis workspace.'
              : 'Open a completed or in-flight run from a secondary panel so the main page stays focused on the current workflow.'}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button onClick={onReload} size="small" variant="text">
            Refresh list
          </Button>
          <Button onClick={onClose} size="small" variant="outlined">
            Close
          </Button>
        </Stack>
      </Stack>

      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

      {isLoading && items.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            Loading recent analyses…
          </Typography>
        </Box>
      ) : null}

      {!isLoading && hasLoaded && items.length === 0 ? (
        <Box className="analysis-empty-state">
          <Stack spacing={1.5}>
            <Typography color="text.secondary" variant="body2">
              No analysis jobs have been created for this media type yet. Upload or reuse media first, then start an analysis run.
            </Typography>
            <Button onClick={onJumpToAssetStep} size="small" variant="contained">
              Go to Step 1
            </Button>
          </Stack>
        </Box>
      ) : null}

      {items.length > 0 ? (
        <Box className="analysis-job-history" data-testid="analysis-history-list">
          {items.map((item) => {
            const isSelected = item.job.id === activeJobId
            const isLoadingSelection = item.job.id === loadingJobId
            const primaryLabel =
              item.asset?.original_filename || item.asset?.object_key || `Analysis ${shortenId(item.job.id)}`

            return (
              <ButtonBase
                className={`analysis-job-history__item ${isSelected ? 'is-selected' : ''}`}
                data-testid={`analysis-history-item-${item.job.id}`}
                key={item.job.id}
                onClick={() => {
                  if (isCompareMode && !item.has_result) {
                    return
                  }
                  if (isCompareMode) {
                    onSelectCompareTarget(item)
                    return
                  }
                  onSelectJob(item)
                }}
                sx={{ borderRadius: '20px', width: '100%', textAlign: 'left' }}
              >
                <Box sx={{ width: '100%' }}>
                  <Stack spacing={1.25}>
                    <Stack alignItems="flex-start" direction="row" justifyContent="space-between" spacing={1.5}>
                      <Box sx={{ minWidth: 0 }}>
                        <Typography sx={{ wordBreak: 'break-word' }} variant="subtitle2">
                          {primaryLabel}
                        </Typography>
                        <Typography color="text.secondary" sx={{ wordBreak: 'break-word' }} variant="body2">
                          {formatTimestamp(item.job.created_at)}
                        </Typography>
                      </Box>
                      <Chip
                        className={`analysis-status-chip is-${item.job.status}`}
                        label={isLoadingSelection ? 'loading' : item.job.status}
                        size="small"
                        variant="outlined"
                      />
                    </Stack>

                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip
                        color={item.has_result ? 'success' : item.job.status === 'failed' ? 'error' : 'default'}
                        label={item.has_result ? 'Results ready' : item.job.status === 'failed' ? 'Failed' : 'No result yet'}
                        size="small"
                        variant="outlined"
                      />
                      <Chip label={item.asset?.media_type || 'analysis'} size="small" variant="outlined" />
                      {isCompareMode ? (
                        <Chip
                          color={item.has_result ? 'primary' : 'default'}
                          label={item.has_result ? 'Compare' : 'Unavailable'}
                          size="small"
                          variant="outlined"
                        />
                      ) : null}
                    </Stack>

                    <Typography color="text.secondary" variant="body2">
                      {truncateText(item.job.objective || 'No analysis objective was stored for this run.', 132)}
                    </Typography>
                  </Stack>
                </Box>
              </ButtonBase>
            )
          })}
        </Box>
      ) : null}
    </Stack>
  )
}

function ResultsActionHub({
  analysisJob,
  analysisResult,
  compareCandidateCount,
  generatedVariantCount,
  isGeneratingVariants,
  onCompare,
  onExport,
  onGenerate,
}: {
  analysisJob: AnalysisJob | null
  analysisResult: AnalysisResult | null
  compareCandidateCount: number
  generatedVariantCount: number
  isGeneratingVariants: boolean
  onCompare: () => void
  onExport: () => void
  onGenerate: () => void
}) {
  const hasResults = Boolean(analysisJob && analysisResult)

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack spacing={0.5}>
          <Typography variant="h6">Step 3: Review and act</Typography>
          <Typography color="text.secondary" variant="body2">
            Once a run is loaded, the fastest next moves are compare, export, and turn the strongest recommendations into action-ready variants.
          </Typography>
        </Stack>
        <Box className="analysis-action-grid">
          <ActionCard
            ctaLabel="Compare run"
            description={
              compareCandidateCount > 0
                ? `${compareCandidateCount} saved run${compareCandidateCount === 1 ? '' : 's'} ready for quick comparison.`
                : 'Compare is most useful after you have at least one additional completed run.'
            }
            disabled={!hasResults || compareCandidateCount === 0}
            icon={<CompareArrowsRounded fontSize="small" />}
            label="Compare"
            onClick={onCompare}
            testId="analysis-action-compare"
          />
          <ActionCard
            ctaLabel="Export JSON"
            description="Download the active job, asset, and dashboard payload as a portable report package."
            disabled={!hasResults}
            icon={<DownloadRounded fontSize="small" />}
            label="Export"
            onClick={onExport}
            testId="analysis-action-export"
          />
          <ActionCard
            ctaLabel={
              isGeneratingVariants
                ? 'Generating…'
                : generatedVariantCount > 0
                  ? 'Regenerate variants'
                  : 'Generate variants'
            }
            description={
              generatedVariantCount > 0
                ? `${generatedVariantCount} saved variant${generatedVariantCount === 1 ? '' : 's'} ready for projected compare against the original.`
                : 'Turn the strongest recommendations into hook, CTA, script, and thumbnail variants.'
            }
            disabled={!hasResults || isGeneratingVariants}
            icon={<AutoAwesomeRounded fontSize="small" />}
            label="Generate"
            onClick={onGenerate}
            testId="analysis-action-generate"
          />
        </Box>
      </Stack>
    </Paper>
  )
}

function ActionCard({
  ctaLabel,
  description,
  disabled,
  icon,
  label,
  onClick,
  testId,
}: {
  ctaLabel: string
  description: string
  disabled: boolean
  icon: ReactElement
  label: string
  onClick: () => void
  testId: string
}) {
  return (
    <Box className={`analysis-action-card ${disabled ? 'is-disabled' : ''}`}>
      <Stack spacing={1.5}>
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5}>
          <Chip icon={icon} label={label} size="small" variant="outlined" />
        </Stack>
        <Typography color="text.secondary" variant="body2">
          {description}
        </Typography>
        <Button data-testid={testId} disabled={disabled} onClick={onClick} variant="contained">
          {ctaLabel}
        </Button>
      </Stack>
    </Box>
  )
}

function QuickComparisonCard({
  baselineAsset,
  baselineJob,
  baselineResult,
  comparisonAsset,
  comparisonJob,
  comparisonResult,
  onClear,
}: {
  baselineAsset: AnalysisAsset | null
  baselineJob: AnalysisJob | null
  baselineResult: AnalysisResult
  comparisonAsset: AnalysisAsset | null
  comparisonJob: AnalysisJob
  comparisonResult: AnalysisResult
  onClear: () => void
}) {
  const comparisonRows = buildQuickComparisonRows(baselineResult, comparisonResult)
  const winner = comparisonRows.reduce(
    (current, row) => {
      if (row.baselineValue > row.comparisonValue) {
        return { baseline: current.baseline + 1, comparison: current.comparison }
      }
      if (row.comparisonValue > row.baselineValue) {
        return { baseline: current.baseline, comparison: current.comparison + 1 }
      }
      return current
    },
    { baseline: 0, comparison: 0 },
  )
  const winnerLabel =
    winner.baseline === winner.comparison
      ? 'The two runs are effectively tied on the primary dashboard metrics.'
      : winner.baseline > winner.comparison
        ? `${baselineAsset?.original_filename || shortenId(baselineJob?.id || 'baseline')} currently leads the quick compare snapshot.`
        : `${comparisonAsset?.original_filename || shortenId(comparisonJob.id)} currently leads the quick compare snapshot.`

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">Quick comparison</Typography>
            <Typography color="text.secondary" variant="body2">
              Use this as a fast call before the dedicated compare workspace lands.
            </Typography>
          </Box>
          <Button onClick={onClear} size="small" variant="outlined">
            Clear comparison
          </Button>
        </Stack>
        <Alert severity="info">{winnerLabel}</Alert>
        <Box className="analysis-compare-grid">
          <CompareSummaryColumn
            title={baselineAsset?.original_filename || `Current run ${shortenId(baselineJob?.id || 'current')}`}
            subtitle={baselineJob?.objective || 'Current analysis'}
          />
          <CompareSummaryColumn
            title={comparisonAsset?.original_filename || `Comparison ${shortenId(comparisonJob.id)}`}
            subtitle={comparisonJob.objective || 'Comparison analysis'}
          />
        </Box>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Metric</TableCell>
              <TableCell align="right">Current</TableCell>
              <TableCell align="right">Compare</TableCell>
              <TableCell align="right">Delta</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {comparisonRows.map((row) => (
              <TableRow key={row.label}>
                <TableCell>{row.label}</TableCell>
                <TableCell align="right">{row.baselineValue.toFixed(1)}</TableCell>
                <TableCell align="right">{row.comparisonValue.toFixed(1)}</TableCell>
                <TableCell align="right">{formatSignedValue(row.baselineValue - row.comparisonValue)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Stack>
    </Paper>
  )
}

function CompareSummaryColumn({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <Box className="analysis-inline-summary">
      <Typography variant="subtitle2">{title}</Typography>
      <Typography color="text.secondary" variant="body2">
        {truncateText(subtitle, 120)}
      </Typography>
    </Box>
  )
}

function GeneratedVariantsPanel({
  asset,
  errorMessage,
  hasResults,
  isGenerating,
  isLoading,
  items,
  job,
  onCopy,
  onDownload,
  onGenerate,
}: {
  asset: AnalysisAsset | null
  errorMessage: string | null
  hasResults: boolean
  isGenerating: boolean
  isLoading: boolean
  items: AnalysisGeneratedVariant[]
  job: AnalysisJob | null
  onCopy: (variant: AnalysisGeneratedVariant) => void
  onDownload: (variant: AnalysisGeneratedVariant) => void
  onGenerate: () => void
}) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">Generated variants</Typography>
            <Typography color="text.secondary" variant="body2">
              Turn the current recommendations into concrete rewrites, then compare each projected variant against the original analysis.
            </Typography>
          </Box>
          <Button disabled={!hasResults || isGenerating} onClick={onGenerate} size="small" variant="contained">
            {isGenerating ? 'Generating…' : items.length > 0 ? 'Regenerate variants' : 'Generate variants'}
          </Button>
        </Stack>

        {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

        {isLoading ? (
          <Alert severity="info">Loading saved generated variants…</Alert>
        ) : null}

        {!hasResults ? (
          <Box className="analysis-empty-state">
            <Typography color="text.secondary" variant="body2">
              Complete an analysis run first, then generate action-ready hook, CTA, script, and thumbnail variants.
            </Typography>
          </Box>
        ) : null}

        {hasResults && !isLoading && items.length === 0 ? (
          <Box className="analysis-empty-state">
            <Stack spacing={1.5}>
              <Typography color="text.secondary" variant="body2">
                No generated variants are stored for this run yet. Generate them once and they will stay attached to this analysis job.
              </Typography>
              <Button disabled={isGenerating} onClick={onGenerate} size="small" variant="outlined">
                Generate variants
              </Button>
            </Stack>
          </Box>
        ) : null}

        {items.length > 0 ? (
          <Stack spacing={2}>
            {items.map((variant) => (
              <Box
                key={variant.id}
                sx={{
                  border: '1px solid rgba(24, 34, 48, 0.08)',
                  borderRadius: '20px',
                  p: 2,
                  bgcolor: 'rgba(248, 250, 252, 0.72)',
                }}
              >
                <Stack spacing={2}>
                  <Stack
                    alignItems={{ xs: 'stretch', md: 'center' }}
                    direction={{ xs: 'column', md: 'row' }}
                    justifyContent="space-between"
                    spacing={1.5}
                  >
                    <Box>
                      <Typography variant="subtitle1">{variant.title}</Typography>
                      <Typography color="text.secondary" variant="body2">
                        {variant.summary}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip label={readableGeneratedVariantType(variant.variant_type)} size="small" variant="outlined" />
                      {variant.source_suggestion_title ? (
                        <Chip label={truncateText(variant.source_suggestion_title, 42)} size="small" variant="outlined" />
                      ) : null}
                      <Button onClick={() => onCopy(variant)} size="small" variant="text">
                        Copy
                      </Button>
                      <Button onClick={() => onDownload(variant)} size="small" variant="outlined">
                        Download
                      </Button>
                    </Stack>
                  </Stack>

                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    {variant.focus_recommendations.map((recommendation) => (
                      <Chip key={`${variant.id}-${recommendation}`} label={truncateText(recommendation, 48)} size="small" variant="outlined" />
                    ))}
                  </Stack>

                  <Box
                    sx={{
                      display: 'grid',
                      gap: 1.25,
                      gridTemplateColumns: {
                        xs: '1fr',
                        md: 'repeat(2, minmax(0, 1fr))',
                      },
                    }}
                  >
                    {variant.sections.map((section) => (
                      <Box
                        key={section.key}
                        sx={{
                          border: '1px solid rgba(24, 34, 48, 0.08)',
                          borderRadius: '16px',
                          p: 1.5,
                          bgcolor: '#fff',
                        }}
                      >
                        <Typography variant="subtitle2">{section.label}</Typography>
                        <Typography color="text.secondary" sx={{ whiteSpace: 'pre-line' }} variant="body2">
                          {section.value}
                        </Typography>
                      </Box>
                    ))}
                  </Box>

                  <Alert severity="info">
                    Compare generated variant vs original: {variant.compare_summary}
                  </Alert>

                  <Box className="analysis-compare-grid">
                    <CompareSummaryColumn
                      title={asset?.original_filename || `Original ${job ? shortenId(job.id) : 'analysis'}`}
                      subtitle={job?.objective || 'Current analysis'}
                    />
                    <CompareSummaryColumn
                      title={variant.title}
                      subtitle="Projected generated variant"
                    />
                  </Box>

                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Metric</TableCell>
                        <TableCell align="right">Original</TableCell>
                        <TableCell align="right">Variant</TableCell>
                        <TableCell align="right">Delta</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {variant.compare_metrics.map((metric) => (
                        <TableRow key={`${variant.id}-${metric.key}`}>
                          <TableCell>{metric.label}</TableCell>
                          <TableCell align="right">{metric.original_value.toFixed(1)}</TableCell>
                          <TableCell align="right">{metric.variant_value.toFixed(1)}</TableCell>
                          <TableCell align="right">{formatSignedValue(metric.delta)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Stack>
              </Box>
            ))}
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  )
}

function AnalysisTransportDiagnosticsCard({
  analysisJob,
  diagnostics,
  progress,
}: {
  analysisJob: AnalysisJob | null
  diagnostics: AnalysisTransportDiagnostics
  progress: AnalysisProgressState | null
}) {
  const queueWaitMs = progress?.diagnostics?.queueWaitMs ?? calculateElapsedMs(analysisJob?.created_at ?? null, analysisJob?.started_at ?? null)
  const processingDurationMs =
    progress?.diagnostics?.processingDurationMs ?? calculateElapsedMs(analysisJob?.started_at ?? null, analysisJob?.finished_at ?? null)
  const resultDeliveryMs =
    progress?.diagnostics?.resultDeliveryMs ?? calculateElapsedMs(analysisJob?.created_at ?? null, analysisJob?.finished_at ?? null)

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">Delivery diagnostics</Typography>
            <Typography color="text.secondary" variant="body2">
              Transport mode, heartbeat health, and timing markers for the active analysis job.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip
              color={diagnostics.mode === 'stream' ? 'primary' : 'warning'}
              label={diagnostics.mode === 'stream' ? 'Live stream' : 'Polling fallback'}
              size="small"
              variant="outlined"
            />
            <Chip label={analysisJob?.status || 'idle'} size="small" variant="outlined" />
          </Stack>
        </Stack>
        <Stack spacing={1.1}>
          <DetailRow label="Current stage" value={readableProgressStage(progress?.stage ?? analysisJob?.status)} />
          <DetailRow label="Stream connected" value={diagnostics.isConnected ? 'Yes' : 'No'} />
          <DetailRow label="Reconnect count" value={String(diagnostics.reconnectCount)} />
          <DetailRow
            label="Last connection"
            value={diagnostics.lastConnectedAt ? formatTimestamp(diagnostics.lastConnectedAt) : 'Not connected yet'}
          />
          <DetailRow
            label="Last heartbeat"
            value={diagnostics.lastHeartbeatAt ? formatTimestamp(diagnostics.lastHeartbeatAt) : 'Waiting for heartbeat'}
          />
          <DetailRow
            label="Queue wait"
            value={queueWaitMs != null ? `${queueWaitMs} ms` : 'Pending'}
          />
          <DetailRow
            label="Processing time"
            value={processingDurationMs != null ? `${processingDurationMs} ms` : 'Pending'}
          />
          <DetailRow
            label="First result"
            value={
              progress?.diagnostics?.timeToFirstResultMs != null
                ? `${progress.diagnostics.timeToFirstResultMs} ms`
                : 'Pending'
            }
          />
          <DetailRow
            label="Delivery time"
            value={
              resultDeliveryMs != null
                ? `${resultDeliveryMs} ms`
                : 'Pending'
            }
          />
        </Stack>
        {diagnostics.lastError ? <Alert severity="warning">{diagnostics.lastError}</Alert> : null}
      </Stack>
    </Paper>
  )
}

function ExecutiveVerdictCard({
  benchmark,
  benchmarkError,
  executiveVerdict,
  executiveVerdictError,
  isLoadingBenchmark,
  isLoadingExecutiveVerdict,
  hasResults,
}: {
  benchmark: AnalysisBenchmarkResponse | null
  benchmarkError: string | null
  executiveVerdict: AnalysisExecutiveVerdict | null
  executiveVerdictError: string | null
  isLoadingBenchmark: boolean
  isLoadingExecutiveVerdict: boolean
  hasResults: boolean
}) {
  if (!hasResults) {
    return (
      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Typography variant="h6">Executive verdict</Typography>
          <Typography color="text.secondary" variant="body2">
            Complete an analysis run to generate a benchmark-aware ship, iterate, or high-risk summary.
          </Typography>
        </Stack>
      </Paper>
    )
  }

  const verdictTone =
    executiveVerdict?.status === 'ship'
      ? 'success'
      : executiveVerdict?.status === 'high_risk'
        ? 'error'
        : 'warning'

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">Executive verdict</Typography>
            <Typography color="text.secondary" variant="body2">
              A benchmark-aware decision summary for the current creative version.
            </Typography>
          </Box>
          {executiveVerdict ? (
            <Chip color={verdictTone} label={executiveVerdict.status.replace('_', ' ')} size="small" />
          ) : null}
        </Stack>
        {isLoadingBenchmark || isLoadingExecutiveVerdict ? <LinearProgress sx={{ borderRadius: 999, height: 8 }} /> : null}
        {benchmarkError ? <Alert severity="warning">{benchmarkError}</Alert> : null}
        {executiveVerdictError ? <Alert severity="warning">{executiveVerdictError}</Alert> : null}
        {executiveVerdict ? (
          <>
            <Typography variant="h5">{executiveVerdict.headline}</Typography>
            <Typography color="text.secondary" variant="body2">
              {executiveVerdict.summary}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip
                icon={<AutoGraphRounded />}
                label={
                  executiveVerdict.benchmark_average_percentile != null
                    ? `Avg percentile ${Math.round(executiveVerdict.benchmark_average_percentile)}`
                    : 'Benchmark pending'
                }
                size="small"
                variant="outlined"
              />
              {benchmark ? <Chip label={`${benchmark.cohort_size} peers`} size="small" variant="outlined" /> : null}
            </Stack>
            <Typography variant="subtitle2">Strengths</Typography>
            <Stack spacing={0.75}>
              {executiveVerdict.top_strengths.map((item) => (
                <Typography color="text.secondary" key={item} variant="body2">
                  {item}
                </Typography>
              ))}
            </Stack>
            <Typography variant="subtitle2">Risks</Typography>
            <Stack spacing={0.75}>
              {executiveVerdict.top_risks.map((item) => (
                <Typography color="text.secondary" key={item} variant="body2">
                  {item}
                </Typography>
              ))}
            </Stack>
            <Typography variant="subtitle2">Recommended actions</Typography>
            <Stack spacing={0.75}>
              {executiveVerdict.recommended_actions.map((item) => (
                <Typography color="text.secondary" key={item} variant="body2">
                  {item}
                </Typography>
              ))}
            </Stack>
          </>
        ) : null}
      </Stack>
    </Paper>
  )
}

function BenchmarkPercentilesCard({
  benchmark,
  errorMessage,
  hasResults,
  isLoading,
}: {
  benchmark: AnalysisBenchmarkResponse | null
  errorMessage: string | null
  hasResults: boolean
  isLoading: boolean
}) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Typography variant="h6">Benchmark percentiles</Typography>
        <Typography color="text.secondary" variant="body2">
          Internal peer benchmarks seeded from completed analyses in the same workspace cohort.
        </Typography>
        {isLoading ? <LinearProgress sx={{ borderRadius: 999, height: 8 }} /> : null}
        {errorMessage ? <Alert severity="warning">{errorMessage}</Alert> : null}
        {!hasResults ? (
          <Typography color="text.secondary" variant="body2">
            Results are required before benchmark cohorts can be resolved.
          </Typography>
        ) : null}
        {benchmark ? (
          <>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip label={benchmark.cohort_label} size="small" variant="outlined" />
              <Chip label={`${benchmark.cohort_size} completed runs`} size="small" variant="outlined" />
            </Stack>
            <Stack spacing={1.25}>
              {benchmark.metrics.map((metric) => (
                <Box key={metric.key}>
                  <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5}>
                    <Typography variant="subtitle2">{metric.label}</Typography>
                    <Typography color="text.secondary" variant="body2">
                      {Math.round(metric.percentile)}th percentile
                    </Typography>
                  </Stack>
                  <LinearProgress
                    sx={{ mt: 1, mb: 0.75, borderRadius: 999, height: 10 }}
                    value={metric.percentile}
                    variant="determinate"
                  />
                  <Typography color="text.secondary" variant="caption">
                    Value {metric.value.toFixed(1)} · Median {metric.cohort_median.toFixed(1)} · P75 {metric.cohort_p75.toFixed(1)}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </>
        ) : null}
      </Stack>
    </Paper>
  )
}

function CalibrationPanel({
  calibration,
  errorMessage,
  hasResults,
  isImporting,
  isLoading,
  onImportCsv,
}: {
  calibration: AnalysisCalibrationResponse | null
  errorMessage: string | null
  hasResults: boolean
  isImporting: boolean
  isLoading: boolean
  onImportCsv: (event: ChangeEvent<HTMLInputElement>) => void
}) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">Outcome calibration</Typography>
            <Typography color="text.secondary" variant="body2">
              Import CSV outcome data to compare prediction signals against actual performance metrics.
            </Typography>
          </Box>
          <Button component="label" disabled={!hasResults || isImporting} size="small" variant="outlined">
            {isImporting ? 'Importing…' : 'Import CSV'}
            <input accept=".csv,text/csv" hidden onChange={onImportCsv} type="file" />
          </Button>
        </Stack>
        {isLoading ? <LinearProgress sx={{ borderRadius: 999, height: 8 }} /> : null}
        {errorMessage ? <Alert severity="warning">{errorMessage}</Alert> : null}
        {!hasResults ? (
          <Typography color="text.secondary" variant="body2">
            Finish an analysis first, then import CSV rows with `analysis_job_id`, `metric_type`, `metric_value`, and `observed_at`.
          </Typography>
        ) : null}
        {calibration ? (
          <>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip label={`${calibration.summary.observation_count} observations`} size="small" variant="outlined" />
              <Chip
                label={
                  calibration.summary.latest_observed_at
                    ? `Latest ${formatTimestamp(calibration.summary.latest_observed_at)}`
                    : 'No imported outcomes yet'
                }
                size="small"
                variant="outlined"
              />
            </Stack>
            {calibration.summary.metric_types.length > 0 ? (
              <Typography color="text.secondary" variant="body2">
                Metrics imported: {calibration.summary.metric_types.join(', ')}
              </Typography>
            ) : null}
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Metric</TableCell>
                  <TableCell>Score</TableCell>
                  <TableCell align="right">Predicted</TableCell>
                  <TableCell align="right">Actual</TableCell>
                  <TableCell>Observed</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {calibration.observations.slice(0, 8).map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.metric_type}</TableCell>
                    <TableCell>{item.score_type}</TableCell>
                    <TableCell align="right">{item.predicted_value.toFixed(1)}</TableCell>
                    <TableCell align="right">{item.actual_value.toFixed(2)}</TableCell>
                    <TableCell>{formatTimestamp(item.observed_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {calibration.observations.length === 0 ? (
              <Typography color="text.secondary" variant="body2">
                No calibration observations yet for this analysis job.
              </Typography>
            ) : null}
          </>
        ) : null}
      </Stack>
    </Paper>
  )
}

function ResultStateBanner({
  resultState,
  analysisJob,
  diagnostics,
  progressLabel,
  sessionToken,
  onRerunSuccess,
}: {
  resultState: 'empty' | 'loading' | 'partial' | 'ready' | 'failed'
  analysisJob: AnalysisJob | null
  diagnostics: AnalysisTransportDiagnostics
  progressLabel: string | null
  sessionToken?: string
  onRerunSuccess?: (job: AnalysisJob) => void
}) {
  const [rerunning, setRerunning] = useState(false)
  const [rerunError, setRerunError] = useState<string | null>(null)

  const transportAlert =
    analysisJob && analysisJob.status !== 'completed' && analysisJob.status !== 'failed'
      ? diagnostics.mode === 'polling'
        ? (
            <Alert severity="warning">
              Live updates disconnected. The page switched to polling every 4 seconds for this run. {reconnectAttemptLabel(diagnostics.reconnectCount)} recorded.
            </Alert>
          )
        : !diagnostics.isConnected
          ? (
              <Alert severity="info">
                Connecting to live updates. The page will fall back to polling if the stream cannot stay open.
              </Alert>
            )
          : null
      : null

  const handleRerun = async () => {
    if (!analysisJob || !sessionToken) return
    setRerunning(true)
    setRerunError(null)
    try {
      const response = await apiRequest<{ job: AnalysisJob }>(
        `/analysis/jobs/${analysisJob.id}/rerun`,
        { method: 'POST', sessionToken }
      )
      onRerunSuccess?.(response.job)
    } catch (err) {
      setRerunError(err instanceof Error ? err.message : 'Failed to rerun job.')
    } finally {
      setRerunning(false)
    }
  }

  if (resultState === 'ready') {
    return null
  }
  if (resultState === 'failed') {
    return (
      <Stack spacing={1}>
        {transportAlert}
        <Alert
          severity="error"
          action={
            sessionToken ? (
              <Button
                color="inherit"
                size="small"
                disabled={rerunning}
                onClick={handleRerun}
              >
                {rerunning ? 'Retrying…' : 'Retry'}
              </Button>
            ) : undefined
          }
        >
          {analysisJob?.error_message || 'Analysis failed before results were produced.'}
        </Alert>
        {rerunError ? <Alert severity="warning">{rerunError}</Alert> : null}
      </Stack>
    )
  }
  if (resultState === 'partial') {
    if (analysisJob?.status === 'completed' && !progressLabel) {
      return (
        <Stack spacing={1}>
          {transportAlert}
          <Alert severity="warning">The job completed, but the dashboard payload is still being fetched.</Alert>
        </Stack>
      )
    }
    return (
      <Stack spacing={1}>
        {transportAlert}
        <Alert severity="info">
          {progressLabel || 'Provisional charts are ready.'} Recommendations and exports will unlock after postprocessing finishes.
        </Alert>
      </Stack>
    )
  }
  if (resultState === 'loading') {
    return (
      <Stack spacing={1}>
        {transportAlert}
        <Alert severity="info">
          {progressLabel || 'The worker is building events, running TRIBE inference, and postprocessing dashboard outputs.'}
        </Alert>
      </Stack>
    )
  }
  return (
    <Stack spacing={1}>
      {transportAlert}
      <Alert severity="info">
        Upload or select an asset, set the review goal, then start analysis. If you want to resume an earlier run instead,
        open the recent analyses panel.
      </Alert>
    </Stack>
  )
}

function AnalysisFlowOverview({
  currentStep,
  hasStoredAsset,
  hasGoalContext,
  hasResults,
}: {
  currentStep: AnalysisFlowStepId
  hasStoredAsset: boolean
  hasGoalContext: boolean
  hasResults: boolean
}) {
  const steps = [
    {
      id: 'asset' as const,
      label: '1. Prepare asset',
      detail: 'Upload new media or select an existing asset from the library.',
      isComplete: hasStoredAsset,
    },
    {
      id: 'goal' as const,
      label: '2. Set goal',
      detail: 'Choose a review template, channel, audience, and objective.',
      isComplete: hasGoalContext,
    },
    {
      id: 'results' as const,
      label: '3. Review results',
      detail: 'Inspect the summary, scenes, intervals, and recommendations.',
      isComplete: hasResults,
    },
  ]

  return (
    <Box className="analysis-flow-grid">
      {steps.map((step) => {
        const stateClassName = step.isComplete ? 'is-complete' : step.id === currentStep ? 'is-active' : ''
        return (
          <Box className={`analysis-flow-card ${stateClassName}`.trim()} key={step.id}>
            <Stack spacing={1}>
              <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1}>
                <Typography variant="subtitle2">{step.label}</Typography>
                <Chip
                  color={step.isComplete ? 'success' : step.id === currentStep ? 'primary' : 'default'}
                  label={step.isComplete ? 'Ready' : step.id === currentStep ? 'Current' : 'Next'}
                  size="small"
                  variant="outlined"
                />
              </Stack>
              <Typography color="text.secondary" variant="body2">
                {step.detail}
              </Typography>
            </Stack>
          </Box>
        )
      })}
    </Box>
  )
}

function TimelineChart({
  points,
  highAttentionIntervals,
  lowAttentionIntervals,
}: {
  points: AnalysisTimelinePoint[]
  highAttentionIntervals?: AnalysisInterval[]
  lowAttentionIntervals?: AnalysisInterval[]
}) {
  const width = 520
  const height = 200
  const engagementPath = buildSeriesPath(points, width, height, 'engagement_score')
  const attentionPath = buildSeriesPath(points, width, height, 'attention_score')
  const memoryPath = buildSeriesPath(points, width, height, 'memory_proxy')

  function intervalToX(ms: number): number {
    if (points.length <= 1) return 0
    const step = width / (points.length - 1)
    let bestIdx = 0
    let bestDiff = Infinity
    for (let i = 0; i < points.length; i++) {
      const diff = Math.abs(points[i].timestamp_ms - ms)
      if (diff < bestDiff) {
        bestDiff = diff
        bestIdx = i
      }
    }
    return bestIdx * step
  }

  return (
    <Box className="analysis-timeline-chart">
      <svg aria-label="analysis timeline chart" viewBox={`0 0 ${width} ${height}`}>
        {(highAttentionIntervals ?? []).map((interval, i) => {
          const x = intervalToX(interval.start_time_ms)
          const w = Math.max(2, intervalToX(interval.end_time_ms) - x)
          return <rect key={`hi-${i}`} x={x} y={0} width={w} height={height} fill="#16a34a" fillOpacity={0.10} />
        })}
        {(lowAttentionIntervals ?? []).map((interval, i) => {
          const x = intervalToX(interval.start_time_ms)
          const w = Math.max(2, intervalToX(interval.end_time_ms) - x)
          return <rect key={`lo-${i}`} x={x} y={0} width={w} height={height} fill="#dc2626" fillOpacity={0.10} />
        })}
        <path className="analysis-timeline-chart__grid" d={`M 0 ${height - 1} H ${width}`} />
        <path className="analysis-timeline-chart__line analysis-timeline-chart__line--engagement" d={engagementPath} />
        <path className="analysis-timeline-chart__line analysis-timeline-chart__line--attention" d={attentionPath} />
        <path className="analysis-timeline-chart__line analysis-timeline-chart__line--memory" d={memoryPath} />
      </svg>
      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        <LegendSwatch color="#f97316" label="Engagement" />
        <LegendSwatch color="#3b5bdb" label="Attention" />
        <LegendSwatch color="#14b8a6" label="Memory Proxy" />
        {(highAttentionIntervals ?? []).length > 0 && (
          <LegendSwatch color="#16a34a" label="High attention zone" />
        )}
        {(lowAttentionIntervals ?? []).length > 0 && (
          <LegendSwatch color="#dc2626" label="Low attention zone" />
        )}
      </Stack>
      <Stack direction="row" justifyContent="space-between" spacing={1}>
        {points.slice(0, 4).map((point) => (
          <Typography color="text.secondary" key={point.timestamp_ms} variant="caption">
            {formatDuration(point.timestamp_ms)}
          </Typography>
        ))}
      </Stack>
    </Box>
  )
}

function TimelineChartSkeleton({ label }: { label: string }) {
  return (
    <Stack spacing={1.5}>
      <Box
        className="analysis-timeline-chart"
        sx={{
          borderRadius: '24px',
          border: '1px solid rgba(24, 34, 48, 0.08)',
          p: 2,
        }}
      >
        <Stack spacing={1.25}>
          <Skeleton height={18} sx={{ transform: 'none' }} width="100%" />
          <Skeleton height={18} sx={{ transform: 'none' }} width="92%" />
          <Skeleton height={18} sx={{ transform: 'none' }} width="84%" />
          <Skeleton height={18} sx={{ transform: 'none' }} width="76%" />
          <Stack direction="row" justifyContent="space-between" spacing={1}>
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={`timeline-axis-${index}`} height={18} sx={{ transform: 'none' }} width={42} />
            ))}
          </Stack>
        </Stack>
      </Box>
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
    </Stack>
  )
}

function VideoFrameStrip({
  frames,
  hasResults,
  isScoringReady,
  asset,
  sessionToken,
}: {
  frames: AnalysisFrameBreakdownItem[]
  hasResults: boolean
  isScoringReady: boolean
  asset: AnalysisAsset | null
  sessionToken: string | null
}) {
  const [frameThumbnails, setFrameThumbnails] = useState<Record<number, string>>({})
  const [thumbnailAspectRatio, setThumbnailAspectRatio] = useState('16 / 9')
  const [thumbnailState, setThumbnailState] = useState<'idle' | 'loading' | 'ready' | 'failed'>('idle')
  const frameTimestampsKey = frames.map((frame) => frame.timestamp_ms).join(',')
  const thumbnailCacheRef = useRef(
    new Map<string, { previewsByTimestamp: Record<number, string>; aspectRatio: string }>(),
  )

  useEffect(() => {
    let isCancelled = false

    if (!hasResults || !asset || asset.media_type !== 'video' || !sessionToken || frames.length === 0) {
      setFrameThumbnails({})
      setThumbnailAspectRatio('16 / 9')
      setThumbnailState('idle')
      return () => {
        isCancelled = true
      }
    }

    if (!canExtractVideoFrames(asset.mime_type || 'video/mp4')) {
      setFrameThumbnails({})
      setThumbnailAspectRatio('16 / 9')
      setThumbnailState('failed')
      return () => {
        isCancelled = true
      }
    }

    const controller = new AbortController()
    const thumbnailCacheKey = `${asset.id}:${frameTimestampsKey}`

    const cachedResult = thumbnailCacheRef.current.get(thumbnailCacheKey)
    if (cachedResult) {
      setFrameThumbnails(cachedResult.previewsByTimestamp)
      setThumbnailAspectRatio(cachedResult.aspectRatio)
      setThumbnailState('ready')
      return () => {
        isCancelled = true
        controller.abort()
      }
    }

    const loadThumbnails = async () => {
      setThumbnailState('loading')
      try {
        const response = await apiFetch(`/api/v1/analysis/assets/${asset.id}/media`, {
          sessionToken,
          signal: controller.signal,
        })
        const blob = await response.blob()
        const resolvedMimeType = blob.type || asset.mime_type || 'video/mp4'
        if (isCancelled) {
          return
        }

        if (!canExtractVideoFrames(resolvedMimeType)) {
          throw new Error(`Unsupported video type for frame extraction: ${resolvedMimeType}`)
        }

        const { previewsByTimestamp, aspectRatio } = await generateFrameThumbnailMap({
          blob,
          frames,
          mimeType: resolvedMimeType,
          signal: controller.signal,
        })

        if (isCancelled) {
          return
        }

        thumbnailCacheRef.current.set(thumbnailCacheKey, {
          previewsByTimestamp,
          aspectRatio,
        })
        setFrameThumbnails(previewsByTimestamp)
        setThumbnailAspectRatio(aspectRatio)
        setThumbnailState('ready')
      } catch (error) {
        if (isCancelled || controller.signal.aborted) {
          return
        }
        setFrameThumbnails({})
        setThumbnailAspectRatio('16 / 9')
        setThumbnailState('failed')
        console.warn('Unable to generate analysis frame thumbnails.', error)
      }
    }

    void loadThumbnails()

    return () => {
      isCancelled = true
      controller.abort()
    }
  }, [asset?.id, asset?.media_type, asset?.mime_type, frameTimestampsKey, frames, hasResults, sessionToken])

  if (!hasResults) {
    return (
      <Box className="analysis-frame-strip" data-testid="frame-breakdown-strip">
        <Typography color="text.secondary" sx={{ mb: 1.5 }} variant="body2">
          Extracted frame previews will populate here once the analysis result is ready.
        </Typography>
        <Box className="analysis-frame-grid">
          {Array.from({ length: 4 }).map((_, i) => (
            <Box className="analysis-frame-card analysis-frame-card--placeholder" key={i}>
              <Box className="analysis-frame-card__thumbnail analysis-frame-card__thumbnail--placeholder" />
              <Box className="analysis-frame-card__title-skeleton" />
              <Box className="analysis-frame-card__subtitle-skeleton" />
            </Box>
          ))}
        </Box>
      </Box>
    )
  }

  if (frames.length === 0) {
    return (
      <Typography color="text.secondary" variant="body2">
        No analysis timestamps are available for this run yet.
      </Typography>
    )
  }

  return (
    <Box
      aria-label="Frame-by-frame breakdown"
      className="analysis-frame-strip"
      data-testid="frame-breakdown-strip"
    >
      <Box className="analysis-frame-grid">
        {frames.map((frame) => {
          const thumbnailSrc = frameThumbnails[frame.timestamp_ms]
          const hasThumbnail = Boolean(thumbnailSrc)

          return (
            <Box
              className="analysis-frame-card"
              data-testid={`frame-breakdown-card-${frame.timestamp_ms}`}
              key={frame.timestamp_ms}
            >
              <Box
                className="analysis-frame-card__thumbnail"
                sx={{ aspectRatio: thumbnailAspectRatio }}
              >
                {hasThumbnail ? (
                  <Box
                    alt={`${frame.label} preview`}
                    className="analysis-frame-card__image"
                    component="img"
                    src={thumbnailSrc}
                  />
                ) : (
                  <Box className="analysis-frame-card__thumbnail-fallback">
                    <Typography variant="caption">
                      {thumbnailState === 'loading' ? 'Loading frame...' : 'Preview unavailable'}
                    </Typography>
                  </Box>
                )}
                <Box className="analysis-frame-card__time-badge">
                  <Typography variant="caption">{formatDuration(frame.timestamp_ms)}</Typography>
                </Box>
              </Box>

              <Stack spacing={0.75}>
                <Typography variant="subtitle2">{frame.label}</Typography>
                <Typography color="text.secondary" variant="caption">
                  {frame.scene_label}
                </Typography>
                <Chip
                  label={frame.strongest_zone ? formatZoneLabel(frame.strongest_zone) : 'Zone unavailable'}
                  size="small"
                  variant="outlined"
                />
              </Stack>

              <Box className="analysis-frame-card__scores">
                <Box className="analysis-frame-card__score-row">
                  <Typography color="text.secondary" variant="caption">
                    Attention
                  </Typography>
                  {isScoringReady ? (
                    <Typography variant="caption">{Math.round(frame.attention_score)}/100</Typography>
                  ) : (
                    <Skeleton height={18} sx={{ transform: 'none' }} width={54} />
                  )}
                </Box>
                <Box className="analysis-frame-card__score-row">
                  <Typography color="text.secondary" variant="caption">
                    Engagement
                  </Typography>
                  {isScoringReady ? (
                    <Typography variant="caption">{Math.round(frame.engagement_score)}/100</Typography>
                  ) : (
                    <Skeleton height={18} sx={{ transform: 'none' }} width={54} />
                  )}
                </Box>
                <Box className="analysis-frame-card__score-row">
                  <Typography color="text.secondary" variant="caption">
                    Memory
                  </Typography>
                  {isScoringReady ? (
                    <Typography variant="caption">{Math.round(frame.memory_proxy)}/100</Typography>
                  ) : (
                    <Skeleton height={18} sx={{ transform: 'none' }} width={54} />
                  )}
                </Box>
              </Box>
            </Box>
          )
        })}
      </Box>
    </Box>
  )
}

function HeatmapFramesCard({
  frames,
  isSceneReady,
  isScoringReady,
  loadingLabel,
}: {
  frames: AnalysisHeatmapFrame[]
  isSceneReady: boolean
  isScoringReady: boolean
  loadingLabel: string
}) {
  if (!isSceneReady) {
    return (
      <Stack spacing={1.25}>
        {Array.from({ length: 2 }).map((_, index) => (
          <Box className="analysis-heatmap-frame" key={`heatmap-skeleton-${index}`}>
            <Stack direction="row" justifyContent="space-between" spacing={2}>
              <Box sx={{ flex: 1 }}>
                <Skeleton height={24} sx={{ transform: 'none' }} width="52%" />
                <Skeleton height={18} sx={{ transform: 'none' }} width="68%" />
              </Box>
              <Skeleton height={30} sx={{ borderRadius: 999, transform: 'none' }} width={112} />
            </Stack>
            <Box
              className="analysis-heatmap-frame__grid"
              sx={{ gridTemplateColumns: 'repeat(3, minmax(44px, 1fr))' }}
            >
              {Array.from({ length: 9 }).map((__, cellIndex) => (
                <Skeleton key={`heatmap-cell-${index}-${cellIndex}`} height={52} sx={{ transform: 'none' }} variant="rounded" />
              ))}
            </Box>
          </Box>
        ))}
        <Typography color="text.secondary" variant="body2">
          {loadingLabel}
        </Typography>
      </Stack>
    )
  }

  return (
    <Box className="analysis-heatmap-frame-list">
      {frames.map((frame) => (
        <Box className="analysis-heatmap-frame" key={`${frame.label}-${frame.timestamp_ms}`}>
          <Stack direction="row" justifyContent="space-between" spacing={2}>
            <Box>
              <Typography variant="subtitle2">{frame.label}</Typography>
              <Typography color="text.secondary" variant="body2">
                {frame.scene_label} at {formatDuration(frame.timestamp_ms)}
              </Typography>
            </Box>
            <Chip
              label={isScoringReady ? formatZoneLabel(frame.strongest_zone) : 'Pending scoring'}
              size="small"
              variant="outlined"
            />
          </Stack>

          <Box
            className="analysis-heatmap-frame__grid"
            sx={{ gridTemplateColumns: `repeat(${frame.grid_columns}, minmax(44px, 1fr))` }}
          >
            {frame.intensity_map.flatMap((row, rowIndex) =>
              row.map((value, columnIndex) => (
                <Box
                  className="analysis-heatmap-frame__cell"
                  key={`${frame.timestamp_ms}-${rowIndex}-${columnIndex}`}
                  sx={{
                    bgcolor: isScoringReady
                      ? `rgba(59, 91, 219, ${Math.max(0.08, Math.min(0.9, value / 100))})`
                      : 'rgba(148, 163, 184, 0.14)',
                  }}
                >
                  {isScoringReady ? (
                    <Typography variant="caption">{Math.round(value)}</Typography>
                  ) : (
                    <Skeleton height={18} sx={{ transform: 'none', mx: 'auto' }} width={22} />
                  )}
                </Box>
              )),
            )}
          </Box>

          <Typography color="text.secondary" variant="body2">
            {isScoringReady
              ? frame.caption
              : 'Frame scaffolding is ready. Zone intensity scores will fill in after primary scoring completes.'}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}

function AttentionIntervalsCard({
  highAttentionIntervals,
  lowAttentionIntervals,
  hasResults,
  loadingLabel,
}: {
  highAttentionIntervals: AnalysisInterval[]
  lowAttentionIntervals: AnalysisInterval[]
  hasResults: boolean
  loadingLabel: string
}) {
  if (!hasResults) {
    return (
      <Box className="analysis-interval-grid">
        <IntervalSkeletonColumn title="High attention" loadingLabel={loadingLabel} />
        <IntervalSkeletonColumn title="Low attention" loadingLabel={loadingLabel} />
      </Box>
    )
  }

  return (
    <Box className="analysis-interval-grid">
      <IntervalColumn
        title="High attention"
        intervals={highAttentionIntervals}
        emptyLabel={hasResults ? 'No standout high-attention interval detected.' : 'Intervals will appear after analysis.'}
        tone="#0f766e"
      />
      <IntervalColumn
        title="Low attention"
        intervals={lowAttentionIntervals}
        emptyLabel={hasResults ? 'No low-attention dip detected.' : 'Intervals will appear after analysis.'}
        tone="#c2410c"
      />
    </Box>
  )
}

function IntervalSkeletonColumn({
  title,
  loadingLabel,
}: {
  title: string
  loadingLabel: string
}) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2">{title}</Typography>
      <Box className="analysis-empty-state">
        <Stack spacing={1.1} sx={{ width: '100%' }}>
          <Skeleton height={56} sx={{ transform: 'none' }} variant="rounded" />
          <Skeleton height={56} sx={{ transform: 'none' }} variant="rounded" />
          <Typography color="text.secondary" variant="body2">
            {loadingLabel}
          </Typography>
        </Stack>
      </Box>
    </Stack>
  )
}

function IntervalColumn({
  title,
  intervals,
  emptyLabel,
  tone,
}: {
  title: string
  intervals: AnalysisInterval[]
  emptyLabel: string
  tone: string
}) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2">{title}</Typography>
      {intervals.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            {emptyLabel}
          </Typography>
        </Box>
      ) : (
        intervals.map((interval) => (
          <Box className="analysis-interval-card" key={`${title}-${interval.start_time_ms}`}>
            <Stack direction="row" justifyContent="space-between" spacing={2}>
              <Typography variant="subtitle2">
                {formatDuration(interval.start_time_ms)} - {formatDuration(interval.end_time_ms)}
              </Typography>
              <Chip
                label={`${Math.round(interval.average_attention_score)}/100`}
                size="small"
                sx={{ color: tone, borderColor: `${tone}55` }}
                variant="outlined"
              />
            </Stack>
            <Typography color="text.secondary" variant="body2">
              {interval.label}
            </Typography>
          </Box>
        ))
      )}
    </Stack>
  )
}

function RecommendationsCard({
  recommendations,
  hasResults,
  isPartial,
  isReady,
  loadingLabel,
  summary,
}: {
  recommendations: AnalysisRecommendation[]
  hasResults: boolean
  isPartial: boolean
  isReady: boolean
  loadingLabel: string
  summary: AnalysisSummary
}) {
  if (!hasResults && !isPartial) {
    return (
      <Box className="analysis-empty-state">
        <Typography color="text.secondary" variant="body2">
          Recommendations are generated after postprocessing turns the TRIBE output into marketer-facing intervals and metrics.
        </Typography>
      </Box>
    )
  }

  if (!isReady) {
    return (
      <Stack spacing={1.5}>
        <Typography color="text.secondary" variant="body2">
          {loadingLabel}
        </Typography>
        {Array.from({ length: 2 }).map((_, index) => (
          <Box className="analysis-recommendation" key={`recommendation-skeleton-${index}`}>
            <Stack direction="row" justifyContent="space-between" spacing={1.5}>
              <Skeleton height={24} sx={{ transform: 'none' }} width="56%" />
              <Skeleton height={30} sx={{ borderRadius: 999, transform: 'none' }} width={72} />
            </Stack>
            <Skeleton height={18} sx={{ transform: 'none', mt: 1 }} width="100%" />
            <Skeleton height={18} sx={{ transform: 'none' }} width="82%" />
          </Box>
        ))}
      </Stack>
    )
  }

  if (recommendations.length === 0) {
    return (
      <Box className="analysis-empty-state">
        <Typography color="text.secondary" variant="body2">
          {isPartial
            ? 'Recommendations are still being generated. The current charts are a provisional preview of the run.'
            : `No recommendations were generated for this run. Summary confidence: ${formatOptionalScore(summary.confidence)}.`}
        </Typography>
      </Box>
    )
  }

  return (
    <Stack spacing={1.5}>
      {recommendations.map((recommendation) => (
        <Box className="analysis-recommendation" key={`${recommendation.title}-${recommendation.timestamp_ms ?? 'na'}`}>
          <Stack direction="row" justifyContent="space-between" spacing={1.5}>
            <Typography variant="subtitle2">{recommendation.title}</Typography>
            <Chip
              className={`analysis-priority-chip analysis-priority-chip--${recommendation.priority}`}
              label={recommendation.priority}
              size="small"
              variant="outlined"
            />
          </Stack>
          <Typography color="text.secondary" variant="body2">
            {recommendation.detail}
          </Typography>
          <Stack direction="row" spacing={1.5}>
            <Typography color="text.secondary" variant="caption">
              {recommendation.timestamp_ms != null ? `Timestamp ${formatDuration(recommendation.timestamp_ms)}` : 'General recommendation'}
            </Typography>
            <Typography color="text.secondary" variant="caption">
              Confidence {formatOptionalScore(recommendation.confidence)}
            </Typography>
          </Stack>
        </Box>
      ))}
    </Stack>
  )
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <Stack alignItems="center" direction="row" spacing={1}>
      <Box sx={{ width: 12, height: 12, borderRadius: 999, bgcolor: color }} />
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
    </Stack>
  )
}

function scoreToColor(score: number): string {
  const clamped = Math.max(0, Math.min(100, score))
  const hue = (clamped / 100) * 120
  return `hsl(${Math.round(hue)}, 70%, 45%)`
}

function ScoreGauge({
  value,
  label,
  isReady,
  size = 76,
}: {
  value: number
  label: string
  isReady: boolean
  size?: number
}) {
  const strokeWidth = 6
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const filled = (Math.max(0, Math.min(100, value)) / 100) * circumference
  const color = scoreToColor(value)

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.5 }}>
      <Box sx={{ position: 'relative', width: size, height: size }}>
        <svg
          aria-hidden="true"
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          style={{ transform: 'rotate(-90deg)' }}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="rgba(24,34,48,0.08)"
            strokeWidth={strokeWidth}
          />
          {isReady && (
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={color}
              strokeWidth={strokeWidth}
              strokeDasharray={`${filled} ${circumference}`}
              strokeLinecap="round"
            />
          )}
        </svg>
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {isReady ? (
            <Typography sx={{ fontWeight: 700, fontSize: 14, lineHeight: 1, color }}>
              {Math.round(value)}
            </Typography>
          ) : (
            <Skeleton width={28} height={16} sx={{ transform: 'none' }} />
          )}
        </Box>
      </Box>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ textAlign: 'center', lineHeight: 1.2, maxWidth: size }}
      >
        {label}
      </Typography>
    </Box>
  )
}

function SegmentHeatstrip({
  segments,
  isReady,
  stripHeight = 32,
}: {
  segments: AnalysisSegmentRow[]
  isReady: boolean
  stripHeight?: number
}) {
  if (!isReady) {
    return <Skeleton height={stripHeight} sx={{ transform: 'none', borderRadius: '6px' }} />
  }
  if (segments.length === 0) {
    return null
  }

  const totalDuration = segments.reduce((max, s) => Math.max(max, s.end_time_ms), 0) || 1

  return (
    <Stack spacing={0.75}>
      <Box
        role="img"
        aria-label="Segment attention heatstrip"
        sx={{
          display: 'flex',
          height: stripHeight,
          borderRadius: '6px',
          overflow: 'hidden',
          gap: '2px',
        }}
      >
        {segments.map((seg, i) => {
          const widthPct = ((seg.end_time_ms - seg.start_time_ms) / totalDuration) * 100
          return (
            <Box
              key={i}
              title={`${seg.label}: ${Math.round(seg.attention_score)}/100`}
              sx={{
                flex: `0 0 ${widthPct}%`,
                bgcolor: scoreToColor(seg.attention_score),
                cursor: 'default',
                transition: 'filter 0.15s',
                '&:hover': { filter: 'brightness(1.2)' },
              }}
            />
          )
        })}
      </Box>
      <Stack direction="row" spacing={2}>
        <LegendSwatch color="hsl(0,70%,45%)" label="Low" />
        <LegendSwatch color="hsl(60,70%,45%)" label="Mid" />
        <LegendSwatch color="hsl(120,70%,45%)" label="High" />
      </Stack>
    </Stack>
  )
}

const SIGNAL_COLUMNS: { key: keyof AnalysisSegmentRow; label: string; invert?: boolean }[] = [
  { key: 'attention_score', label: 'Attention' },
  { key: 'engagement_score', label: 'Engagement' },
  { key: 'memory_proxy', label: 'Memory' },
  { key: 'emotion_score', label: 'Emotion' },
  { key: 'cognitive_load', label: 'Cog. Load', invert: true },
  { key: 'conversion_proxy', label: 'Conversion' },
  { key: 'peak_focus', label: 'Peak Focus' },
  { key: 'temporal_change', label: 'Temporal Δ' },
  { key: 'consistency', label: 'Consistency' },
  { key: 'hemisphere_balance', label: 'Hemi. Bal.' },
]

function SignalMatrixCard({
  segments,
  isReady,
}: {
  segments: AnalysisSegmentRow[]
  isReady: boolean
}) {
  if (!isReady) {
    return <Skeleton height={200} sx={{ transform: 'none', borderRadius: '6px' }} />
  }
  if (segments.length === 0) return null

  const CELL_W = 72
  const CELL_H = 32
  const ROW_LABEL_W = 72

  return (
    <Box sx={{ overflowX: 'auto', overflowY: 'visible' }}>
      {/* header row */}
      <Box sx={{ display: 'flex', mb: 0.25 }}>
        <Box sx={{ width: ROW_LABEL_W, flexShrink: 0 }} />
        {SIGNAL_COLUMNS.map(col => (
          <Box
            key={col.key as string}
            sx={{
              width: CELL_W,
              flexShrink: 0,
              px: 0.5,
              textAlign: 'center',
            }}
          >
            <Typography
              noWrap
              color="text.secondary"
              variant="caption"
              sx={{ display: 'block', fontSize: '0.65rem', lineHeight: 1.2 }}
            >
              {col.label}
            </Typography>
          </Box>
        ))}
      </Box>

      {/* data rows */}
      {segments.map(seg => (
        <Box key={seg.segment_index} sx={{ display: 'flex', mb: '2px', alignItems: 'center' }}>
          {/* row label */}
          <Box sx={{ width: ROW_LABEL_W, flexShrink: 0, pr: 0.5 }}>
            <Typography
              noWrap
              color="text.secondary"
              variant="caption"
              sx={{ fontSize: '0.65rem' }}
            >
              {seg.label}
            </Typography>
          </Box>

          {/* cells */}
          {SIGNAL_COLUMNS.map(col => {
            const raw = ((seg[col.key] as number | undefined) ?? 0)
            const hasData = (seg[col.key] as number | undefined) !== undefined
            const displayScore = col.invert ? 100 - raw : raw
            const color = hasData ? scoreToColor(displayScore) : 'rgba(128,128,128,0.15)'
            return (
              <Box
                key={col.key as string}
                title={hasData ? `${seg.label} · ${col.label}: ${Math.round(raw)}/100` : `${seg.label} · ${col.label}: no data (re-run analysis)`}
                sx={{
                  width: CELL_W,
                  height: CELL_H,
                  flexShrink: 0,
                  bgcolor: color,
                  borderRadius: '3px',
                  mx: '1px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'default',
                  transition: 'filter 0.15s',
                  '&:hover': { filter: 'brightness(1.2)' },
                }}
              >
                <Typography
                  variant="caption"
                  sx={{ color: hasData ? '#fff' : 'text.disabled', fontSize: '0.6rem', fontWeight: 600, lineHeight: 1 }}
                >
                  {hasData ? Math.round(raw) : '—'}
                </Typography>
              </Box>
            )
          })}
        </Box>
      ))}

      {/* legend */}
      <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
        <LegendSwatch color="hsl(0,70%,45%)" label="Low" />
        <LegendSwatch color="hsl(60,70%,45%)" label="Mid" />
        <LegendSwatch color="hsl(120,70%,45%)" label="High" />
        <Typography color="text.secondary" variant="caption" sx={{ ml: 1, alignSelf: 'center' }}>
          * Cognitive Load is inverted (high = bad)
        </Typography>
      </Stack>
    </Box>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
      <Typography sx={{ textAlign: 'right', wordBreak: 'break-word' }} variant="subtitle2">
        {value}
      </Typography>
    </Stack>
  )
}

function ValidationRow({ label, value }: { label: string; value: string }) {
  return (
    <Box className="analysis-stage-row">
      <Typography variant="subtitle2">{label}</Typography>
      <Typography color="text.secondary" variant="body2">
        {value}
      </Typography>
    </Box>
  )
}

function resetWorkflowState(
  setUploadState: Dispatch<SetStateAction<UploadState>>,
  setAnalysisJob: Dispatch<SetStateAction<AnalysisJob | null>>,
  setAnalysisResult: Dispatch<SetStateAction<AnalysisResult | null>>,
  setAnalysisPreviewResult: Dispatch<SetStateAction<AnalysisResult | null>>,
  setAnalysisProgress: Dispatch<SetStateAction<AnalysisProgressState | null>>,
  setBannerMessage: Dispatch<SetStateAction<BannerMessage | null>>,
) {
  setUploadState({
    stage: 'idle',
    progressPercent: 0,
    validationErrors: [],
  })
  setAnalysisJob(null)
  setAnalysisResult(null)
  setAnalysisPreviewResult(null)
  setAnalysisProgress(null)
  setBannerMessage(null)
}

function resolveAnalysisFlowStep({
  hasDraft,
  hasGoalContext,
  analysisJob,
  analysisResult,
}: {
  hasDraft: boolean
  hasGoalContext: boolean
  analysisJob: AnalysisJob | null
  analysisResult: AnalysisResult | null
}): AnalysisFlowStepId {
  if (analysisResult || analysisJob) {
    return 'results'
  }
  if (hasDraft && !hasGoalContext) {
    return 'goal'
  }
  if (hasDraft) {
    return 'goal'
  }
  return 'asset'
}

function mergeLatestAnalysisAsset(currentAssets: AnalysisAsset[], nextAsset: AnalysisAsset) {
  return [nextAsset, ...currentAssets.filter((asset) => asset.id !== nextAsset.id)].slice(0, 12)
}

function buildSelectedAssetStorageKey(scope: string) {
  return `neuromarketer.analysis.selected-asset.${scope}`
}

function buildSelectedJobStorageKey(scope: string) {
  return `neuromarketer.analysis.selected-job.${scope}`
}

function buildAnalysisWizardStorageKey(scope: string) {
  return `neuromarketer.analysis.wizard.${scope}`
}

function readSelectedAnalysisAssetId(storageKey: string) {
  if (typeof window === 'undefined') {
    return null
  }
  return window.sessionStorage.getItem(storageKey)
}

function readSelectedAnalysisJobId(storageKey: string) {
  if (typeof window === 'undefined') {
    return null
  }
  return window.sessionStorage.getItem(storageKey)
}

function storeSelectedAnalysisAssetId(storageKey: string, assetId: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(storageKey, assetId)
}

function clearSelectedAnalysisAssetId(storageKey: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.removeItem(storageKey)
}

function storeSelectedAnalysisJobId(storageKey: string, jobId: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(storageKey, jobId)
}

function clearSelectedAnalysisJobId(storageKey: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.removeItem(storageKey)
}

function readAnalysisWizardSnapshot(storageKey: string): AnalysisWizardSnapshot | null {
  if (typeof window === 'undefined') {
    return null
  }

  const rawSnapshot = window.sessionStorage.getItem(storageKey)
  if (!rawSnapshot) {
    return null
  }

  try {
    const parsed = JSON.parse(rawSnapshot) as Partial<AnalysisWizardSnapshot>
    if (!parsed || typeof parsed !== 'object') {
      return null
    }
    const mediaType = parsed.mediaType
    const selectionMode = parsed.selectionMode
    if (
      (mediaType !== 'video' && mediaType !== 'audio' && mediaType !== 'text') ||
      (selectionMode !== 'auto' && selectionMode !== 'asset' && selectionMode !== 'job')
    ) {
      return null
    }

    return {
      mediaType,
      objective: typeof parsed.objective === 'string' ? parsed.objective : '',
      goalTemplate: typeof parsed.goalTemplate === 'string' ? parsed.goalTemplate : '',
      channel: typeof parsed.channel === 'string' ? parsed.channel : '',
      audienceSegment: typeof parsed.audienceSegment === 'string' ? parsed.audienceSegment : '',
      selectionMode,
    }
  } catch {
    return null
  }
}

function storeAnalysisWizardSnapshot(storageKey: string, snapshot: AnalysisWizardSnapshot) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(storageKey, JSON.stringify(snapshot))
}

function scrollToSection(elementId: string) {
  if (typeof document === 'undefined') {
    return
  }
  document.getElementById(elementId)?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

function sanitizeDownloadFilename(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'analysis'
}

function downloadBlob({
  filename,
  mimeType,
  content,
}: {
  filename: string
  mimeType: string
  content: string
}) {
  if (typeof window === 'undefined') {
    return
  }

  const blob = new Blob([content], { type: mimeType })
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}

function readableGeneratedVariantType(variantType: AnalysisGeneratedVariantType) {
  switch (variantType) {
    case 'hook_rewrite':
      return 'Hook rewrite'
    case 'cta_rewrite':
      return 'CTA rewrite'
    case 'shorter_script':
      return 'Shorter script'
    case 'alternate_thumbnail':
      return 'Alternate thumbnail'
  }
  return 'Generated variant'
}

function buildGeneratedVariantText({
  asset,
  job,
  variant,
}: {
  asset: AnalysisAsset | null
  job: AnalysisJob
  variant: AnalysisGeneratedVariant
}) {
  return [
    `${variant.title}: ${asset?.original_filename || `Analysis ${shortenId(job.id)}`}`,
    '',
    `Objective: ${job.objective || 'Not specified'}`,
    `Goal template: ${job.goal_template ? readableGoalTemplate(job.goal_template) : 'Not specified'}`,
    `Channel: ${job.channel ? readableChannel(job.channel) : 'Not specified'}`,
    `Audience: ${job.audience_segment || 'Not specified'}`,
    '',
    variant.summary,
    '',
    'Focus recommendations:',
    ...(variant.focus_recommendations.length > 0
      ? variant.focus_recommendations.map((item, index) => `${index + 1}. ${item}`)
      : ['1. No specific recommendation tags were stored for this variant.']),
    '',
    'Variant sections:',
    ...variant.sections.flatMap((section) => [`${section.label}:`, section.value, '']),
    'Projected compare vs original:',
    variant.compare_summary,
    ...variant.compare_metrics.map(
      (metric) =>
        `${metric.label}: ${metric.original_value.toFixed(1)} -> ${metric.variant_value.toFixed(1)} (${formatSignedValue(metric.delta)})`,
    ),
  ].join('\n')
}

function buildQuickComparisonRows(baselineResult: AnalysisResult, comparisonResult: AnalysisResult) {
  return [
    {
      label: 'Overall attention',
      baselineValue: baselineResult.summary_json.overall_attention_score,
      comparisonValue: comparisonResult.summary_json.overall_attention_score,
    },
    {
      label: 'Hook score',
      baselineValue: baselineResult.summary_json.hook_score_first_3_seconds,
      comparisonValue: comparisonResult.summary_json.hook_score_first_3_seconds,
    },
    {
      label: 'Sustained engagement',
      baselineValue: baselineResult.summary_json.sustained_engagement_score,
      comparisonValue: comparisonResult.summary_json.sustained_engagement_score,
    },
    {
      label: 'Memory proxy',
      baselineValue: baselineResult.summary_json.memory_proxy_score,
      comparisonValue: comparisonResult.summary_json.memory_proxy_score,
    },
    {
      label: 'Low cognitive load',
      baselineValue: 100 - baselineResult.summary_json.cognitive_load_proxy,
      comparisonValue: 100 - comparisonResult.summary_json.cognitive_load_proxy,
    },
  ]
}

async function fetchAnalysisJobDetails({
  jobId,
  sessionToken,
}: {
  jobId: string
  sessionToken: string
}): Promise<AnalysisJobStatusResponse> {
  const statusResponse = await apiRequest<AnalysisJobStatusResponse>(`/api/v1/analysis/jobs/${jobId}`, {
    sessionToken,
  })

  if (statusResponse.result || statusResponse.job.status !== 'completed') {
    return statusResponse
  }

  const result = await apiRequest<AnalysisResult>(`/api/v1/analysis/jobs/${jobId}/results`, {
    sessionToken,
  })

  return {
    job: statusResponse.job,
    result,
    asset: statusResponse.asset ?? null,
  }
}

function upsertAnalysisHistoryItem(
  currentItems: AnalysisJobListItem[],
  nextItem: AnalysisJobListItem,
  limit: number,
) {
  const existingIndex = currentItems.findIndex((item) => item.job.id === nextItem.job.id)
  if (existingIndex === -1) {
    return [nextItem, ...currentItems].slice(0, limit)
  }

  const existing = currentItems[existingIndex]
  const mergedItem: AnalysisJobListItem = {
    job: nextItem.job,
    asset: nextItem.asset ?? existing.asset ?? null,
    has_result: nextItem.has_result || existing.has_result,
    result_created_at: nextItem.result_created_at ?? existing.result_created_at ?? null,
  }

  return currentItems.map((item, index) => (index === existingIndex ? mergedItem : item))
}

function resolveSuggestedGoalContext({
  suggestions,
  mediaType,
  selectedAsset,
  selectedFile,
  textFilename,
}: {
  suggestions: GoalSuggestion[]
  mediaType: MediaType
  selectedAsset?: AnalysisAsset
  selectedFile: File | null
  textFilename: string
}) {
  const sourceLabel = `${selectedAsset?.original_filename || ''} ${selectedFile?.name || ''} ${textFilename}`.toLowerCase()

  if (mediaType === 'text') {
    if (sourceLabel.includes('email') || sourceLabel.includes('newsletter')) {
      return {
        media_type: 'text' as const,
        goal_template: 'email_clickthrough',
        channel: 'email',
        audience_placeholder: 'Subscribers, trial users, lifecycle segments',
        rationale: 'The filename looks email-oriented, so clickthrough review is the best default.',
      }
    }
    if (sourceLabel.includes('landing') || sourceLabel.includes('hero') || sourceLabel.includes('homepage')) {
      return {
        media_type: 'text' as const,
        goal_template: 'landing_page_clarity',
        channel: 'landing_page',
        audience_placeholder: 'New visitors, paid traffic, ICP accounts',
        rationale: 'The filename suggests a website surface, so clarity and friction are the right first pass.',
      }
    }
  }

  if (mediaType === 'video') {
    if (sourceLabel.includes('ugc') || sourceLabel.includes('creator') || sourceLabel.includes('testimonial')) {
      return {
        media_type: 'video' as const,
        goal_template: 'ugc_native_social',
        channel: 'tiktok',
        audience_placeholder: 'Cold prospects, creator-led lookalikes, retargeting pools',
        rationale: 'The upload reads like UGC or creator content, so native-social fit is the best starting preset.',
      }
    }
    if (sourceLabel.includes('brand') || sourceLabel.includes('anthem') || sourceLabel.includes('film')) {
      return {
        media_type: 'video' as const,
        goal_template: 'brand_story_film',
        channel: 'youtube_pre_roll',
        audience_placeholder: 'Awareness audiences, high-value segments, brand lift panels',
        rationale: 'The filename suggests a campaign film, so story continuity and memory should lead the review.',
      }
    }
  }

  return suggestions.find((suggestion) => suggestion.media_type === mediaType) ?? null
}

function validateGoalContext({
  channel,
  goalTemplate,
  mediaType,
  objective,
  availableChannels,
  availableGoalTemplates,
}: {
  channel: string
  goalTemplate: string
  mediaType: MediaType
  objective: string
  availableChannels: ChannelOption[]
  availableGoalTemplates: GoalTemplateOption[]
}) {
  const errors: string[] = []

  if (!goalTemplate) {
    errors.push('Choose a review template before starting analysis.')
  } else if (!availableGoalTemplates.some((option) => option.value === goalTemplate)) {
    errors.push(`The selected template is not supported for ${mediaType} inputs.`)
  }

  if (!channel) {
    errors.push('Choose the target channel before starting analysis.')
  } else if (!availableChannels.some((option) => option.value === channel)) {
    errors.push(`The selected channel is not supported for ${mediaType} inputs.`)
  }

  if (objective.trim() && objective.trim().length < 16) {
    errors.push('Add a slightly more specific objective so downstream recommendations have enough context.')
  }

  return errors
}

function validateCurrentInput({
  config,
  mediaType,
  selectedFile,
  textContent,
}: {
  config: AnalysisConfigResponse
  mediaType: MediaType
  selectedFile: File | null
  textContent: string
}) {
  const errors: string[] = []

  if (mediaType === 'text') {
    if (selectedFile) {
      if (selectedFile.size > config.max_file_size_bytes) {
        errors.push(`File size exceeds ${formatFileSize(config.max_file_size_bytes)}.`)
      }

      const selectedMimeType = resolveUploadMimeType(selectedFile)
      if (!selectedMimeType || !config.allowed_mime_types.text.includes(selectedMimeType)) {
        errors.push(`Unsupported text mime type: ${selectedMimeType || 'unknown'}.`)
      }
      return errors
    }

    const trimmedText = textContent.trim()
    if (!trimmedText) {
      errors.push('Text analysis requires pasted content or an uploaded document.')
    }
    if (trimmedText.length > config.max_text_characters) {
      errors.push(`Text analysis is limited to ${config.max_text_characters.toLocaleString()} characters.`)
    }
    return errors
  }

  if (!selectedFile) {
    errors.push(`Select a ${mediaType} file before starting the upload.`)
    return errors
  }

  if (selectedFile.size > config.max_file_size_bytes) {
    errors.push(`File size exceeds ${formatFileSize(config.max_file_size_bytes)}.`)
  }

  if (!config.allowed_mime_types[mediaType].includes(selectedFile.type)) {
    errors.push(`Unsupported ${mediaType} mime type: ${selectedFile.type || 'unknown'}.`)
  }

  return errors
}

function buildUploadSource({
  mediaType,
  selectedFile,
  textContent,
  textFilename,
}: {
  mediaType: MediaType
  selectedFile: File | null
  textContent: string
  textFilename: string
}): UploadSource | null {
  if (mediaType === 'text') {
    if (selectedFile) {
      const mimeType = resolveUploadMimeType(selectedFile)
      if (!mimeType) {
        return null
      }
      return {
        file: selectedFile,
        fileName: selectedFile.name,
        mimeType,
        sizeBytes: selectedFile.size,
      }
    }

    const trimmedText = textContent.trim()
    if (!trimmedText) {
      return null
    }
    const file = new Blob([trimmedText], { type: 'text/plain' })
    return {
      file,
      fileName: ensureTextFilename(textFilename),
      mimeType: 'text/plain',
      sizeBytes: file.size,
    }
  }

  if (!selectedFile) {
    return null
  }

  return {
    file: selectedFile,
    fileName: selectedFile.name,
    mimeType: resolveUploadMimeType(selectedFile),
    sizeBytes: selectedFile.size,
  }
}

function buildSummaryCards(summary: AnalysisSummary): SummaryCard[] {
  return [
    {
      key: 'overall_attention_score',
      label: 'Overall Attention',
      value: summary.overall_attention_score,
      helper: `Confidence ${formatOptionalScore(summary.confidence)}`,
    },
    {
      key: 'hook_score_first_3_seconds',
      label: 'Hook Score',
      value: summary.hook_score_first_3_seconds,
      helper: 'Opening 3-second hold strength',
    },
    {
      key: 'sustained_engagement_score',
      label: 'Sustained Engagement',
      value: summary.sustained_engagement_score,
      helper: 'Average engagement after the opening beat',
    },
    {
      key: 'memory_proxy_score',
      label: 'Memory Proxy',
      value: summary.memory_proxy_score,
      helper: `Coverage ${formatOptionalScore(summary.completeness)}`,
    },
    {
      key: 'cognitive_load_proxy',
      label: 'Cognitive Load',
      value: summary.cognitive_load_proxy,
      helper: 'Higher scores indicate more friction',
    },
  ]
}

function buildFrameBreakdownItems({
  timelinePoints,
  segmentsRows,
  heatmapFrames,
}: {
  timelinePoints: AnalysisTimelinePoint[]
  segmentsRows: AnalysisSegmentRow[]
  heatmapFrames: AnalysisHeatmapFrame[]
}): AnalysisFrameBreakdownItem[] {
  const heatmapFrameByTimestamp = new Map(heatmapFrames.map((frame) => [frame.timestamp_ms, frame]))

  return timelinePoints.map((point, index) => {
    const matchingSegment =
      segmentsRows[index] ??
      segmentsRows.find((segment) => point.timestamp_ms >= segment.start_time_ms && point.timestamp_ms <= segment.end_time_ms) ??
      [...segmentsRows].reverse().find((segment) => segment.start_time_ms <= point.timestamp_ms)
    const matchingHeatmapFrame = heatmapFrameByTimestamp.get(point.timestamp_ms)

    return {
      timestamp_ms: point.timestamp_ms,
      label: `Frame ${index + 1}`,
      scene_label: matchingSegment?.label ?? matchingHeatmapFrame?.scene_label ?? `Scene ${String(index + 1).padStart(2, '0')}`,
      strongest_zone: matchingHeatmapFrame?.strongest_zone ?? null,
      attention_score: point.attention_score,
      engagement_score: point.engagement_score,
      memory_proxy: point.memory_proxy,
    }
  })
}

function canExtractVideoFrames(mimeType: string | null | undefined) {
  if (typeof document === 'undefined') {
    return false
  }

  const probe = document.createElement('video')
  if (typeof probe.canPlayType !== 'function') {
    return false
  }

  const resolvedMimeType = mimeType || 'video/mp4'
  if (probe.canPlayType(resolvedMimeType) !== '') {
    return true
  }

  if (!resolvedMimeType.includes('/')) {
    return false
  }

  const [mediaType] = resolvedMimeType.split('/', 1)
  if (mediaType !== 'video') {
    return false
  }

  return probe.canPlayType('video/mp4') !== ''
}

async function generateFrameThumbnailMap({
  blob,
  frames,
  mimeType,
  signal,
}: {
  blob: Blob
  frames: AnalysisFrameBreakdownItem[]
  mimeType: string
  signal: AbortSignal
}): Promise<{
  previewsByTimestamp: Record<number, string>
  aspectRatio: string
}> {
  const objectUrl = window.URL.createObjectURL(new Blob([blob], { type: mimeType || blob.type || 'video/mp4' }))
  const video = document.createElement('video')
  video.preload = 'auto'
  video.muted = true
  video.playsInline = true
  video.src = objectUrl
  video.load()

  try {
    await waitForVideoEvent(video, 'loadedmetadata', signal)
    await waitForVideoEvent(video, 'loadeddata', signal)

    const previewWidth = 320
    const aspectRatioValue =
      video.videoWidth > 0 && video.videoHeight > 0 ? `${video.videoWidth} / ${video.videoHeight}` : '16 / 9'
    const previewHeight =
      video.videoWidth > 0 && video.videoHeight > 0
        ? Math.max(180, Math.round(previewWidth * (video.videoHeight / video.videoWidth)))
        : 180
    const canvas = document.createElement('canvas')
    canvas.width = previewWidth
    canvas.height = previewHeight
    const context = canvas.getContext('2d')
    if (!context) {
      throw new Error('Canvas context is unavailable.')
    }

    const previewsByTimestamp: Record<number, string> = {}

    for (const frame of frames) {
      if (signal.aborted) {
        throw new DOMException('The operation was aborted.', 'AbortError')
      }

      const targetTimeSeconds = resolveThumbnailSeekTime({
        durationSeconds: video.duration,
        timestampMs: frame.timestamp_ms,
      })
      video.currentTime = targetTimeSeconds
      await waitForVideoEvent(video, 'seeked', signal)
      context.drawImage(video, 0, 0, canvas.width, canvas.height)
      previewsByTimestamp[frame.timestamp_ms] = canvas.toDataURL('image/jpeg', 0.76)
    }

    return {
      previewsByTimestamp,
      aspectRatio: aspectRatioValue,
    }
  } finally {
    window.URL.revokeObjectURL(objectUrl)
    video.removeAttribute('src')
    video.load()
  }
}

function resolveThumbnailSeekTime({
  durationSeconds,
  timestampMs,
}: {
  durationSeconds: number
  timestampMs: number
}) {
  const fallbackSeconds = Math.max(0.05, timestampMs / 1000)
  if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
    return fallbackSeconds
  }

  return Math.min(Math.max(0.05, timestampMs / 1000), Math.max(0.05, durationSeconds - 0.05))
}

function waitForVideoEvent(
  video: HTMLVideoElement,
  eventName: 'loadedmetadata' | 'loadeddata' | 'seeked',
  signal: AbortSignal,
) {
  return new Promise<void>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      cleanup()
      reject(new Error(`Timed out while waiting for video event: ${eventName}.`))
    }, 10000)

    const cleanup = () => {
      window.clearTimeout(timeoutId)
      video.removeEventListener(eventName, handleSuccess)
      video.removeEventListener('error', handleError)
      signal.removeEventListener('abort', handleAbort)
    }

    const handleSuccess = () => {
      cleanup()
      resolve()
    }

    const handleError = () => {
      cleanup()
      reject(new Error(`Unable to load video event: ${eventName}.`))
    }

    const handleAbort = () => {
      cleanup()
      reject(new DOMException('The operation was aborted.', 'AbortError'))
    }

    video.addEventListener(eventName, handleSuccess, { once: true })
    video.addEventListener('error', handleError, { once: true })
    signal.addEventListener('abort', handleAbort, { once: true })
  })
}

function resolveCurrentStage(
  progressStage: string | null | undefined,
  uploadStage: UploadStage,
  jobStatus?: AnalysisJob['status'],
) {
  if (progressStage) {
    return progressStage
  }
  if (jobStatus) {
    return jobStatus
  }
  if (uploadStage === 'validating') {
    return 'validating'
  }
  if (uploadStage === 'uploaded') {
    return 'uploaded'
  }
  if (uploadStage === 'uploading') {
    return 'uploading'
  }
  if (uploadStage === 'failed') {
    return 'failed'
  }
  return 'idle'
}

function resolveVisibleProgressState(
  analysisProgress: AnalysisProgressState | null,
  evaluationProgress: AnalysisProgressState | null,
): AnalysisProgressState | null {
  if (!evaluationProgress) {
    return analysisProgress
  }

  return {
    ...evaluationProgress,
    diagnostics:
      analysisProgress?.jobId === evaluationProgress.jobId
        ? analysisProgress.diagnostics
        : evaluationProgress.diagnostics,
  }
}

function resolveAnalysisStageAvailability({
  analysisResult,
  analysisPreviewResult,
  currentStage,
}: {
  analysisResult: AnalysisResult | null
  analysisPreviewResult: AnalysisResult | null
  currentStage: string
}) {
  if (analysisResult) {
    return {
      sceneStructureReady: true,
      primaryScoringReady: true,
      recommendationsReady: true,
    }
  }

  const sceneReadyStages = new Set([
    'scene_extraction_ready',
    'primary_scoring_started',
    'primary_scoring_ready',
    'postprocessing_started',
    'recommendations_ready',
    'completed',
    'evaluation_queued',
    'evaluation_started',
  ])
  const scoringReadyStages = new Set([
    'primary_scoring_ready',
    'postprocessing_started',
    'recommendations_ready',
    'completed',
    'evaluation_queued',
    'evaluation_started',
  ])
  const recommendationReadyStages = new Set([
    'recommendations_ready',
    'completed',
    'evaluation_queued',
    'evaluation_started',
  ])
  const hasPreview = Boolean(analysisPreviewResult)

  return {
    sceneStructureReady: hasPreview && sceneReadyStages.has(currentStage),
    primaryScoringReady: hasPreview && scoringReadyStages.has(currentStage),
    recommendationsReady: hasPreview && recommendationReadyStages.has(currentStage),
  }
}

function resolveResultState({
  analysisJob,
  analysisResult,
  analysisPreviewResult,
  uploadState,
}: {
  analysisJob: AnalysisJob | null
  analysisResult: AnalysisResult | null
  analysisPreviewResult: AnalysisResult | null
  uploadState: UploadState
}) {
  if (analysisJob?.status === 'failed') {
    return 'failed'
  }
  if (analysisResult) {
    return 'ready'
  }
  if (analysisPreviewResult) {
    return 'partial'
  }
  if (analysisJob?.status === 'completed') {
    return 'partial'
  }
  if (analysisJob?.status === 'queued' || analysisJob?.status === 'processing') {
    return 'loading'
  }
  if (uploadState.stage === 'validating') {
    return 'loading'
  }
  if (uploadState.stage === 'uploaded') {
    return 'empty'
  }
  return 'empty'
}

function stageRows(currentStage: string) {
  return [
    {
      label: 'Idle',
      detail: 'No asset is being prepared yet.',
      isActive: currentStage === 'idle',
    },
    {
      label: 'Validating',
      detail: 'Client-side validation is checking required fields, mime type, and size before upload.',
      isActive: currentStage === 'validating',
    },
    {
      label: 'Uploading',
      detail: 'The browser is streaming media directly into object storage.',
      isActive: currentStage === 'uploading',
    },
    {
      label: 'Uploaded',
      detail: 'The backend has confirmed the object and created the version reference.',
      isActive: currentStage === 'uploaded',
    },
    {
      label: 'Queued',
      detail: 'Upload finalization is done and the worker job is waiting for capacity.',
      isActive: currentStage === 'queued',
    },
    {
      label: 'Worker started',
      detail: 'A worker claimed the job and is loading the creative inputs.',
      isActive: currentStage === 'worker_started',
    },
    {
      label: 'Asset resolved',
      detail: 'Creative metadata and storage references are resolved for inference.',
      isActive: currentStage === 'asset_resolved',
    },
    {
      label: 'Inference started',
      detail: 'TRIBE event extraction is running on the uploaded asset.',
      isActive: currentStage === 'inference_started' || currentStage === 'processing',
    },
    {
      label: 'Scene extraction ready',
      detail: 'Scene windows and frame scaffolding are ready while scoring continues.',
      isActive: currentStage === 'scene_extraction_ready',
    },
    {
      label: 'Primary scoring started',
      detail: 'Attention, memory, and cognitive-load metrics are being computed.',
      isActive: currentStage === 'primary_scoring_started',
    },
    {
      label: 'Primary scoring ready',
      detail: 'Scored charts and provisional metrics are available while recommendations are pending.',
      isActive: currentStage === 'primary_scoring_ready',
    },
    {
      label: 'Post-processing started',
      detail: 'Intervals and recommendation candidates are being composed from the scored output.',
      isActive: currentStage === 'postprocessing_started',
    },
    {
      label: 'Recommendations ready',
      detail: 'Recommendation output is ready and the final dashboard payload is being persisted.',
      isActive: currentStage === 'recommendations_ready',
    },
    {
      label: 'Evaluation queued',
      detail: 'LLM critique was requested and is waiting for evaluation worker capacity.',
      isActive: currentStage === 'evaluation_queued',
    },
    {
      label: 'Evaluation started',
      detail: 'The evaluation worker is reading the completed analysis snapshot and drafting critique sections.',
      isActive: currentStage === 'evaluation_started',
    },
    {
      label: 'Completed / Failed',
      detail: 'Results are available for rendering or the error payload is attached to the job.',
      isActive: currentStage === 'completed' || currentStage === 'failed',
    },
  ]
}

function buildScenePendingMessage(stageAvailability: {
  sceneStructureReady: boolean
  primaryScoringReady: boolean
  recommendationsReady: boolean
}, currentStage: string) {
  if (['idle', 'validating', 'uploading', 'uploaded'].includes(currentStage)) {
    return 'Start analysis to populate scene windows and frame scaffolding.'
  }
  if (stageAvailability.sceneStructureReady) {
    return 'Scene extraction is complete. Attention and engagement scores are still being computed.'
  }
  return 'Scene windows and frame scaffolding will appear after inference finishes extracting the first structure pass.'
}

function buildScoringPendingMessage(stageAvailability: {
  sceneStructureReady: boolean
  primaryScoringReady: boolean
  recommendationsReady: boolean
}, currentStage: string) {
  if (['idle', 'validating', 'uploading', 'uploaded'].includes(currentStage)) {
    return 'Start analysis to unlock scored attention, memory, and cognitive-load metrics.'
  }
  if (stageAvailability.sceneStructureReady) {
    return 'Scene extraction is complete. Primary scoring is filling in attention, memory, and cognitive-load metrics now.'
  }
  return 'Primary metrics unlock after the first scene-extraction pass completes.'
}

function buildRecommendationsPendingMessage(stageAvailability: {
  sceneStructureReady: boolean
  primaryScoringReady: boolean
  recommendationsReady: boolean
}, currentStage: string) {
  if (['idle', 'validating', 'uploading', 'uploaded'].includes(currentStage)) {
    return 'Recommendations appear after a completed analysis run unlocks scoring and post-processing.'
  }
  if (stageAvailability.recommendationsReady) {
    return 'Recommendations are ready.'
  }
  if (stageAvailability.primaryScoringReady) {
    return 'Scored charts are ready. Recommendations are still being composed from the post-processed signals.'
  }
  if (stageAvailability.sceneStructureReady) {
    return 'Recommendations unlock after the scored metrics and interval pass complete.'
  }
  return 'Recommendations appear after scene extraction, scoring, and post-processing finish.'
}

function buildSeriesPath(
  points: AnalysisTimelinePoint[],
  width: number,
  height: number,
  key: keyof Pick<AnalysisTimelinePoint, 'engagement_score' | 'attention_score' | 'memory_proxy'>,
) {
  if (points.length === 0) {
    return `M 0 ${height} L ${width} ${height}`
  }

  const step = points.length === 1 ? width : width / (points.length - 1)
  const commands = points.map((point, index) => {
    const rawValue = point[key] ?? 0
    const normalizedValue = Math.max(0, Math.min(100, rawValue))
    const x = index * step
    const y = height - (normalizedValue / 100) * (height - 12) - 6
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
  })
  return commands.join(' ')
}

function ensureTextFilename(value: string) {
  const sanitized = value.trim() || 'analysis-notes.txt'
  const lastSegment = sanitized.split(/[\\/]/).pop() || sanitized
  return /\.[A-Za-z0-9]{1,10}$/.test(lastSegment) ? sanitized : `${sanitized}.txt`
}

function buildTextUploadAccept(mimeTypes: string[]) {
  return [...new Set([...mimeTypes, ...TEXT_DOCUMENT_EXTENSIONS])].join(',')
}

function resolveUploadMimeType(file: File) {
  if (file.type) {
    return file.type
  }

  const extension = resolveFileExtension(file.name)
  return extension ? TEXT_DOCUMENT_MIME_BY_EXTENSION[extension] || '' : ''
}

function resolveFileExtension(filename: string) {
  const lastDotIndex = filename.lastIndexOf('.')
  if (lastDotIndex === -1) {
    return ''
  }
  return filename.slice(lastDotIndex).toLowerCase()
}

function shortenId(value: string) {
  return `${value.slice(0, 8)}…`
}

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value
  }
  return `${value.slice(0, maxLength - 1).trimEnd()}…`
}

function formatDuration(milliseconds: number) {
  const totalSeconds = Math.floor(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function formatFileSize(sizeInBytes: number) {
  if (sizeInBytes === 0) {
    return '0 B'
  }

  const units = ['B', 'KB', 'MB', 'GB']
  let unitIndex = 0
  let value = sizeInBytes

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }

  return `${value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`
}

function formatOptionalScore(value: number | null | undefined) {
  if (value == null) {
    return '--'
  }
  return `${Math.round(value)}%`
}

function formatSignedValue(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
}

function formatZoneLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function readableGoalTemplate(value: string) {
  const match = defaultGoalTemplateOptions.find((option) => option.value === value)
  return match?.label || value.replaceAll('_', ' ')
}

function readableChannel(value: string) {
  const match = defaultChannelOptions.find((option) => option.value === value)
  return match?.label || value.replaceAll('_', ' ')
}

function formatTimestamp(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

function calculateElapsedMs(startValue: string | null | undefined, endValue: string | null | undefined) {
  if (!startValue || !endValue) {
    return null
  }
  const startedAt = new Date(startValue)
  const endedAt = new Date(endValue)
  if (Number.isNaN(startedAt.getTime()) || Number.isNaN(endedAt.getTime())) {
    return null
  }
  return Math.max(0, Math.round(endedAt.getTime() - startedAt.getTime()))
}

function normalizeAnalysisProgressState(
  jobId: string,
  progress:
    | AnalysisJobStatusResponse['progress']
    | Pick<AnalysisProgressEvent, 'stage' | 'stage_label' | 'diagnostics'>
    | null
    | undefined,
): AnalysisProgressState | null {
  if (!progress?.stage) {
    return null
  }

  return {
    jobId,
    stage: progress.stage,
    stageLabel: progress.stage_label || null,
    diagnostics: {
      queueWaitMs: progress.diagnostics?.queue_wait_ms ?? null,
      processingDurationMs: progress.diagnostics?.processing_duration_ms ?? null,
      timeToFirstResultMs: progress.diagnostics?.time_to_first_result_ms ?? null,
      resultDeliveryMs: progress.diagnostics?.result_delivery_ms ?? null,
      postprocessDurationMs: progress.diagnostics?.postprocess_duration_ms ?? null,
    },
  }
}

function areAnalysisJobsEqual(current: AnalysisJob | null, next: AnalysisJob | null) {
  return JSON.stringify(current) === JSON.stringify(next)
}

function areAnalysisResultsEqual(current: AnalysisResult | null, next: AnalysisResult | null) {
  return JSON.stringify(current) === JSON.stringify(next)
}

function areAnalysisProgressStatesEqual(current: AnalysisProgressState | null, next: AnalysisProgressState | null) {
  return JSON.stringify(current) === JSON.stringify(next)
}

function readableProgressStage(value: string | null | undefined) {
  if (!value) {
    return 'Pending'
  }

  const labels: Record<string, string> = {
    idle: 'Idle',
    validating: 'Validating',
    uploading: 'Uploading',
    uploaded: 'Uploaded',
    queued: 'Queued',
    worker_started: 'Worker started',
    asset_resolved: 'Asset resolved',
    inference_started: 'Inference started',
    scene_extraction_ready: 'Scene extraction ready',
    scoring_queued: 'Primary scoring queued',
    primary_scoring_started: 'Primary scoring started',
    primary_scoring_ready: 'Primary scoring ready',
    postprocessing_started: 'Post-processing started',
    recommendations_ready: 'Recommendations ready',
    evaluation_queued: 'Evaluation queued',
    evaluation_started: 'Evaluation started',
    completed: 'Completed',
    failed: 'Failed',
    processing: 'Processing',
  }

  return labels[value] || value.replaceAll('_', ' ')
}

function reconnectAttemptLabel(count: number) {
  return `${count} reconnect attempt${count === 1 ? '' : 's'}`
}

export default AnalysisPage
