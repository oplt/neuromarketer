import { Box, Chip, Paper, Skeleton, Stack, Typography } from '@mui/material'
import { memo, useMemo } from 'react'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import { resolveComparisonItemLabel, scoreToColor } from '../utils'
import type { AnalysisComparisonItem } from '../types'

type ScoreGaugeProps = {
  isReady: boolean
  label: string
  size?: number
  value: number
}

function ScoreGauge({ isReady, label, size = 68, value }: ScoreGaugeProps) {
  const strokeWidth = 6
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const filled = (Math.max(0, Math.min(100, value)) / 100) * circumference
  const color = scoreToColor(value)

  return (
    <Box sx={{ alignItems: 'center', display: 'flex', flexDirection: 'column', gap: 0.5 }}>
      <Box sx={{ height: size, position: 'relative', width: size }}>
        <svg
          aria-hidden="true"
          height={size}
          style={{ transform: 'rotate(-90deg)' }}
          viewBox={`0 0 ${size} ${size}`}
          width={size}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            fill="none"
            r={radius}
            stroke="rgba(24,34,48,0.08)"
            strokeWidth={strokeWidth}
          />
          {isReady && (
            <circle
              cx={size / 2}
              cy={size / 2}
              fill="none"
              r={radius}
              stroke={color}
              strokeDasharray={`${filled} ${circumference}`}
              strokeLinecap="round"
              strokeWidth={strokeWidth}
            />
          )}
        </svg>
        <Box sx={{ alignItems: 'center', display: 'flex', inset: 0, justifyContent: 'center', position: 'absolute' }}>
          {isReady ? (
            <Typography sx={{ color, fontSize: 13, fontWeight: 700, lineHeight: 1 }}>
              {Math.round(value)}
            </Typography>
          ) : (
            <Skeleton height={16} sx={{ transform: 'none' }} width={26} />
          )}
        </Box>
      </Box>
      <Typography
        color="text.secondary"
        sx={{ lineHeight: 1.2, maxWidth: size, textAlign: 'center' }}
        variant="caption"
      >
        {label}
      </Typography>
    </Box>
  )
}

type ScoreGaugesComparisonProps = {
  items: AnalysisComparisonItem[]
}

const METRICS: Array<{ key: string; label: string }> = [
  { key: 'overall_attention', label: 'Attention' },
  { key: 'hook', label: 'Hook' },
  { key: 'sustained_engagement', label: 'Sustained' },
  { key: 'memory_proxy', label: 'Memory' },
  { key: 'low_cognitive_load', label: 'Low Load' },
]

function ScoreGaugesComparisonBase({ items }: ScoreGaugesComparisonProps) {
  const columnCount = useMemo(() => Math.min(items.length, 4), [items.length])

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems="center" direction="row" spacing={0.5}>
          <Typography variant="h6">Score profiles</Typography>
          <HelpTooltip title="Green ≥ 70, amber ≥ 40, red below threshold." />
        </Stack>
        <Box
          sx={{
            display: 'grid',
            gap: 3,
            gridTemplateColumns: `repeat(${columnCount}, 1fr)`,
          }}
        >
          {items.map((item) => (
            <Box key={item.analysis_job_id}>
              <Stack spacing={0.75} sx={{ mb: 2 }}>
                <Typography variant="subtitle2">{resolveComparisonItemLabel(item)}</Typography>
                {item.is_winner && (
                  <Chip color="success" label="Winner" size="small" sx={{ alignSelf: 'flex-start' }} variant="outlined" />
                )}
                {item.is_baseline && !item.is_winner && (
                  <Chip color="primary" label="Baseline" size="small" sx={{ alignSelf: 'flex-start' }} variant="outlined" />
                )}
              </Stack>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                {METRICS.map(({ key, label }) => (
                  <ScoreGauge key={key} isReady label={label} value={item.scores_json[key] ?? 0} />
                ))}
              </Box>
            </Box>
          ))}
        </Box>
      </Stack>
    </Paper>
  )
}

const ScoreGaugesComparison = memo(ScoreGaugesComparisonBase)
export default ScoreGaugesComparison
