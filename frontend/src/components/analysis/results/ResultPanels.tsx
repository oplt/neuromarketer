import AutoGraphRounded from '@mui/icons-material/AutoGraphRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { useEffect, useRef, useState, type ChangeEvent } from 'react'

import { apiFetch, apiRequest } from '../../../lib/api'
import type {
  AnalysisAsset,
  AnalysisBenchmarkResponse,
  AnalysisCalibrationResponse,
  AnalysisExecutiveVerdict,
  AnalysisFrameBreakdownItem,
  AnalysisHeatmapFrame,
  AnalysisInterval,
  AnalysisJob,
  AnalysisRecommendation,
  AnalysisSegmentRow,
  AnalysisSummary,
  AnalysisTimelinePoint,
  AnalysisTransportDiagnostics,
  AnalysisProgressState,
  MediaType,
  SummaryCard,
} from '../../../features/analysis/types'
import {
  buildSeriesPath,
  calculateElapsedMs,
  canExtractVideoFrames,
  formatDuration,
  formatOptionalScore,
  formatTimestamp,
  formatZoneLabel,
  generateFrameThumbnailMap,
  getAnalysisResultPresentation,
  readableProgressStage,
  reconnectAttemptLabel,
} from '../../../features/analysis/utils'
import { scoreToColor } from '../../../features/analysis/resultRendering'
import DetailRow from '../shared/DetailRow'
import LegendSwatch from '../shared/LegendSwatch'

export function AnalysisTransportDiagnosticsCard({
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

export function ExecutiveVerdictCard({
  benchmark,
  benchmarkError,
  calibration,
  executiveVerdict,
  executiveVerdictError,
  recommendations,
  summary,
  isLoadingBenchmark,
  isLoadingExecutiveVerdict,
  hasResults,
}: {
  benchmark: AnalysisBenchmarkResponse | null
  benchmarkError: string | null
  calibration: AnalysisCalibrationResponse | null
  executiveVerdict: AnalysisExecutiveVerdict | null
  executiveVerdictError: string | null
  recommendations: AnalysisRecommendation[]
  summary: AnalysisSummary
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

  const fallbackAverage =
    (summary.overall_attention_score +
      summary.hook_score_first_3_seconds +
      summary.sustained_engagement_score +
      summary.memory_proxy_score +
      (100 - summary.cognitive_load_proxy)) /
    5
  const fallbackStatus = fallbackAverage >= 72 ? 'ship' : fallbackAverage >= 55 ? 'iterate' : 'high_risk'
  const status = executiveVerdict?.status ?? fallbackStatus
  const verdictLabel = status === 'ship' ? 'Ship' : status === 'iterate' ? 'Fix' : 'Kill'
  const verdictTone = status === 'ship' ? 'success' : status === 'high_risk' ? 'error' : 'warning'
  const benchmarkAverage =
    executiveVerdict?.benchmark_average_percentile ??
    (benchmark?.metrics.length
      ? benchmark.metrics.reduce((total, metric) => total + metric.percentile, 0) / benchmark.metrics.length
      : null)
  const calibrationCount = calibration?.summary.observation_count ?? 0
  const topRisks =
    executiveVerdict?.top_risks?.slice(0, 3) ??
    recommendations
      .filter((recommendation) => recommendation.priority !== 'low')
      .slice(0, 3)
      .map((recommendation) => recommendation.title)
  const topStrengths =
    executiveVerdict?.top_strengths?.slice(0, 2) ??
    [
      `Attention ${Math.round(summary.overall_attention_score)}/100`,
      `Memory ${Math.round(summary.memory_proxy_score)}/100`,
    ]
  const topActions =
    executiveVerdict?.recommended_actions?.slice(0, 3) ??
    recommendations.slice(0, 3).map((recommendation) =>
      recommendation.timestamp_ms != null
        ? `${formatDuration(recommendation.timestamp_ms)}: ${recommendation.title}`
        : recommendation.title,
    )

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ xs: 'stretch', md: 'center' }} direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography color="text.secondary" variant="overline">
              Decision
            </Typography>
            <Typography variant="h4">
              {executiveVerdict?.headline || `${verdictLabel} this creative with caution`}
            </Typography>
            <Typography color="text.secondary" variant="body2">
              {executiveVerdict?.summary ||
                'Directional model output. Import outcome data before treating this as calibrated performance proof.'}
            </Typography>
          </Box>
          <Chip color={verdictTone} label={verdictLabel} size="medium" sx={{ alignSelf: { xs: 'flex-start', md: 'center' }, fontWeight: 800 }} />
        </Stack>
        {isLoadingBenchmark || isLoadingExecutiveVerdict ? <LinearProgress sx={{ borderRadius: 999, height: 8 }} /> : null}
        {benchmarkError ? <Alert severity="warning">{benchmarkError}</Alert> : null}
        {executiveVerdictError ? <Alert severity="warning">{executiveVerdictError}</Alert> : null}
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Chip
            icon={<AutoGraphRounded />}
            label={benchmarkAverage != null ? `Benchmark avg ${Math.round(benchmarkAverage)}th percentile` : 'Benchmark pending'}
            size="small"
            variant="outlined"
          />
          {benchmark ? <Chip label={`${benchmark.cohort_size} peer runs`} size="small" variant="outlined" /> : null}
          <Chip
            color={calibrationCount > 0 ? 'success' : 'warning'}
            label={calibrationCount > 0 ? `${calibrationCount} outcome observations` : 'Directional, not calibrated'}
            size="small"
            variant="outlined"
          />
          <Chip label={`Confidence ${formatOptionalScore(summary.confidence)}`} size="small" variant="outlined" />
        </Stack>

        <Box className="dashboard-grid dashboard-grid--content">
          <Box className="analysis-inline-summary">
            <Typography variant="subtitle2">Why</Typography>
            <Stack spacing={0.75}>
              {[...topStrengths, ...topRisks].slice(0, 3).map((item) => (
                <Typography color="text.secondary" key={item} variant="body2">
                  {item}
                </Typography>
              ))}
            </Stack>
          </Box>
          <Box className="analysis-inline-summary">
            <Typography variant="subtitle2">Fix first</Typography>
            <Stack spacing={0.75}>
              {topActions.length > 0 ? (
                topActions.map((item) => (
                  <Typography color="text.secondary" key={item} variant="body2">
                    {item}
                  </Typography>
                ))
              ) : (
                <Typography color="text.secondary" variant="body2">
                  Review weak scenes and import outcomes before scaling spend.
                </Typography>
              )}
            </Stack>
          </Box>
        </Box>
      </Stack>
    </Paper>
  )
}

export function BenchmarkPercentilesCard({
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

export function CalibrationPanel({
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

export function ResultStateBanner({
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
        `/api/v1/analysis/jobs/${analysisJob.id}/rerun`,
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

export function SignalSummaryCard({
  cards,
  isReady,
  loadingLabel,
}: {
  cards: SummaryCard[]
  isReady: boolean
  loadingLabel: string
}) {
  const strongestCard = cards.reduce((best, card) => (card.value > best.value ? card : best), cards[0])
  const weakestCard = cards.reduce((worst, card) => (card.value < worst.value ? card : worst), cards[0])
  const baselineCount = cards.filter((card) => Math.round(card.value) === 50).length

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Box>
          <Typography variant="h6">Signal summary</Typography>
          <Typography color="text.secondary" variant="body2">
            Core scores as comparable bars. Baseline-heavy runs are called out instead of hidden inside a radar.
          </Typography>
        </Box>

        {isReady ? (
          <Stack spacing={1.25}>
            {cards.map((card) => {
              const value = Math.max(0, Math.min(100, card.value))
              return (
                <Box key={card.key}>
                  <Stack direction="row" justifyContent="space-between" spacing={1.5}>
                    <Typography variant="subtitle2">{card.label}</Typography>
                    <Typography color="text.secondary" variant="body2">
                      {Math.round(value)}/100 · {scoreBandLabel(value)}
                    </Typography>
                  </Stack>
                  <Box
                    aria-label={`${card.label} score ${Math.round(value)} out of 100`}
                    className="analysis-score-bar"
                    role="img"
                  >
                    <Box
                      className="analysis-score-bar__fill"
                      sx={{
                        bgcolor: scoreToColor(value),
                        width: `${value}%`,
                      }}
                    />
                  </Box>
                  <Typography color="text.secondary" variant="caption">
                    {card.helper}
                  </Typography>
                </Box>
              )
            })}
          </Stack>
        ) : (
          <Stack spacing={1.25}>
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={`signal-summary-skeleton-${index}`} height={42} sx={{ transform: 'none' }} variant="rounded" />
            ))}
            <Typography color="text.secondary" variant="body2">
              {loadingLabel}
            </Typography>
          </Stack>
        )}

        {isReady ? (
          <Box className="analysis-empty-state">
            <Typography variant="subtitle2">
              Strongest: {strongestCard.label} · Weakest: {weakestCard.label}
            </Typography>
            <Typography color="text.secondary" variant="body2">
              {baselineCount >= 3
                ? `${baselineCount} signals are sitting at 50/100, so treat them as neutral baseline until more evidence is available.`
                : 'Use the weakest bar to choose which creative moment to inspect next.'}
            </Typography>
          </Box>
        ) : null}
      </Stack>
    </Paper>
  )
}

function scoreBandLabel(value: number) {
  if (value < 45) {
    return 'weak'
  }
  if (value <= 70) {
    return 'watch'
  }
  return 'strong'
}

export function TimelineChart({
  points,
  segments,
  highAttentionIntervals,
  lowAttentionIntervals,
}: {
  points: AnalysisTimelinePoint[]
  segments: AnalysisSegmentRow[]
  highAttentionIntervals?: AnalysisInterval[]
  lowAttentionIntervals?: AnalysisInterval[]
}) {
  const width = 520
  const height = 200
  const engagementPath = buildSeriesPath(points, width, height, 'engagement_score')
  const attentionPath = buildSeriesPath(points, width, height, 'attention_score')
  const memoryPath = buildSeriesPath(points, width, height, 'memory_proxy')
  const scoreTicks = [100, 50, 0]
  const visibleSegmentBoundaries = segments
    .filter((segment) => segment.start_time_ms > 0)
    .slice(0, 18)

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
        {scoreTicks.map((score) => {
          const y = height - (score / 100) * (height - 12) - 6
          return (
            <g key={`score-tick-${score}`}>
              <path className="analysis-timeline-chart__grid" d={`M 0 ${y} H ${width}`} />
              <text className="analysis-timeline-chart__axis-label" x={4} y={Math.max(12, y - 4)}>
                {score}
              </text>
            </g>
          )
        })}
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
        {visibleSegmentBoundaries.map((segment) => {
          const x = intervalToX(segment.start_time_ms)
          return (
            <path
              className="analysis-timeline-chart__segment"
              d={`M ${x} 8 V ${height - 8}`}
              key={`${segment.label}-${segment.start_time_ms}`}
            />
          )
        })}
        <path className="analysis-timeline-chart__line analysis-timeline-chart__line--engagement" d={engagementPath} />
        <path className="analysis-timeline-chart__line analysis-timeline-chart__line--attention" d={attentionPath} />
        <path className="analysis-timeline-chart__line analysis-timeline-chart__line--memory" d={memoryPath} />
        {points.map((point, index) => {
          if (index % Math.max(1, Math.ceil(points.length / 8)) !== 0) {
            return null
          }
          const x = intervalToX(point.timestamp_ms)
          const y = height - (Math.max(0, Math.min(100, point.engagement_score)) / 100) * (height - 12) - 6
          return (
            <circle
              className="analysis-timeline-chart__point"
              cx={x}
              cy={y}
              key={`engagement-point-${point.timestamp_ms}`}
              r={3.5}
            />
          )
        })}
      </svg>
      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        <LegendSwatch color="#f97316" label="Engagement" />
        <LegendSwatch color="#3b5bdb" label="Attention" />
        <LegendSwatch color="#14b8a6" label="Memory Proxy" />
        {visibleSegmentBoundaries.length > 0 && <LegendSwatch color="#94a3b8" label="Scene boundary" />}
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

export function TimelineChartSkeleton({ label }: { label: string }) {
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

type KeyMomentFrame = {
  frame: AnalysisFrameBreakdownItem
  reason: string
}

function buildKeyMomentFrames(frames: AnalysisFrameBreakdownItem[]): KeyMomentFrame[] {
  if (frames.length === 0) {
    return []
  }

  const candidates: KeyMomentFrame[] = [
    { frame: frames[0], reason: 'Opening moment' },
    { frame: maxByScore(frames, 'engagement_score'), reason: 'Peak engagement' },
    { frame: minByScore(frames, 'attention_score'), reason: 'Weakest attention' },
    { frame: maxByScore(frames, 'memory_proxy'), reason: 'Memory peak' },
  ]

  const seenTimestamps = new Set<number>()
  return candidates
    .filter((candidate) => {
      if (seenTimestamps.has(candidate.frame.timestamp_ms)) {
        return false
      }
      seenTimestamps.add(candidate.frame.timestamp_ms)
      return true
    })
    .slice(0, 4)
}

function maxByScore(
  frames: AnalysisFrameBreakdownItem[],
  key: keyof Pick<AnalysisFrameBreakdownItem, 'attention_score' | 'engagement_score' | 'memory_proxy'>,
) {
  return frames.reduce((best, frame) => (frame[key] > best[key] ? frame : best), frames[0])
}

function minByScore(
  frames: AnalysisFrameBreakdownItem[],
  key: keyof Pick<AnalysisFrameBreakdownItem, 'attention_score' | 'engagement_score' | 'memory_proxy'>,
) {
  return frames.reduce((worst, frame) => (frame[key] < worst[key] ? frame : worst), frames[0])
}

export function VideoFrameStrip({
  frames,
  hasResults,
  isScoringReady,
  asset,
  presentation,
  sessionToken,
}: {
  frames: AnalysisFrameBreakdownItem[]
  hasResults: boolean
  isScoringReady: boolean
  asset: AnalysisAsset | null
  presentation: ReturnType<typeof getAnalysisResultPresentation>
  sessionToken: string | null
}) {
  const [frameThumbnails, setFrameThumbnails] = useState<Record<number, string>>({})
  const [thumbnailAspectRatio, setThumbnailAspectRatio] = useState('16 / 9')
  const [thumbnailState, setThumbnailState] = useState<'idle' | 'loading' | 'ready' | 'failed'>('idle')
  const keyMoments = buildKeyMomentFrames(frames)
  const keyMomentFrames = keyMoments.map((moment) => moment.frame)
  const frameTimestampsKey = keyMomentFrames.map((frame) => frame.timestamp_ms).join(',')
  const thumbnailCacheRef = useRef(
    new Map<string, { previewsByTimestamp: Record<number, string>; aspectRatio: string }>(),
  )

  useEffect(() => {
    let isCancelled = false

    if (!hasResults || !asset || asset.media_type !== 'video' || !sessionToken || keyMomentFrames.length === 0) {
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
          frames: keyMomentFrames,
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
    // `keyMomentFrames` intentionally excluded: its identity changes on every parent render, but `frameTimestampsKey`
    // is its stable content hash. Including `frames` aborts the in-flight thumbnail fetch on every re-render,
    // so the cache never populates and the images never appear.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset?.id, asset?.media_type, asset?.mime_type, frameTimestampsKey, hasResults, sessionToken])

  if (!hasResults) {
    return (
      <Box className="analysis-frame-strip" data-testid="frame-breakdown-strip">
        <Typography color="text.secondary" sx={{ mb: 1.5 }} variant="body2">
          {presentation.pendingSampleLabel}
        </Typography>
        <Box className="analysis-frame-grid">
          {Array.from({ length: 3 }).map((_, i) => (
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

  if (asset?.media_type !== 'video') {
    return (
      <Box
        aria-label={`${presentation.sampleTitle} list`}
        className="analysis-frame-strip"
        data-testid="frame-breakdown-strip"
      >
        <Box className="analysis-frame-grid">
          {keyMoments.map(({ frame, reason }) => (
            <Box
              className="analysis-frame-card"
              data-testid={`frame-breakdown-card-${frame.timestamp_ms}`}
              key={frame.timestamp_ms}
            >
              <Stack spacing={0.75}>
                <Typography color="text.secondary" variant="caption">
                  {formatDuration(frame.timestamp_ms)}
                </Typography>
                <Typography variant="subtitle2">{frame.scene_label || frame.label}</Typography>
                <Chip label={reason} size="small" color="primary" variant="outlined" />
                <Chip label={presentation.unavailablePreviewLabel} size="small" variant="outlined" />
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
          ))}
        </Box>
      </Box>
    )
  }

  return (
    <Box
      aria-label="Frame-by-frame breakdown"
      className="analysis-frame-strip"
      data-testid="frame-breakdown-strip"
    >
      <Box className="analysis-frame-grid">
        {keyMoments.map(({ frame, reason }) => {
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
                      {thumbnailState === 'loading' ? 'Loading frame...' : presentation.unavailablePreviewLabel}
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
                <Chip label={reason} size="small" color="primary" variant="outlined" />
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

export function MinimalModalityResults({
  asset,
  heatmapFrames,
  highAttentionIntervals,
  lowAttentionIntervals,
  isReady,
  loadingLabel,
  mediaType,
  recommendations,
  segments,
  summary,
  timelinePoints,
}: {
  asset: AnalysisAsset | null
  heatmapFrames: AnalysisHeatmapFrame[]
  highAttentionIntervals: AnalysisInterval[]
  lowAttentionIntervals: AnalysisInterval[]
  isReady: boolean
  loadingLabel: string
  mediaType: MediaType
  recommendations: AnalysisRecommendation[]
  segments: AnalysisSegmentRow[]
  summary: AnalysisSummary
  timelinePoints: AnalysisTimelinePoint[]
}) {
  const isText = mediaType === 'text'
  const documentKind = resolveDocumentKind(asset)
  const orderedSegments = [...segments].sort((left, right) => {
    const leftScore = isReady ? left.attention_score + left.memory_proxy - left.cognitive_load : left.segment_index
    const rightScore = isReady ? right.attention_score + right.memory_proxy - right.cognitive_load : right.segment_index
    return isReady ? rightScore - leftScore : leftScore - rightScore
  })
  const topSections = orderedSegments.slice(0, 4)
  const weakSections = [...segments]
    .sort((left, right) => left.attention_score - right.attention_score)
    .slice(0, 3)
  const heatmapByTimestamp = new Map(heatmapFrames.map((frame) => [frame.timestamp_ms, frame]))
  const intervalCopy = isText
    ? 'For PDF/DOC uploads, page-level scoring appears when the extractor provides page-aware sections. Otherwise, these cards use passage windows as page proxies.'
    : 'Audio results are grouped by time window, focused on pacing, memory, attention, and load rather than visual context.'

  return (
    <Stack spacing={3}>
      <Paper className="dashboard-card analysis-modality-card" elevation={0}>
        <Stack spacing={2.25}>
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.5}>
            <Box>
              <Typography color="text.secondary" variant="overline">
                {isText ? `${documentKind} analysis` : 'Audio analysis'}
              </Typography>
              <Typography variant="h5">
                {isText ? 'Minimal document results' : 'Minimal audio results'}
              </Typography>
              <Typography color="text.secondary" variant="body2">
                {intervalCopy}
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip label={`${segments.length} ${isText ? 'sections' : 'audio windows'}`} variant="outlined" />
              <Chip label={`Confidence ${formatOptionalScore(summary.confidence)}`} variant="outlined" />
              <Chip label={`Coverage ${formatOptionalScore(summary.completeness)}`} variant="outlined" />
            </Stack>
          </Stack>

          <Box className="analysis-document-grid">
            {isReady ? (
              topSections.map((segment, index) => (
                <SectionScoreCard
                  heatmapFrame={heatmapByTimestamp.get(segment.start_time_ms) ?? heatmapFrames[index] ?? null}
                  isText={isText}
                  key={`${segment.label}-${segment.start_time_ms}`}
                  rank={index + 1}
                  segment={segment}
                />
              ))
            ) : (
              Array.from({ length: 4 }).map((_, index) => (
                <Box className="analysis-document-card" key={`document-section-skeleton-${index}`}>
                  <Skeleton height={24} sx={{ transform: 'none' }} width="48%" />
                  <Skeleton height={76} sx={{ transform: 'none' }} variant="rounded" />
                  <Skeleton height={18} sx={{ transform: 'none' }} width="84%" />
                </Box>
              ))
            )}
          </Box>
        </Stack>
      </Paper>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">{isText ? 'Page / passage signal map' : 'Audio window signal map'}</Typography>
            <Typography color="text.secondary" variant="body2">
              {isText
                ? 'If the upload preserves page context, section labels can be treated as page-level evidence. Visual-grid scores are shown only when the backend emits them for that section.'
                : 'Scores are aligned to audio windows. No frame or page preview is expected for audio assets.'}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{isText ? 'Section' : 'Audio window'}</TableCell>
                  <TableCell>{isText ? 'Page / passage context' : 'Time window'}</TableCell>
                  <TableCell align="right">Attention</TableCell>
                  <TableCell align="right">Memory</TableCell>
                  <TableCell align="right">Load</TableCell>
                  <TableCell>Evidence</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {isReady
                  ? segments.map((segment, index) => {
                      const heatmapFrame = heatmapByTimestamp.get(segment.start_time_ms) ?? heatmapFrames[index] ?? null
                      return (
                        <TableRow key={`${segment.label}-${segment.start_time_ms}`}>
                          <TableCell>{segment.label}</TableCell>
                          <TableCell>
                            {isText
                              ? resolveTextSectionContext(segment, index)
                              : `${formatDuration(segment.start_time_ms)} - ${formatDuration(segment.end_time_ms)}`}
                          </TableCell>
                          <TableCell align="right">{Math.round(segment.attention_score)}</TableCell>
                          <TableCell align="right">{Math.round(segment.memory_proxy)}</TableCell>
                          <TableCell align="right">{Math.round(segment.cognitive_load)}</TableCell>
                          <TableCell>
                            {heatmapFrame
                              ? `${heatmapFrame.caption || 'Visual/context grid available'} ${heatmapFrame.strongest_zone ? `Strongest: ${formatZoneLabel(heatmapFrame.strongest_zone)}.` : ''}`
                              : segment.note || 'No section-specific visual context emitted for this result.'}
                          </TableCell>
                        </TableRow>
                      )
                    })
                  : Array.from({ length: 4 }).map((_, index) => (
                      <TableRow key={`modality-row-skeleton-${index}`}>
                        <TableCell><Skeleton height={22} sx={{ transform: 'none' }} width="70%" /></TableCell>
                        <TableCell><Skeleton height={22} sx={{ transform: 'none' }} width="80%" /></TableCell>
                        <TableCell align="right"><Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={40} /></TableCell>
                        <TableCell align="right"><Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={40} /></TableCell>
                        <TableCell align="right"><Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={40} /></TableCell>
                        <TableCell><Skeleton height={22} sx={{ transform: 'none' }} width="90%" /></TableCell>
                      </TableRow>
                    ))}
              </TableBody>
            </Table>
            {!isReady ? (
              <Typography color="text.secondary" variant="body2">
                {loadingLabel}
              </Typography>
            ) : null}
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">{isText ? 'Fix these sections first' : 'Fix these audio windows first'}</Typography>
            <Stack spacing={1.2}>
              {weakSections.length ? (
                weakSections.map((segment) => (
                  <Box className="analysis-section-risk" key={`${segment.label}-${segment.end_time_ms}`}>
                    <Stack spacing={0.5}>
                      <Typography variant="subtitle2">{segment.label}</Typography>
                      <Typography color="text.secondary" variant="body2">
                        {isText
                          ? segment.note || 'Low attention section; simplify or strengthen the value proof.'
                          : `${formatDuration(segment.start_time_ms)} - ${formatDuration(segment.end_time_ms)} needs pacing or clarity improvement.`}
                      </Typography>
                    </Stack>
                    <Chip color="warning" label={`${Math.round(segment.attention_score)}/100`} size="small" />
                  </Box>
                ))
              ) : (
                <Typography color="text.secondary" variant="body2">
                  No weak sections were detected yet.
                </Typography>
              )}
            </Stack>
          </Stack>
        </Paper>
      </Box>

      {timelinePoints.length > 0 && (highAttentionIntervals.length > 0 || lowAttentionIntervals.length > 0 || recommendations.length > 0) ? null : (
        <Alert severity="info">
          This {isText ? 'document' : 'audio'} result uses modality-specific scoring. Video-only frame previews and spatial heatmaps are intentionally hidden.
        </Alert>
      )}
    </Stack>
  )
}

function SectionScoreCard({
  heatmapFrame,
  isText,
  rank,
  segment,
}: {
  heatmapFrame: AnalysisHeatmapFrame | null
  isText: boolean
  rank: number
  segment: AnalysisSegmentRow
}) {
  return (
    <Box className="analysis-document-card">
      <Stack spacing={1.5}>
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1}>
          <Typography color="text.secondary" variant="overline">
            {isText ? `Section ${rank}` : `Window ${rank}`}
          </Typography>
          <Chip label={segment.label} size="small" variant="outlined" />
        </Stack>
        <Typography variant="subtitle1">
          {isText ? resolveTextSectionContext(segment, rank - 1) : `${formatDuration(segment.start_time_ms)} - ${formatDuration(segment.end_time_ms)}`}
        </Typography>
        <Box className="analysis-document-card__scores">
          <MiniScore label="Attention" value={segment.attention_score} />
          <MiniScore label="Memory" value={segment.memory_proxy} />
          <MiniScore label="Load" value={segment.cognitive_load} invert />
        </Box>
        <Typography color="text.secondary" variant="body2">
          {heatmapFrame
            ? heatmapFrame.caption || 'Context-specific signal grid is available for this section.'
            : segment.note || 'No visual context emitted for this section; using sequence-level scoring.'}
        </Typography>
      </Stack>
    </Box>
  )
}

function MiniScore({ invert = false, label, value }: { invert?: boolean; label: string; value: number }) {
  const normalized = Math.max(0, Math.min(100, value))
  const color = scoreToColor(invert ? 100 - normalized : normalized)
  return (
    <Box>
      <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1}>
        <Typography color="text.secondary" variant="caption">
          {label}
        </Typography>
        <Typography variant="caption">{Math.round(normalized)}</Typography>
      </Stack>
      <Box className="analysis-mini-score">
        <Box sx={{ bgcolor: color, width: `${normalized}%` }} />
      </Box>
    </Box>
  )
}

function resolveDocumentKind(asset: AnalysisAsset | null) {
  const fileName = (asset?.original_filename || asset?.object_key || '').toLowerCase()
  const mimeType = (asset?.mime_type || '').toLowerCase()
  if (fileName.endsWith('.pdf') || mimeType.includes('pdf')) {
    return 'PDF'
  }
  if (/\.(doc|docx|odt|rtf)$/.test(fileName) || mimeType.includes('word') || mimeType.includes('document')) {
    return 'Document'
  }
  return 'Text'
}

function resolveTextSectionContext(segment: AnalysisSegmentRow, index: number) {
  const explicitPage = /page\s+\d+/i.exec(`${segment.label} ${segment.note}`)?.[0]
  if (explicitPage) {
    return explicitPage
  }
  return `Passage ${index + 1}`
}

export function AttentionIntervalsCard({
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

export function RecommendationsCard({
  recommendations,
  hasResults,
  isPartial,
  isReady,
  loadingLabel,
  recommendationTimeLabel,
  summary,
}: {
  recommendations: AnalysisRecommendation[]
  hasResults: boolean
  isPartial: boolean
  isReady: boolean
  loadingLabel: string
  recommendationTimeLabel: string
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
          <Stack alignItems={{ xs: 'flex-start', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
            <Box>
              <Typography color="text.secondary" variant="caption">
                {recommendation.timestamp_ms != null
                  ? `${recommendationTimeLabel} ${formatDuration(recommendation.timestamp_ms)}`
                  : 'Whole creative'}
              </Typography>
              <Typography variant="subtitle2">{recommendation.title}</Typography>
            </Box>
            <Chip
              className={`analysis-priority-chip analysis-priority-chip--${recommendation.priority}`}
              label={recommendation.priority}
              size="small"
              variant="outlined"
            />
          </Stack>
          <Typography color="text.secondary" variant="body2">
            Edit: {recommendation.detail}
          </Typography>
          <Stack direction="row" spacing={1.5} useFlexGap flexWrap="wrap">
            <Typography color="text.secondary" variant="caption">
              Confidence {formatOptionalScore(recommendation.confidence)}
            </Typography>
            <Typography color="text.secondary" variant="caption">
              Expected effect: improve the weakest decision signal before comparing variants.
            </Typography>
          </Stack>
        </Box>
      ))}
    </Stack>
  )
}

export function SegmentHeatstrip({
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
  const strongestSegment = segments.reduce((best, segment) =>
    segment.attention_score > best.attention_score ? segment : best,
  )
  const weakestSegment = segments.reduce((worst, segment) =>
    segment.attention_score < worst.attention_score ? segment : worst,
  )

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
                minWidth: 18,
                '&:hover': { filter: 'brightness(1.2)' },
              }}
            />
          )
        })}
      </Box>
      <Stack direction="row" spacing={2}>
        <LegendSwatch color="hsl(0,70%,45%)" label="Weak <45" />
        <LegendSwatch color="hsl(60,70%,45%)" label="Watch 45-70" />
        <LegendSwatch color="hsl(120,70%,45%)" label="Strong >70" />
      </Stack>
      <Typography color="text.secondary" variant="caption">
        Weakest: {weakestSegment.label} ({Math.round(weakestSegment.attention_score)}/100). Strongest:{' '}
        {strongestSegment.label} ({Math.round(strongestSegment.attention_score)}/100).
      </Typography>
    </Stack>
  )
}

const SIGNAL_COLUMNS: { key: keyof AnalysisSegmentRow; label: string; invert?: boolean }[] = [
  { key: 'attention_score', label: 'Attention' },
  { key: 'engagement_score', label: 'Engagement' },
  { key: 'memory_proxy', label: 'Memory' },
  { key: 'cognitive_load', label: 'Load', invert: true },
  { key: 'conversion_proxy', label: 'Conversion' },
]

export function SignalMatrixCard({
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

  const sortedSegments = [...segments]
    .sort((a, b) => signalRiskScore(b) - signalRiskScore(a))
    .slice(0, 12)

  return (
    <Stack spacing={1.5}>
      <Box className="analysis-signal-matrix__header">
        <Typography color="text.secondary" variant="caption">
          Segment
        </Typography>
        {SIGNAL_COLUMNS.map((col) => (
          <Box
            key={col.key as string}
            sx={{ textAlign: 'center' }}
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

      {sortedSegments.map((seg) => (
        <Box className="analysis-signal-matrix__row" key={seg.segment_index}>
          <Box sx={{ minWidth: 0 }}>
            <Typography noWrap variant="caption">
              {seg.label}
            </Typography>
            <Typography color="text.secondary" noWrap variant="caption">
              {formatDuration(seg.start_time_ms)} - {formatDuration(seg.end_time_ms)}
            </Typography>
          </Box>

          {SIGNAL_COLUMNS.map((col) => {
            const raw = ((seg[col.key] as number | undefined) ?? 0)
            const hasData = (seg[col.key] as number | undefined) !== undefined
            const displayScore = col.invert ? 100 - raw : raw
            const color = hasData ? scoreToColor(displayScore) : 'rgba(128,128,128,0.15)'
            return (
              <Box
                aria-label={hasData ? `${seg.label} ${col.label} ${Math.round(raw)} out of 100` : `${seg.label} ${col.label} no data`}
                className="analysis-signal-matrix__cell"
                key={col.key as string}
                role="img"
                title={hasData ? `${seg.label} · ${col.label}: ${Math.round(raw)}/100` : `${seg.label} · ${col.label}: no data (re-run analysis)`}
                sx={{
                  bgcolor: color,
                }}
              />
            )
          })}
        </Box>
      ))}

      <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
        <LegendSwatch color="hsl(0,70%,45%)" label="Low" />
        <LegendSwatch color="hsl(60,70%,45%)" label="Mid" />
        <LegendSwatch color="hsl(120,70%,45%)" label="High" />
        <Typography color="text.secondary" variant="caption" sx={{ ml: 1, alignSelf: 'center' }}>
          * Cognitive Load is inverted (high = bad)
        </Typography>
      </Stack>
    </Stack>
  )
}

function signalRiskScore(segment: AnalysisSegmentRow) {
  return (
    (100 - segment.attention_score) * 0.35 +
    (100 - segment.engagement_score) * 0.25 +
    (100 - segment.memory_proxy) * 0.15 +
    segment.cognitive_load * 0.15 +
    (100 - segment.conversion_proxy) * 0.1
  )
}
