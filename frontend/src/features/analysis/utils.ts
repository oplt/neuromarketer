import { apiRequest } from '../../lib/api'
import type {
  AnalysisAsset,
  AnalysisFlowStepId,
  AnalysisFrameBreakdownItem,
  AnalysisGeneratedVariant,
  AnalysisGeneratedVariantType,
  AnalysisHeatmapFrame,
  AnalysisJob,
  AnalysisJobListItem,
  AnalysisJobStatusResponse,
  AnalysisProgressEvent,
  AnalysisProgressState,
  AnalysisResult,
  AnalysisSegmentRow,
  AnalysisSummary,
  AnalysisTimelinePoint,
  GoalSuggestion,
  MediaType,
  SummaryCard,
  UploadSource,
  UploadStage,
  UploadState,
} from './types'
import {
  defaultChannelOptions,
  defaultGoalTemplateOptions,
  TEXT_DOCUMENT_EXTENSIONS,
  TEXT_DOCUMENT_MIME_BY_EXTENSION,
} from './constants'

type AnalysisJobResultDetailResponse = {
  job: AnalysisJobStatusResponse['job']
  asset?: AnalysisAsset | null
  result: AnalysisResult
  progress?: AnalysisJobStatusResponse['progress']
}

export async function fetchAnalysisJobDetails({
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

  const detailResponse = await apiRequest<AnalysisJobResultDetailResponse>(`/api/v1/analysis/jobs/${jobId}/results`, {
    sessionToken,
  })

  return {
    job: detailResponse.job,
    result: detailResponse.result,
    asset: detailResponse.asset ?? statusResponse.asset ?? null,
    progress: detailResponse.progress ?? statusResponse.progress ?? null,
  }
}

export function resolveAnalysisFlowStep({
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

export function mergeLatestAnalysisAsset(currentAssets: AnalysisAsset[], nextAsset: AnalysisAsset) {
  return [nextAsset, ...currentAssets.filter((asset) => asset.id !== nextAsset.id)].slice(0, 12)
}

export function scrollToSection(elementId: string) {
  if (typeof document === 'undefined') {
    return
  }
  document.getElementById(elementId)?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

export function sanitizeDownloadFilename(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'analysis'
}

export function downloadBlob({
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

export function readableGeneratedVariantType(variantType: AnalysisGeneratedVariantType) {
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

export function buildGeneratedVariantText({
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

export function buildQuickComparisonRows(baselineResult: AnalysisResult, comparisonResult: AnalysisResult) {
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

export function upsertAnalysisHistoryItem(
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

export function resolveSuggestedGoalContext({
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


export function buildUploadSource({
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

export function buildSummaryCards(summary: AnalysisSummary): SummaryCard[] {
  const presentation = getAnalysisResultPresentation(summary.modality)
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
      helper: presentation.hookHelper,
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

export function getAnalysisResultPresentation(mediaType: MediaType | null | undefined) {
  switch (mediaType) {
    case 'audio':
      return {
        mediaType,
        timelineTitle: 'Audio timeline',
        timelineDescription: 'Attention, engagement, and memory proxies aligned to audio windows.',
        segmentTitle: 'Audio window table',
        segmentDescription: 'Window-by-window scoring across the processed audio timeline.',
        matrixTitle: 'Multi-signal audio matrix',
        matrixDescription: 'Per-window breakdown across neural and behavioural audio signals.',
        heatmapTitle: 'Audio signal grid',
        heatmapDescription: 'A non-spatial signal grid for each selected audio window.',
        sampleTitle: 'Audio window breakdown',
        sampleDescription: 'Time-synchronized audio windows with attention, engagement, and memory scores.',
        sampleLabelPrefix: 'Audio sample',
        segmentFallbackPrefix: 'Audio window',
        pendingSampleLabel: 'Audio windows will populate here once the result is ready.',
        unavailablePreviewLabel: 'Audio has no visual frame preview.',
        recommendationTimeLabel: 'Audio time',
        hookHelper: 'Opening audio-window hold strength',
      }
    case 'text':
      return {
        mediaType,
        timelineTitle: 'Text sequence chart',
        timelineDescription: 'Attention, engagement, and memory proxies aligned to passages.',
        segmentTitle: 'Passage table',
        segmentDescription: 'Passage-by-passage scoring across the processed text sequence.',
        matrixTitle: 'Multi-signal passage matrix',
        matrixDescription: 'Per-passage breakdown across copy, memory, load, and conversion signals.',
        heatmapTitle: 'Copy signal grid',
        heatmapDescription: 'A non-spatial signal grid for selected passages, not a visual heatmap.',
        sampleTitle: 'Passage breakdown',
        sampleDescription: 'Processed text passages with attention, engagement, and memory scores.',
        sampleLabelPrefix: 'Passage sample',
        segmentFallbackPrefix: 'Passage',
        pendingSampleLabel: 'Passages will populate here once the result is ready.',
        unavailablePreviewLabel: 'Text analysis has no visual frame preview.',
        recommendationTimeLabel: 'Passage time',
        hookHelper: 'Lead passage clarity and pull',
      }
    case 'video':
    default:
      return {
        mediaType: 'video' as const,
        timelineTitle: 'Timeline chart',
        timelineDescription: 'Attention, engagement, and memory proxies aligned to processed timestamps.',
        segmentTitle: 'Scene / segment table',
        segmentDescription: 'Per-scene scoring across the processed video timeline.',
        matrixTitle: 'Multi-signal scene matrix',
        matrixDescription:
          'Per-scene breakdown across all 10 neural & behavioural signals. Cognitive Load is shown inverted (green = low load).',
        heatmapTitle: 'Attention heatmap overlays',
        heatmapDescription:
          'Brain plots are intentionally replaced with grid-based timestamp overlays derived from the processed timeline.',
        sampleTitle: 'Frame-by-frame breakdown',
        sampleDescription: 'Extracted frames at each analysis timestamp with attention zone and scene data.',
        sampleLabelPrefix: 'Frame',
        segmentFallbackPrefix: 'Scene',
        pendingSampleLabel: 'Extracted frame previews will populate here once the analysis result is ready.',
        unavailablePreviewLabel: 'Preview unavailable',
        recommendationTimeLabel: 'Scene time',
        hookHelper: 'Opening 3-second hold strength',
      }
  }
}

export function buildFrameBreakdownItems({
  timelinePoints,
  segmentsRows,
  heatmapFrames,
  mediaType = 'video',
}: {
  timelinePoints: AnalysisTimelinePoint[]
  segmentsRows: AnalysisSegmentRow[]
  heatmapFrames: AnalysisHeatmapFrame[]
  mediaType?: MediaType
}): AnalysisFrameBreakdownItem[] {
  const heatmapFrameByTimestamp = new Map(heatmapFrames.map((frame) => [frame.timestamp_ms, frame]))
  const presentation = getAnalysisResultPresentation(mediaType)

  return timelinePoints.map((point, index) => {
    const matchingSegment =
      segmentsRows[index] ??
      segmentsRows.find((segment) => point.timestamp_ms >= segment.start_time_ms && point.timestamp_ms <= segment.end_time_ms) ??
      [...segmentsRows].reverse().find((segment) => segment.start_time_ms <= point.timestamp_ms)
    const matchingHeatmapFrame = heatmapFrameByTimestamp.get(point.timestamp_ms)

    return {
      timestamp_ms: point.timestamp_ms,
      label: `${presentation.sampleLabelPrefix} ${index + 1}`,
      scene_label:
        matchingSegment?.label ??
        matchingHeatmapFrame?.scene_label ??
        `${presentation.segmentFallbackPrefix} ${String(index + 1).padStart(2, '0')}`,
      strongest_zone: matchingHeatmapFrame?.strongest_zone ?? null,
      attention_score: point.attention_score,
      engagement_score: point.engagement_score,
      memory_proxy: point.memory_proxy,
    }
  })
}

export function canExtractVideoFrames(mimeType: string | null | undefined) {
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

export async function generateFrameThumbnailMap({
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

export function resolveThumbnailSeekTime({
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

export function waitForVideoEvent(
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

export function resolveCurrentStage(
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

export function resolveVisibleProgressState(
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

export function resolveAnalysisStageAvailability({
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

export function resolveResultState({
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

export function stageRows(currentStage: string) {
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
      label: 'Structure ready',
      detail: 'Timeline segments and signal scaffolding are ready while scoring continues.',
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

export function buildScenePendingMessage(stageAvailability: {
  sceneStructureReady: boolean
  primaryScoringReady: boolean
  recommendationsReady: boolean
}, currentStage: string) {
  if (['idle', 'validating', 'uploading', 'uploaded'].includes(currentStage)) {
    return 'Start analysis to populate timeline segments and signal scaffolding.'
  }
  if (stageAvailability.sceneStructureReady) {
    return 'Timeline structure is complete. Attention and engagement scores are still being computed.'
  }
  return 'Timeline segments and signal scaffolding will appear after inference finishes the first structure pass.'
}

export function buildScoringPendingMessage(stageAvailability: {
  sceneStructureReady: boolean
  primaryScoringReady: boolean
  recommendationsReady: boolean
}, currentStage: string) {
  if (['idle', 'validating', 'uploading', 'uploaded'].includes(currentStage)) {
    return 'Start analysis to unlock scored attention, memory, and cognitive-load metrics.'
  }
  if (stageAvailability.sceneStructureReady) {
    return 'Timeline structure is complete. Primary scoring is filling in attention, memory, and cognitive-load metrics now.'
  }
  return 'Primary metrics unlock after the first structure pass completes.'
}

export function buildRecommendationsPendingMessage(stageAvailability: {
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
  return 'Recommendations appear after structure extraction, scoring, and post-processing finish.'
}

export function buildSeriesPath(
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

export function ensureTextFilename(value: string) {
  const sanitized = value.trim() || 'analysis-notes.txt'
  const lastSegment = sanitized.split(/[\\/]/).pop() || sanitized
  return /\.[A-Za-z0-9]{1,10}$/.test(lastSegment) ? sanitized : `${sanitized}.txt`
}

export function buildTextUploadAccept(mimeTypes: string[]) {
  return [...new Set([...mimeTypes, ...TEXT_DOCUMENT_EXTENSIONS])].join(',')
}

export function resolveUploadMimeType(file: File) {
  if (file.type) {
    return file.type
  }

  const extension = resolveFileExtension(file.name)
  return extension ? TEXT_DOCUMENT_MIME_BY_EXTENSION[extension] || '' : ''
}

export function resolveFileExtension(filename: string) {
  const lastDotIndex = filename.lastIndexOf('.')
  if (lastDotIndex === -1) {
    return ''
  }
  return filename.slice(lastDotIndex).toLowerCase()
}

export function shortenId(value: string) {
  return `${value.slice(0, 8)}…`
}

export function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value
  }
  return `${value.slice(0, maxLength - 1).trimEnd()}…`
}

export function formatDuration(milliseconds: number) {
  const totalSeconds = Math.floor(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function formatFileSize(sizeInBytes: number) {
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

export function formatOptionalScore(value: number | null | undefined) {
  if (value == null) {
    return '--'
  }
  return `${Math.round(value)}%`
}

export function formatSignedValue(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
}

export function formatZoneLabel(value: string) {
  return value.replaceAll('_', ' ')
}

export function readableGoalTemplate(value: string) {
  const match = defaultGoalTemplateOptions.find((option) => option.value === value)
  return match?.label || value.replaceAll('_', ' ')
}

export function readableChannel(value: string) {
  const match = defaultChannelOptions.find((option) => option.value === value)
  return match?.label || value.replaceAll('_', ' ')
}

export function formatTimestamp(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export function calculateElapsedMs(startValue: string | null | undefined, endValue: string | null | undefined) {
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

export function normalizeAnalysisProgressState(
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

export function areAnalysisJobsEqual(current: AnalysisJob | null, next: AnalysisJob | null) {
  return JSON.stringify(current) === JSON.stringify(next)
}

export function areAnalysisResultsEqual(current: AnalysisResult | null, next: AnalysisResult | null) {
  return JSON.stringify(current) === JSON.stringify(next)
}

export function areAnalysisProgressStatesEqual(current: AnalysisProgressState | null, next: AnalysisProgressState | null) {
  return JSON.stringify(current) === JSON.stringify(next)
}

export function readableProgressStage(value: string | null | undefined) {
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

export function reconnectAttemptLabel(count: number) {
  return `${count} reconnect attempt${count === 1 ? '' : 's'}`
}