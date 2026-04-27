import { Box, Button, Chip, Paper, Stack, Typography } from '@mui/material'
import { memo, useCallback } from 'react'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import { formatTimestamp, truncateText } from '../utils'
import type { AnalysisComparisonHistoryItem } from '../types'
import ComparisonEmptyState from './ComparisonEmptyState'

type ComparisonHistoryPanelProps = {
  activeComparisonId: string | null
  comparisonLoadingId: string | null
  history: AnalysisComparisonHistoryItem[]
  isLoading: boolean
  onOpenComparison: (comparisonId: string) => void
  onRefresh: () => void
}

function ComparisonHistoryPanelBase({
  activeComparisonId,
  comparisonLoadingId,
  history,
  isLoading,
  onOpenComparison,
  onRefresh,
}: ComparisonHistoryPanelProps) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack
          alignItems={{ xs: 'stretch', md: 'center' }}
          direction={{ xs: 'column', md: 'row' }}
          justifyContent="space-between"
          spacing={1.5}
        >
          <Stack alignItems="center" direction="row" spacing={0.5}>
            <Typography variant="h6">Saved comparisons</Typography>
            <HelpTooltip title="Reopen earlier winner calls without leaving the workspace." />
          </Stack>
          <Button onClick={onRefresh} size="small" variant="text">
            Refresh
          </Button>
        </Stack>

        {isLoading ? <ComparisonEmptyState message="Loading compare history…" /> : null}

        {!isLoading && history.length === 0 ? (
          <ComparisonEmptyState message="No saved comparisons yet. Create one from the completed analysis list to start building decision history." />
        ) : null}

        {history.length > 0 ? (
          <Box className="analysis-job-history" data-testid="compare-history-list">
            {history.map((item) => (
              <ComparisonHistoryRow
                activeComparisonId={activeComparisonId}
                comparisonLoadingId={comparisonLoadingId}
                item={item}
                key={item.id}
                onOpenComparison={onOpenComparison}
              />
            ))}
          </Box>
        ) : null}
      </Stack>
    </Paper>
  )
}

type ComparisonHistoryRowProps = {
  activeComparisonId: string | null
  comparisonLoadingId: string | null
  item: AnalysisComparisonHistoryItem
  onOpenComparison: (comparisonId: string) => void
}

function ComparisonHistoryRowBase({
  activeComparisonId,
  comparisonLoadingId,
  item,
  onOpenComparison,
}: ComparisonHistoryRowProps) {
  const handleOpen = useCallback(() => onOpenComparison(item.id), [item.id, onOpenComparison])
  const isActive = activeComparisonId === item.id
  const isLoadingThis = comparisonLoadingId === item.id

  return (
    <Box className={`analysis-job-history__item ${isActive ? 'is-selected' : ''}`}>
      <Stack spacing={1.25}>
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5}>
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ wordBreak: 'break-word' }} variant="subtitle2">
              {item.name}
            </Typography>
            <Typography color="text.secondary" variant="body2">
              {formatTimestamp(item.created_at)}
            </Typography>
          </Box>
          <Chip
            color="primary"
            label={isLoadingThis ? 'Loading' : `${item.candidate_count} items`}
            size="small"
            variant="outlined"
          />
        </Stack>
        <Typography color="text.secondary" variant="body2">
          {truncateText(item.item_labels.join(' • '), 120)}
        </Typography>
        <Button onClick={handleOpen} size="small" variant="outlined">
          Open comparison
        </Button>
      </Stack>
    </Box>
  )
}

const ComparisonHistoryRow = memo(ComparisonHistoryRowBase)
const ComparisonHistoryPanel = memo(ComparisonHistoryPanelBase)
export default ComparisonHistoryPanel
