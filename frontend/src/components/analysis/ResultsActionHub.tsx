import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded'
import CompareArrowsRounded from '@mui/icons-material/CompareArrowsRounded'
import DownloadRounded from '@mui/icons-material/DownloadRounded'
import { Box, Paper, Stack, Typography } from '@mui/material'
import type { AnalysisJob, AnalysisResult } from '../../features/analysis/types'
import ActionCard from './shared/ActionCard'

type ResultsActionHubProps = {
  analysisJob: AnalysisJob | null
  analysisResult: AnalysisResult | null
  compareCandidateCount: number
  generatedVariantCount: number
  isGeneratingVariants: boolean
  onCompare: () => void
  onExport: () => void
  onGenerate: () => void
}

export default function ResultsActionHub({
  analysisJob,
  analysisResult,
  compareCandidateCount,
  generatedVariantCount,
  isGeneratingVariants,
  onCompare,
  onExport,
  onGenerate,
}: ResultsActionHubProps) {
  const hasResults = Boolean(analysisJob && analysisResult)

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack spacing={0.5}>
          <Typography variant="h6">Step 3: Review and act</Typography>
          <Typography color="text.secondary" variant="body2">
            Compare, export, or generate variants from the current run.
          </Typography>
        </Stack>
        <Box className="analysis-action-grid">
          <ActionCard
            ctaLabel="Compare run"
            description={
              compareCandidateCount > 0
                ? `${compareCandidateCount} saved run${compareCandidateCount === 1 ? '' : 's'} ready for quick comparison.`
                : 'Add one more completed run to enable comparison.'
            }
            disabled={!hasResults || compareCandidateCount === 0}
            icon={<CompareArrowsRounded fontSize="small" />}
            label="Compare"
            onClick={onCompare}
            testId="analysis-action-compare"
          />
          <ActionCard
            ctaLabel="Export JSON"
            description="Download the active job, asset, and dashboard payload as a portable report package."
            disabled={!hasResults}
            icon={<DownloadRounded fontSize="small" />}
            label="Export"
            onClick={onExport}
            testId="analysis-action-export"
          />
          <ActionCard
            ctaLabel={
              isGeneratingVariants
                ? 'Generating…'
                : generatedVariantCount > 0
                  ? 'Regenerate variants'
                  : 'Generate variants'
            }
            description={
              generatedVariantCount > 0
                ? `${generatedVariantCount} saved variant${generatedVariantCount === 1 ? '' : 's'} ready for projected compare against the original.`
                : 'Generate hook, CTA, script, and thumbnail variants.'
            }
            disabled={!hasResults || isGeneratingVariants}
            icon={<AutoAwesomeRounded fontSize="small" />}
            label="Generate"
            onClick={onGenerate}
            testId="analysis-action-generate"
          />
        </Box>
      </Stack>
    </Paper>
  )
}
