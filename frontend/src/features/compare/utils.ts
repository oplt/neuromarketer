import type {
  AnalysisComparison,
  AnalysisComparisonHistoryItem,
  AnalysisComparisonItem,
  AnalysisJobListItem,
} from './types'

export function resolveAnalysisLabel(item: AnalysisJobListItem): string {
  return item.asset?.original_filename || item.job.objective || `Analysis ${item.job.id.slice(0, 8)}`
}

export function resolveComparisonItemLabel(item: AnalysisComparisonItem): string {
  return item.asset?.original_filename || item.job.objective || `Analysis ${item.analysis_job_id.slice(0, 8)}`
}

export function findComparisonItemLabel(items: AnalysisComparisonItem[], analysisJobId: string): string {
  return resolveComparisonItemLabel(items.find((item) => item.analysis_job_id === analysisJobId) || items[0])
}

export function buildHistoryItemFromComparison(comparison: AnalysisComparison): AnalysisComparisonHistoryItem {
  return {
    id: comparison.id,
    name: comparison.name,
    created_at: comparison.created_at,
    winning_analysis_job_id: comparison.winning_analysis_job_id || null,
    baseline_job_id: comparison.baseline_job_id || null,
    candidate_count: comparison.items.length,
    summary_json: comparison.summary_json,
    item_labels: comparison.items.map((item) => resolveComparisonItemLabel(item)),
  }
}

export function resolveComparisonLabel(comparison: AnalysisComparison): string {
  const winner = comparison.items.find((item) => item.analysis_job_id === comparison.winning_analysis_job_id)
  return winner ? resolveComparisonItemLabel(winner) : comparison.name
}

export function readableGoalTemplate(value: string): string {
  return value.replaceAll('_', ' ')
}

export function readableChannel(value: string): string {
  return value.replaceAll('_', ' ')
}

export function readableMetric(value: string): string {
  return value.replaceAll('_', ' ')
}

export function formatTimestamp(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export function truncateText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value
  }
  return `${value.slice(0, maxLength - 1).trimEnd()}…`
}

export function formatNumber(value: number | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--'
  }
  return value.toFixed(1)
}

export function formatSignedNumber(value: number | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
}

export function scoreToColor(score: number): string {
  const clamped = Math.max(0, Math.min(100, score))
  const hue = (clamped / 100) * 120
  return `hsl(${Math.round(hue)}, 70%, 45%)`
}
