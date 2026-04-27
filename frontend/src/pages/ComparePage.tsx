import CompareArrowsRounded from '@mui/icons-material/CompareArrowsRounded'
import HistoryRounded from '@mui/icons-material/HistoryRounded'
import LaunchRounded from '@mui/icons-material/LaunchRounded'
import SwapHorizRounded from '@mui/icons-material/SwapHorizRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Suspense, lazy, memo, useCallback, useEffect, useMemo, useState } from 'react'
import HelpTooltip from '../components/layout/HelpTooltip'
import {
  CompareCandidateList,
  ComparisonHistoryPanel,
  ComparisonResults,
  SelectedCandidatesPanel,
  cacheComparisonDetail,
  cacheComparisonHistoryEntry,
  resolveAnalysisLabel,
  resolveComparisonLabel,
  useComparisonCandidates,
  useComparisonDetail,
  useComparisonHistory,
  type AnalysisComparison,
  type AnalysisJobListItem,
  type CompareBanner,
} from '../features/compare'
import { buildHistoryItemFromComparison } from '../features/compare/utils'
import { apiRequest } from '../lib/api'
import {
  buildCompareWorkspaceStorageKey,
  readCompareWorkspaceSnapshot,
  storeCompareWorkspaceSnapshot,
} from '../lib/compareWorkspace'
import type { AuthSession } from '../lib/session'

const CollaborationPanel = lazy(() => import('../components/collaboration/CollaborationPanel'))

type ComparePageProps = {
  session: AuthSession
}

function ComparePage({ session }: ComparePageProps) {
  const sessionToken = session.sessionToken
  const storageScope = session.defaultProjectId || session.email
  const storageKey = useMemo(() => buildCompareWorkspaceStorageKey(storageScope), [storageScope])
  const storedSnapshot = useMemo(() => readCompareWorkspaceSnapshot(storageKey), [storageKey])

  const [selectedJobIds, setSelectedJobIds] = useState<string[]>(storedSnapshot.selectedJobIds)
  const [baselineJobId, setBaselineJobId] = useState<string | null>(storedSnapshot.baselineJobId)
  const [activeComparisonId, setActiveComparisonId] = useState<string | null>(
    storedSnapshot.activeComparisonId,
  )
  const [comparisonName, setComparisonName] = useState('')
  const [banner, setBanner] = useState<CompareBanner | null>(null)
  const [isCreatingComparison, setIsCreatingComparison] = useState(false)

  const handleError = useCallback((nextBanner: CompareBanner) => setBanner(nextBanner), [])

  const { analysisHistory, isLoading: isLoadingAnalyses } = useComparisonCandidates({
    sessionToken,
    onError: handleError,
  })

  const {
    comparisonHistory,
    isLoading: isLoadingComparisons,
    reload: reloadComparisonHistory,
    setComparisonHistory,
  } = useComparisonHistory({ sessionToken, onError: handleError })

  const { activeComparison, comparisonLoadingId, loadComparison, setActiveComparison } =
    useComparisonDetail({ sessionToken, onError: handleError })

  const completedAnalyses = useMemo(
    () => analysisHistory.filter((item) => item.has_result && item.job.status === 'completed'),
    [analysisHistory],
  )

  const selectedAnalyses = useMemo(
    () => completedAnalyses.filter((item) => selectedJobIds.includes(item.job.id)),
    [completedAnalyses, selectedJobIds],
  )

  const baselineCandidate = useMemo(
    () => selectedAnalyses.find((item) => item.job.id === baselineJobId) ?? selectedAnalyses[0] ?? null,
    [baselineJobId, selectedAnalyses],
  )

  useEffect(() => {
    storeCompareWorkspaceSnapshot(storageKey, {
      selectedJobIds,
      baselineJobId,
      activeComparisonId,
    })
  }, [activeComparisonId, baselineJobId, selectedJobIds, storageKey])

  useEffect(() => {
    if (!completedAnalyses.length) {
      return
    }
    setSelectedJobIds((current) => current.filter((jobId) => completedAnalyses.some((item) => item.job.id === jobId)))
    setBaselineJobId((current) => {
      if (current && completedAnalyses.some((item) => item.job.id === current)) {
        return current
      }
      const seededJobId =
        storedSnapshot.selectedJobIds.find((jobId) =>
          completedAnalyses.some((item) => item.job.id === jobId),
        ) || null
      return seededJobId
    })
  }, [completedAnalyses, storedSnapshot.selectedJobIds])

  useEffect(() => {
    if (!activeComparisonId || activeComparison?.id === activeComparisonId || !sessionToken) {
      return
    }
    void loadComparison(activeComparisonId)
  }, [activeComparison?.id, activeComparisonId, loadComparison, sessionToken])

  const applyActiveComparison = useCallback(
    (comparison: AnalysisComparison) => {
      setActiveComparison(comparison)
      setActiveComparisonId(comparison.id)
      setComparisonName(comparison.name)
      setSelectedJobIds(comparison.items.map((item) => item.analysis_job_id))
      setBaselineJobId(
        comparison.baseline_job_id ||
          comparison.items.find((item) => item.is_baseline)?.analysis_job_id ||
          null,
      )
    },
    [setActiveComparison],
  )

  const handleToggleAnalysis = useCallback((item: AnalysisJobListItem) => {
    if (!item.has_result || item.job.status !== 'completed') {
      return
    }

    setSelectedJobIds((current) => {
      if (current.includes(item.job.id)) {
        const nextSelection = current.filter((jobId) => jobId !== item.job.id)
        setBaselineJobId((currentBaseline) =>
          currentBaseline === item.job.id ? nextSelection[0] || null : currentBaseline,
        )
        return nextSelection
      }
      if (current.length >= 5) {
        setBanner({
          type: 'error',
          message: 'Compare workspace supports up to 5 completed analyses at a time.',
        })
        return current
      }
      const nextSelection = [...current, item.job.id]
      setBaselineJobId((currentBaseline) => currentBaseline || item.job.id)
      return nextSelection
    })
  }, [])

  const handleClearSelection = useCallback(() => {
    setSelectedJobIds([])
    setBaselineJobId(null)
    setActiveComparison(null)
    setActiveComparisonId(null)
  }, [setActiveComparison])

  const handleCreateComparison = useCallback(async () => {
    if (!sessionToken) {
      return
    }
    if (selectedJobIds.length < 2) {
      setBanner({
        type: 'error',
        message: 'Select at least 2 completed analyses before creating a comparison.',
      })
      return
    }

    setIsCreatingComparison(true)
    try {
      const comparison = await apiRequest<AnalysisComparison>('/api/v1/analysis/comparisons', {
        method: 'POST',
        sessionToken,
        body: {
          name: comparisonName.trim() || null,
          analysis_job_ids: selectedJobIds,
          baseline_job_id: baselineJobId || selectedJobIds[0],
          comparison_context: { workspace_source: 'compare_tab' },
        },
      })
      applyActiveComparison(comparison)
      cacheComparisonDetail(sessionToken, comparison)
      cacheComparisonHistoryEntry(sessionToken, comparison)
      setComparisonHistory((current) =>
        [
          buildHistoryItemFromComparison(comparison),
          ...current.filter((item) => item.id !== comparison.id),
        ].slice(0, 12),
      )
      setBanner({
        type: 'success',
        message: `Comparison ready. ${resolveComparisonLabel(comparison)} leads the current ranking.`,
      })
    } catch (error) {
      setBanner({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to create comparison.',
      })
    } finally {
      setIsCreatingComparison(false)
    }
  }, [applyActiveComparison, baselineJobId, comparisonName, selectedJobIds, sessionToken, setComparisonHistory])

  const handleOpenComparison = useCallback(
    (comparisonId: string) => {
      void loadComparison(comparisonId).then((comparison) => {
        if (comparison) {
          applyActiveComparison(comparison)
        }
      })
    },
    [applyActiveComparison, loadComparison],
  )

  const handleRefreshHistory = useCallback(() => {
    void reloadComparisonHistory()
  }, [reloadComparisonHistory])

  return (
    <Stack spacing={3}>
      <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
        <Stack spacing={2.5}>
          <Chip color="primary" label="Compare workspace" sx={{ alignSelf: 'flex-start' }} />
          <Stack alignItems="center" direction="row" spacing={0.75}>
            <Typography variant="h4">Pick a winner across 2 to 5 analyses.</Typography>
            <HelpTooltip title="Each comparison ranks selected analyses with weighted scores, deltas, scene-level changes, and recommendation overlap against your chosen baseline." />
          </Stack>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip icon={<CompareArrowsRounded />} label={`${selectedJobIds.length} selected`} variant="outlined" />
            <Chip
              icon={<SwapHorizRounded />}
              label={baselineCandidate ? `Baseline: ${resolveAnalysisLabel(baselineCandidate)}` : 'Pick a baseline'}
              variant="outlined"
            />
            <Chip icon={<HistoryRounded />} label={`${comparisonHistory.length} saved`} variant="outlined" />
          </Stack>
        </Stack>
      </Paper>

      {banner ? <Alert severity={banner.type}>{banner.message}</Alert> : null}

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Stack
              alignItems={{ xs: 'stretch', md: 'center' }}
              direction={{ xs: 'column', md: 'row' }}
              justifyContent="space-between"
              spacing={1.5}
            >
              <Stack alignItems="center" direction="row" spacing={0.5}>
                <Typography variant="h6">Build a comparison</Typography>
                <HelpTooltip title="Select 2 to 5 completed analyses. The baseline controls delta views and recommendation overlap." />
              </Stack>
              <Button
                disabled={selectedJobIds.length === 0}
                onClick={handleClearSelection}
                size="small"
                variant="outlined"
              >
                Clear selection
              </Button>
            </Stack>

            <TextField
              label="Comparison name"
              onChange={(event) => setComparisonName(event.target.value)}
              placeholder="Example: Spring launch hooks"
              value={comparisonName}
            />

            <SelectedCandidatesPanel
              baselineJobId={baselineCandidate?.job.id ?? null}
              items={selectedAnalyses}
              onRemove={handleToggleAnalysis}
              onSetBaseline={setBaselineJobId}
            />

            <Button
              data-testid="create-analysis-comparison"
              disabled={selectedJobIds.length < 2 || isCreatingComparison}
              onClick={() => void handleCreateComparison()}
              startIcon={<LaunchRounded />}
              variant="contained"
            >
              {isCreatingComparison ? 'Creating comparison…' : 'Create comparison'}
            </Button>

            <CompareCandidateList
              baselineJobId={baselineCandidate?.job.id ?? null}
              isLoading={isLoadingAnalyses}
              items={completedAnalyses}
              onSetBaseline={setBaselineJobId}
              onToggle={handleToggleAnalysis}
              selectedJobIds={selectedJobIds}
            />
          </Stack>
        </Paper>

        <ComparisonHistoryPanel
          activeComparisonId={activeComparisonId}
          comparisonLoadingId={comparisonLoadingId}
          history={comparisonHistory}
          isLoading={isLoadingComparisons}
          onOpenComparison={handleOpenComparison}
          onRefresh={handleRefreshHistory}
        />
      </Box>

      {activeComparison ? <ComparisonResults comparison={activeComparison} /> : null}

      <Suspense fallback={<DeferredPanelFallback title="Comparison review ops" />}>
        <CollaborationPanel
          entityId={activeComparison?.id ?? null}
          entityType="analysis_comparison"
          session={session}
          subtitle="Attach comments, ownership, and approval state to the saved comparison decision."
          title="Comparison review ops"
        />
      </Suspense>
    </Stack>
  )
}

function DeferredPanelFallbackBase({ title }: { title: string }) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Typography variant="h6">{title}</Typography>
        <LinearProgress sx={{ borderRadius: 999, height: 8 }} />
      </Stack>
    </Paper>
  )
}

const DeferredPanelFallback = memo(DeferredPanelFallbackBase)

export default ComparePage
