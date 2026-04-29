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
    <Box className="compare-asset-list">
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
    <Box className={`compare-asset-row ${selected ? 'is-selected' : ''}`}>
      <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
        <Box className="compare-asset-thumb">{item.asset?.media_type?.slice(0, 1).toUpperCase() || 'A'}</Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack spacing={0.5}>
            <Typography sx={{ wordBreak: 'break-word' }} variant="subtitle2">
              {resolveAnalysisLabel(item)}
            </Typography>
            <Typography color="text.secondary" variant="body2">
              {formatTimestamp(item.job.created_at)}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {isBaseline ? <Chip color="primary" label="Baseline" size="small" variant="outlined" /> : null}
              {item.job.goal_template ? (
                <Chip label={readableGoalTemplate(item.job.goal_template)} size="small" variant="outlined" />
              ) : null}
              {item.job.channel ? <Chip label={readableChannel(item.job.channel)} size="small" variant="outlined" /> : null}
              <Chip label={item.asset?.media_type || 'analysis'} size="small" variant="outlined" />
            </Stack>
            <Typography color="text.secondary" variant="body2">
              {truncateText(item.job.objective || 'No objective stored.', 84)}
            </Typography>
          </Stack>
        </Box>

        <Stack alignItems={{ xs: 'stretch', sm: 'flex-end' }} spacing={1}>
          <Button onClick={handleToggle} size="small" variant={selected ? 'contained' : 'outlined'}>
            {selected ? 'Selected' : 'Add'}
          </Button>
          <Button disabled={!selected} onClick={handleBaseline} size="small" variant="text">
            Baseline
          </Button>
        </Stack>
      </Stack>
    </Box>
  )
}

const CompareCandidateRow = memo(CompareCandidateRowBase)
const CompareCandidateList = memo(CompareCandidateListBase)
export default CompareCandidateList
