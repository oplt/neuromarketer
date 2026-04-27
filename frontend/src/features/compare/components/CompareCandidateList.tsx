import { Box, Button, Chip, Stack, Typography } from '@mui/material'
import { memo, useCallback } from 'react'
import { formatTimestamp, readableChannel, readableGoalTemplate, resolveAnalysisLabel, truncateText } from '../utils'
import type { AnalysisJobListItem } from '../types'
import ComparisonEmptyState from './ComparisonEmptyState'

type CompareCandidateListProps = {
  baselineJobId: string | null
  isLoading: boolean
  items: AnalysisJobListItem[]
  onSetBaseline: (jobId: string) => void
  onToggle: (item: AnalysisJobListItem) => void
  selectedJobIds: string[]
}

function CompareCandidateListBase({
  baselineJobId,
  isLoading,
  items,
  onSetBaseline,
  onToggle,
  selectedJobIds,
}: CompareCandidateListProps) {
  if (isLoading) {
    return <ComparisonEmptyState message="Loading completed analyses…" />
  }
  if (items.length === 0) {
    return (
      <ComparisonEmptyState message="No completed analyses are available yet. Finish at least two runs in Analysis before using compare." />
    )
  }

  return (
    <Box className="analysis-job-history">
      {items.map((item) => (
        <CompareCandidateRow
          baselineJobId={baselineJobId}
          item={item}
          key={item.job.id}
          onSetBaseline={onSetBaseline}
          onToggle={onToggle}
          selected={selectedJobIds.includes(item.job.id)}
        />
      ))}
    </Box>
  )
}

type CompareCandidateRowProps = {
  baselineJobId: string | null
  item: AnalysisJobListItem
  onSetBaseline: (jobId: string) => void
  onToggle: (item: AnalysisJobListItem) => void
  selected: boolean
}

function CompareCandidateRowBase({ baselineJobId, item, onSetBaseline, onToggle, selected }: CompareCandidateRowProps) {
  const handleToggle = useCallback(() => onToggle(item), [item, onToggle])
  const handleBaseline = useCallback(() => onSetBaseline(item.job.id), [item.job.id, onSetBaseline])
  const isBaseline = baselineJobId === item.job.id

  return (
    <Box className={`analysis-job-history__item ${selected ? 'is-selected' : ''}`}>
      <Stack spacing={1.25}>
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5}>
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ wordBreak: 'break-word' }} variant="subtitle2">
              {resolveAnalysisLabel(item)}
            </Typography>
            <Typography color="text.secondary" variant="body2">
              {formatTimestamp(item.job.created_at)}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            {isBaseline ? <Chip color="primary" label="Baseline" size="small" variant="outlined" /> : null}
            <Chip
              className={`analysis-status-chip is-${item.job.status}`}
              label={item.job.status}
              size="small"
              variant="outlined"
            />
          </Stack>
        </Stack>

        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          {item.job.goal_template ? (
            <Chip label={readableGoalTemplate(item.job.goal_template)} size="small" variant="outlined" />
          ) : null}
          {item.job.channel ? <Chip label={readableChannel(item.job.channel)} size="small" variant="outlined" /> : null}
          <Chip label={item.asset?.media_type || 'analysis'} size="small" variant="outlined" />
        </Stack>

        <Typography color="text.secondary" variant="body2">
          {truncateText(item.job.objective || 'No objective stored for this analysis.', 132)}
        </Typography>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button onClick={handleToggle} size="small" variant={selected ? 'contained' : 'outlined'}>
            {selected ? 'Selected' : 'Add to compare'}
          </Button>
          <Button disabled={!selected} onClick={handleBaseline} size="small" variant="text">
            Set as baseline
          </Button>
        </Stack>
      </Stack>
    </Box>
  )
}

const CompareCandidateRow = memo(CompareCandidateRowBase)
const CompareCandidateList = memo(CompareCandidateListBase)
export default CompareCandidateList
