import PlayCircleRounded from '@mui/icons-material/PlayCircleRounded'
import TuneRounded from '@mui/icons-material/TuneRounded'
import { Alert, Box, Button, Paper, Stack, Typography } from '@mui/material'
import type { ReactNode } from 'react'
import type { AnalysisAsset, AnalysisJob, AnalysisProgressState, MediaType } from '../../features/analysis/types'
import { readableChannel, readableGoalTemplate, stageRows } from '../../features/analysis/utils'
import DetailRow from './shared/DetailRow'

type ReviewRunStepProps = {
  analysisJob: AnalysisJob | null
  canStartAnalysis: boolean
  channel: string
  goalTemplate: string
  goalValidationErrors: string[]
  onBack: () => void
  onStartAnalysis: () => void
  selectedAsset?: AnalysisAsset
  selectedMediaType: MediaType
}

export function ReviewRunStep({
  analysisJob,
  canStartAnalysis,
  channel,
  goalTemplate,
  goalValidationErrors,
  onBack,
  onStartAnalysis,
  selectedAsset,
  selectedMediaType,
}: ReviewRunStepProps) {
  const disabledReason = !selectedAsset
    ? 'Select or upload media first.'
    : goalValidationErrors.length > 0
      ? goalValidationErrors.join(' ')
      : ''

  return (
    <Paper className="dashboard-card analyze-step-card" elevation={0}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5">Review & run</Typography>
          <Typography color="text.secondary" variant="body2">Confirm the setup before starting analysis.</Typography>
        </Box>
        <Box className="analysis-review-summary">
          <DetailRow label="Selected asset" value={selectedAsset?.original_filename || selectedAsset?.object_key || 'No asset selected'} />
          <DetailRow label="Goal" value={goalTemplate ? readableGoalTemplate(goalTemplate) : 'Not specified'} />
          <DetailRow label="Channel" value={channel ? readableChannel(channel) : 'Not specified'} />
          <DetailRow label="Analysis stages" value={`${selectedMediaType} intake, processing, scoring, recommendations`} />
        </Box>
        {disabledReason ? <Alert severity="warning">{disabledReason}</Alert> : null}
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Button onClick={onBack} variant="outlined">Back</Button>
          <Button disabled={!canStartAnalysis} onClick={onStartAnalysis} size="large" startIcon={<PlayCircleRounded />} variant="contained">
            {analysisJob?.status === 'failed' ? 'Retry analysis' : 'Start analysis'}
          </Button>
        </Stack>
      </Stack>
    </Paper>
  )
}

type ProcessingStatusProps = {
  analysisJob: AnalysisJob | null
  currentStage: string
  isRunning: boolean
  onBack: () => void
  onOpenDetails: () => void
  progress: AnalysisProgressState | null
  resultState: 'empty' | 'loading' | 'partial' | 'ready' | 'failed'
}

export function ProcessingStatus({
  analysisJob,
  currentStage,
  isRunning,
  onBack,
  onOpenDetails,
  progress,
  resultState,
}: ProcessingStatusProps) {
  const stages = ['Uploading', 'Processing', 'Scoring', 'Recommendations', 'Done']
  const activeIndex = resultState === 'ready'
    ? stages.length - 1
    : Math.min(Math.max(stageRows(currentStage).findIndex((row) => row.isActive), 0) + 1, stages.length - 2)

  return (
    <Paper className="dashboard-card analyze-step-card" elevation={0}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5">{analysisJob?.status === 'failed' ? 'Analysis failed' : 'Analysis in progress'}</Typography>
          <Typography color="text.secondary" variant="body2">
            {progress?.stageLabel || (isRunning ? 'We are processing the creative now.' : 'Waiting for worker updates.')}
          </Typography>
        </Box>
        <Box className="analysis-progress-track">
          {stages.map((stage, index) => (
            <Box className={`analysis-progress-track__item ${index <= activeIndex ? 'is-active' : ''}`.trim()} key={stage}>
              <span />
              <Typography variant="body2">{stage}</Typography>
            </Box>
          ))}
        </Box>
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Button onClick={onBack} variant="outlined">Back</Button>
          <Button onClick={onOpenDetails} startIcon={<TuneRounded />} variant="contained">View technical details</Button>
        </Stack>
      </Stack>
    </Paper>
  )
}

export function ResultsStep({ children }: { children: ReactNode }) {
  return (
    <Stack className="analysis-results-step" spacing={3}>
      <Box>
        <Typography variant="h5">Results</Typography>
        <Typography color="text.secondary" variant="body2">
          Score overview, scene observations, recommendations, and report actions.
        </Typography>
      </Box>
      {children}
    </Stack>
  )
}
