import type { Dispatch, SetStateAction } from 'react'
import {
  placeholderHeatmapFrames,
  placeholderMetrics,
  placeholderSegments,
  placeholderSummary,
  placeholderTimeline,
} from './constants'
import type {
  AnalysisJob,
  AnalysisResult,
  AnalysisSummary,
  AnalysisProgressState,
  BannerMessage,
  UploadState,
} from './types'

export function scoreToColor(score: number): string {
  const clamped = Math.max(0, Math.min(100, score))
  const hue = (clamped / 100) * 120
  return `hsl(${Math.round(hue)}, 70%, 45%)`
}

export function normalizeAnalysisResultForRender(result: AnalysisResult | null): AnalysisResult | null {
  if (!result) {
    return null
  }

  const resultWithUnknownShape = result as AnalysisResult & {
    summary_json?: AnalysisSummary | null
    metrics_json?: AnalysisResult['metrics_json'] | null
    timeline_json?: AnalysisResult['timeline_json'] | null
    segments_json?: AnalysisResult['segments_json'] | null
    visualizations_json?: Partial<AnalysisResult['visualizations_json']> | null
    recommendations_json?: AnalysisResult['recommendations_json'] | null
  }
  const summary = resultWithUnknownShape.summary_json ?? placeholderSummary
  const metrics = Array.isArray(resultWithUnknownShape.metrics_json)
    ? resultWithUnknownShape.metrics_json
    : placeholderMetrics
  const visualizations = resultWithUnknownShape.visualizations_json ?? {}
  const normalizedSummary: AnalysisSummary = {
    ...placeholderSummary,
    ...summary,
    metadata: {
      ...placeholderSummary.metadata,
      ...(summary.metadata ?? {}),
    },
  }

  normalizedSummary.overall_attention_score = resolveSummaryScore(
    summary,
    metrics,
    'overall_attention_score',
    ['overall_attention', 'attention', 'attention_score'],
  )
  normalizedSummary.hook_score_first_3_seconds = resolveSummaryScore(
    summary,
    metrics,
    'hook_score_first_3_seconds',
    ['hook_score', 'hook', 'opening_attention_score'],
  )
  normalizedSummary.sustained_engagement_score = resolveSummaryScore(
    summary,
    metrics,
    'sustained_engagement_score',
    ['engagement', 'engagement_score', 'sustained_engagement'],
  )
  normalizedSummary.memory_proxy_score = resolveSummaryScore(
    summary,
    metrics,
    'memory_proxy_score',
    ['memory_proxy', 'memory', 'memory_score'],
  )
  normalizedSummary.cognitive_load_proxy = resolveSummaryScore(
    summary,
    metrics,
    'cognitive_load_proxy',
    ['cognitive_load', 'load', 'cognitive_load_score'],
  )
  const useVideoPlaceholders = normalizedSummary.modality === 'video'

  return {
    ...result,
    summary_json: normalizedSummary,
    metrics_json: metrics,
    timeline_json: Array.isArray(resultWithUnknownShape.timeline_json)
      ? resultWithUnknownShape.timeline_json
      : useVideoPlaceholders ? placeholderTimeline : [],
    segments_json: Array.isArray(resultWithUnknownShape.segments_json)
      ? resultWithUnknownShape.segments_json
      : useVideoPlaceholders ? placeholderSegments : [],
    visualizations_json: {
      visualization_mode: visualizations.visualization_mode ?? 'grid',
      heatmap_frames: Array.isArray(visualizations.heatmap_frames)
        ? visualizations.heatmap_frames
        : useVideoPlaceholders ? placeholderHeatmapFrames : [],
      high_attention_intervals: Array.isArray(visualizations.high_attention_intervals)
        ? visualizations.high_attention_intervals
        : [],
      low_attention_intervals: Array.isArray(visualizations.low_attention_intervals)
        ? visualizations.low_attention_intervals
        : [],
      presentation: visualizations.presentation ?? null,
    },
    recommendations_json: Array.isArray(resultWithUnknownShape.recommendations_json)
      ? resultWithUnknownShape.recommendations_json
      : [],
  }
}

export function resolveSummaryScore(
  summary: AnalysisSummary,
  metrics: AnalysisResult['metrics_json'],
  key: keyof Pick<
    AnalysisSummary,
    | 'overall_attention_score'
    | 'hook_score_first_3_seconds'
    | 'sustained_engagement_score'
    | 'memory_proxy_score'
    | 'cognitive_load_proxy'
  >,
  aliases: string[],
): number {
  const directValue = coerceScoreValue(summary[key])
  if (directValue !== null) {
    return directValue
  }

  const normalizedAliases = new Set([key, ...aliases].map(normalizeMetricKey))
  const metricMatch = metrics.find((metric) => normalizedAliases.has(normalizeMetricKey(metric.key)))
  const metricValue = coerceScoreValue(metricMatch?.value)
  if (metricValue !== null) {
    return metricValue
  }

  return placeholderSummary[key]
}

export function normalizeMetricKey(value: string): string {
  return value.toLowerCase().replaceAll(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
}

export function coerceScoreValue(value: unknown): number | null {
  if (typeof value !== 'number' && typeof value !== 'string') {
    return null
  }

  const numericValue = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numericValue)) {
    return null
  }

  return numericValue > 0 && numericValue <= 1 ? numericValue * 100 : numericValue
}

export function resetWorkflowState(
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
