export function formatTimestamp(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.floor(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function formatFileSize(sizeInBytes: number): string {
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

export function formatOptionalScore(value: number | null | undefined): string {
  if (value == null) {
    return '--'
  }
  return `${Math.round(value)}%`
}

export function formatSignedValue(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
}

export function formatZoneLabel(value: string): string {
  return value.replaceAll('_', ' ')
}

export function shortenId(value: string): string {
  return `${value.slice(0, 8)}…`
}

export function truncateText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value
  }
  return `${value.slice(0, maxLength - 1).trimEnd()}…`
}

export function calculateElapsedMs(
  startValue: string | null | undefined,
  endValue: string | null | undefined,
): number | null {
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

export function reconnectAttemptLabel(count: number): string {
  return `${count} reconnect attempt${count === 1 ? '' : 's'}`
}

export function readableProgressStage(value: string | null | undefined): string {
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
