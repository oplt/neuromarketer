import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { Chip } from '@mui/material'
import { Box, Paper, Stack, Tooltip, Typography } from '@mui/material'
import { RadarChart } from '@mui/x-charts/RadarChart'
import { memo, useMemo, useState } from 'react'

type MetricRow = {
  key: string
  label: string
  value: number
  unit: string
  detail?: string | null
  confidence?: number | null
  source?: string
}

type MetricsRadarSeries = {
  label: string
  metrics: MetricRow[]
}

type MetricsRadarCardProps = {
  title: string
  description: string
  series: MetricsRadarSeries[]
  emptyMessage?: string
  testId?: string
}

type RadarMetricDefinition = {
  key: string
  label: string
  max: number
}

function formatRadarAxisLabel(label: string) {
  const normalized = label.replace(' /100', '').trim()
  const words = normalized.split(/\s+/).filter(Boolean)
  if (words.length <= 2) {
    return normalized
  }

  const lines: string[] = []
  for (let index = 0; index < words.length; index += 2) {
    lines.push(words.slice(index, index + 2).join(' '))
  }
  return lines.join('\n')
}

function buildRadarMetrics(series: MetricsRadarSeries[]): RadarMetricDefinition[] {
  const orderedKeys: string[] = []
  const metricMeta = new Map<string, { label: string; unit: string }>()

  for (const item of series) {
    for (const metric of item.metrics) {
      if (!orderedKeys.includes(metric.key)) {
        orderedKeys.push(metric.key)
      }
      if (!metricMeta.has(metric.key)) {
        metricMeta.set(metric.key, { label: metric.label, unit: metric.unit })
      }
    }
  }

  return orderedKeys.map((key) => {
    const meta = metricMeta.get(key) ?? { label: key, unit: '' }
    const maxValue = Math.max(
      ...series.map((item) => item.metrics.find((metric) => metric.key === key)?.value ?? 0),
      0,
    )

    return {
      key,
      label: meta.unit ? `${meta.label} ${meta.unit}` : meta.label,
      max: resolveRadarMax(maxValue, meta.unit),
    }
  })
}

function resolveRadarMax(value: number, unit: string) {
  if (!Number.isFinite(value) || value <= 0) {
    return 1
  }
  if (unit === '/100' || unit === '%') {
    return 100
  }
  if (value <= 1) {
    return 1
  }
  if (value <= 10) {
    return Math.ceil(value)
  }
  if (value <= 100) {
    return Math.ceil(value / 10) * 10
  }
  return Math.ceil(value / 25) * 25
}

function formatMetricValue(metric: MetricRow) {
  const suffix = metric.unit ? ` ${metric.unit}` : ''
  return `${metric.value.toFixed(metric.unit === 'seconds' ? 2 : 1)}${suffix}`
}

function formatConfidence(confidence: number | null | undefined) {
  if (confidence == null || Number.isNaN(confidence)) {
    return 'n/a'
  }
  return confidence.toFixed(2)
}

function MetricsRadarCard({
  title,
  description,
  series,
  emptyMessage = 'Radar visualization appears when at least three metrics are available.',
  testId,
}: MetricsRadarCardProps) {
  const radarMetrics = useMemo(() => buildRadarMetrics(series), [series])
  const hasEnoughMetrics = radarMetrics.length >= 3
  const chartHeight = series.length > 1 ? 280 : 250
  const [highlightedMetricIndex, setHighlightedMetricIndex] = useState<number>(0)

  const chartSeries = useMemo(
    () =>
      series.map((item) => ({
        label: series.length > 1 ? item.label : undefined,
        data: radarMetrics.map(
          (metric) => item.metrics.find((entry) => entry.key === metric.key)?.value ?? 0,
        ),
        fillArea: series.length === 1,
      })),
    [series, radarMetrics],
  )

  const chartRadar = useMemo(
    () => ({
      metrics: radarMetrics.map((metric) => ({
        name: formatRadarAxisLabel(metric.label),
        max: metric.max,
      })),
    }),
    [radarMetrics],
  )

  const primarySeriesMetrics = series[0]?.metrics ?? []
  const selectedMetricKey = radarMetrics[highlightedMetricIndex]?.key
  const selectedMetric =
    primarySeriesMetrics.find((metric) => metric.key === selectedMetricKey) ??
    primarySeriesMetrics[0] ??
    null

  return (
    <Paper className="dashboard-card" data-testid={testId} elevation={0}>
      <Stack spacing={1.25}>
        <Stack alignItems="center" direction="row" spacing={0.75}>
          <Typography variant="h6">{title}</Typography>
          <Tooltip arrow placement="top" title={description}>
            <InfoOutlinedIcon
              aria-label={`${title} description`}
              fontSize="small"
              sx={{ color: 'text.secondary', cursor: 'help' }}
              tabIndex={0}
            />
          </Tooltip>
        </Stack>

        {hasEnoughMetrics ? (
          <Box sx={{ height: chartHeight, width: '100%' }}>
            <RadarChart
              height={chartHeight}
              onHighlightChange={(highlight) => {
                const axisIndex =
                  typeof highlight?.dataIndex === 'number'
                    ? highlight.dataIndex
                    : null
                if (axisIndex == null || axisIndex < 0 || axisIndex >= radarMetrics.length) {
                  return
                }
                setHighlightedMetricIndex(axisIndex)
              }}
              series={chartSeries}
              radar={chartRadar}
              slotProps={{ tooltip: { trigger: 'none' } }}
            />
          </Box>
        ) : null}

        {hasEnoughMetrics && selectedMetric ? (
          <Box
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
                  {selectedMetric.label}
                </Typography>
                <Typography color="text.secondary" sx={{ lineHeight: 1.4, mt: 0.35 }} variant="caption">
                  {selectedMetric.detail || 'Directional model signal. Calibrate with campaign outcomes before treating it as proof.'}
                </Typography>
              </Box>
              <Typography sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} variant="subtitle2">
                {formatMetricValue(selectedMetric)}
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
                label={`Confidence ${formatConfidence(selectedMetric.confidence)}`}
                size="small"
                variant="outlined"
              />
              {selectedMetric.source ? <Chip label={selectedMetric.source} size="small" variant="outlined" /> : null}
            </Stack>
          </Box>
        ) : (
          <Box className="analysis-empty-state">
            <Typography color="text.secondary" variant="body2">
              {emptyMessage}
            </Typography>
          </Box>
        )}
      </Stack>
    </Paper>
  )
}

export default memo(MetricsRadarCard)
