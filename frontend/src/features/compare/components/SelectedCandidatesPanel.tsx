import { Box, Button, Chip, Stack, Typography } from '@mui/material'
import { memo, useCallback } from 'react'
import { resolveAnalysisLabel, truncateText } from '../utils'
import type { AnalysisJobListItem } from '../types'
import ComparisonEmptyState from './ComparisonEmptyState'

type SelectedCandidatesPanelProps = {
  baselineJobId: string | null
  items: AnalysisJobListItem[]
  onRemove: (item: AnalysisJobListItem) => void
  onSetBaseline: (jobId: string) => void
}

function SelectedCandidatesPanelBase({
  baselineJobId,
  items,
  onRemove,
  onSetBaseline,
}: SelectedCandidatesPanelProps) {
  if (items.length === 0) {
    return <ComparisonEmptyState message="No analyses selected yet. Add completed runs below to build a side-by-side review." />
  }

  return (
    <Box className="compare-selected-grid">
      {items.map((item) => (
        <SelectedCandidateCard
          baselineJobId={baselineJobId}
          item={item}
          key={item.job.id}
          onRemove={onRemove}
          onSetBaseline={onSetBaseline}
        />
      ))}
    </Box>
  )
}

type SelectedCandidateCardProps = {
  baselineJobId: string | null
  item: AnalysisJobListItem
  onRemove: (item: AnalysisJobListItem) => void
  onSetBaseline: (jobId: string) => void
}

function SelectedCandidateCardBase({
  baselineJobId,
  item,
  onRemove,
  onSetBaseline,
}: SelectedCandidateCardProps) {
  const isBaseline = baselineJobId === item.job.id
  const handleRemove = useCallback(() => onRemove(item), [item, onRemove])
  const handleSetBaseline = useCallback(() => onSetBaseline(item.job.id), [item.job.id, onSetBaseline])

  return (
    <Box className={`compare-selected-card ${isBaseline ? 'is-baseline' : ''}`}>
      <Stack spacing={1.25}>
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5}>
          <Typography variant="subtitle2">{resolveAnalysisLabel(item)}</Typography>
          {isBaseline ? <Chip color="primary" label="Baseline" size="small" variant="outlined" /> : null}
        </Stack>
        <Typography color="text.secondary" variant="body2">
          {truncateText(item.job.objective || 'No objective stored.', 92)}
        </Typography>
        <Stack direction="row" spacing={1}>
          <Button onClick={handleSetBaseline} size="small" variant="text">
            Baseline
          </Button>
          <Button onClick={handleRemove} size="small" variant="outlined">
            Remove
          </Button>
        </Stack>
      </Stack>
    </Box>
  )
}

const SelectedCandidateCard = memo(SelectedCandidateCardBase)
const SelectedCandidatesPanel = memo(SelectedCandidatesPanelBase)
export default SelectedCandidatesPanel
