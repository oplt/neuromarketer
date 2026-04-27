import { Box, Paper, Stack, Typography } from '@mui/material'
import { memo } from 'react'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import { resolveComparisonItemLabel, scoreToColor } from '../utils'
import type { AnalysisComparisonItem, AnalysisSegmentRow } from '../types'

type CompareSegmentHeatstripProps = {
  label?: string
  segments: AnalysisSegmentRow[]
  stripHeight?: number
}

function CompareSegmentHeatstrip({ label: stripLabel, segments, stripHeight = 28 }: CompareSegmentHeatstripProps) {
  if (segments.length === 0) return null
  const totalDuration = segments.reduce((max, s) => Math.max(max, s.end_time_ms), 0) || 1

  return (
    <Stack spacing={0.5}>
      {stripLabel && (
        <Typography color="text.secondary" variant="caption">
          {stripLabel}
        </Typography>
      )}
      <Box
        aria-label={`${stripLabel ?? 'Segment'} attention heatstrip`}
        role="img"
        sx={{
          borderRadius: '6px',
          display: 'flex',
          gap: '2px',
          height: stripHeight,
          overflow: 'hidden',
        }}
      >
        {segments.map((seg, i) => {
          const widthPct = ((seg.end_time_ms - seg.start_time_ms) / totalDuration) * 100
          return (
            <Box
              key={i}
              title={`${seg.label}: ${Math.round(seg.attention_score)}/100`}
              sx={{
                '&:hover': { filter: 'brightness(1.2)' },
                bgcolor: scoreToColor(seg.attention_score),
                cursor: 'default',
                flex: `0 0 ${widthPct}%`,
                transition: 'filter 0.15s',
              }}
            />
          )
        })}
      </Box>
    </Stack>
  )
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <Stack alignItems="center" direction="row" spacing={0.75}>
      <Box sx={{ bgcolor: color, borderRadius: '50%', flexShrink: 0, height: 10, width: 10 }} />
      <Typography color="text.secondary" variant="caption">
        {label}
      </Typography>
    </Stack>
  )
}

type CompareHeatstripCardProps = {
  baseline: AnalysisComparisonItem | null
  challenger: AnalysisComparisonItem
}

function CompareHeatstripCardBase({ baseline, challenger }: CompareHeatstripCardProps) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={1.5}>
        <Stack alignItems="center" direction="row" spacing={0.5}>
          <Typography variant="subtitle1">Attention heatstrip</Typography>
          <HelpTooltip title="Each band represents one segment colored by attention. Red = low, green = high." />
        </Stack>
        {baseline && (
          <CompareSegmentHeatstrip
            label={`Baseline: ${resolveComparisonItemLabel(baseline)}`}
            segments={baseline.result.segments_json}
          />
        )}
        <CompareSegmentHeatstrip
          label={`Challenger: ${resolveComparisonItemLabel(challenger)}`}
          segments={challenger.result.segments_json}
        />
        <Stack direction="row" spacing={2}>
          <LegendSwatch color="hsl(0,70%,45%)" label="Low" />
          <LegendSwatch color="hsl(60,70%,45%)" label="Mid" />
          <LegendSwatch color="hsl(120,70%,45%)" label="High" />
        </Stack>
      </Stack>
    </Paper>
  )
}

const CompareHeatstripCard = memo(CompareHeatstripCardBase)
export default CompareHeatstripCard
