import AudiotrackRounded from '@mui/icons-material/AudiotrackRounded'
import DescriptionRounded from '@mui/icons-material/DescriptionRounded'
import VideoLibraryRounded from '@mui/icons-material/VideoLibraryRounded'

import type {
  AnalysisGoalPresetsResponse,
  AnalysisHeatmapFrame,
  AnalysisMetricRow,
  AnalysisSegmentRow,
  AnalysisSummary,
  AnalysisTimelinePoint,
  ChannelOption,
  GoalPresetGroup,
  GoalSuggestion,
  GoalTemplateOption,
  MediaType,
} from './types'

export const TEXT_DOCUMENT_MIME_BY_EXTENSION: Record<string, string> = {
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

export const TEXT_DOCUMENT_EXTENSIONS = Object.keys(TEXT_DOCUMENT_MIME_BY_EXTENSION)

export const defaultGoalTemplateOptions: GoalTemplateOption[] = [
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

export const defaultChannelOptions: ChannelOption[] = [
  { value: 'meta_feed', label: 'Meta feed', supported_media_types: ['video', 'audio'] },
  { value: 'instagram_reels', label: 'Instagram Reels', supported_media_types: ['video'] },
  { value: 'tiktok', label: 'TikTok', supported_media_types: ['video'] },
  { value: 'youtube_pre_roll', label: 'YouTube pre-roll', supported_media_types: ['video', 'audio'] },
  { value: 'landing_page', label: 'Landing page', supported_media_types: ['video', 'text'] },
  { value: 'email', label: 'Email', supported_media_types: ['text'] },
] as const

export const defaultGoalPresetGroups: GoalPresetGroup[] = [
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

export const defaultGoalSuggestions: GoalSuggestion[] = [
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

export const defaultGoalPresets: AnalysisGoalPresetsResponse = {
  goal_templates: [...defaultGoalTemplateOptions],
  channels: [...defaultChannelOptions],
  preset_groups: [...defaultGoalPresetGroups],
  suggestions: [...defaultGoalSuggestions],
}

export const mediaTypeOptions: Array<{
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

export const placeholderSummary: AnalysisSummary = {
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

export const placeholderMetrics: AnalysisMetricRow[] = [
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

export const placeholderTimeline: AnalysisTimelinePoint[] = [
  { timestamp_ms: 0, engagement_score: 0, attention_score: 0, memory_proxy: 0 },
  { timestamp_ms: 1500, engagement_score: 0, attention_score: 0, memory_proxy: 0 },
  { timestamp_ms: 3000, engagement_score: 0, attention_score: 0, memory_proxy: 0 },
]

export const placeholderSegments: AnalysisSegmentRow[] = [
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

export const placeholderHeatmapFrames: AnalysisHeatmapFrame[] = [
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

export const ANALYSIS_HISTORY_LIMIT = 12
