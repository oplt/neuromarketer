import CloseRounded from '@mui/icons-material/CloseRounded'
import HistoryRounded from '@mui/icons-material/HistoryRounded'
import LaunchRounded from '@mui/icons-material/LaunchRounded'
import SettingsRounded from '@mui/icons-material/SettingsRounded'
import UploadFileRounded from '@mui/icons-material/UploadFileRounded'
import {
  Alert,
  Box,
  Button,
  Collapse,
  Drawer,
  IconButton,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Suspense, lazy, memo, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
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
  onOpenAnalysis?: () => void
  session: AuthSession
}

function ComparePage({ onOpenAnalysis, session }: ComparePageProps) {
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
  const [comparisonType, setComparisonType] = useState('overall_decision')
  const [assetSearch, setAssetSearch] = useState('')
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
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

  const filteredAnalyses = useMemo(() => {
    const query = assetSearch.trim().toLowerCase()
    if (!query) {
      return completedAnalyses
    }
    return completedAnalyses.filter((item) => {
      const label = resolveAnalysisLabel(item).toLowerCase()
      const objective = item.job.objective?.toLowerCase() || ''
      const channel = item.job.channel?.toLowerCase() || ''
      return label.includes(query) || objective.includes(query) || channel.includes(query)
    })
  }, [assetSearch, completedAnalyses])

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
          comparison_context: {
            workspace_source: 'compare_tab',
            comparison_type: comparisonType,
          },
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
  }, [
    applyActiveComparison,
    baselineJobId,
    comparisonName,
    comparisonType,
    selectedJobIds,
    sessionToken,
    setComparisonHistory,
  ])

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

  const handleNewComparison = useCallback(() => {
    setActiveComparison(null)
    setActiveComparisonId(null)
    setBanner(null)
  }, [setActiveComparison])

  return (
    <Stack className="compare-page" spacing={3}>
      <Box className="compare-shell">
        <Stack spacing={3}>
          <CompareStepper activeStep={activeComparison ? 3 : selectedJobIds.length >= 2 ? 2 : 1} />
          <Stack
            alignItems={{ xs: 'stretch', md: 'center' }}
            direction={{ xs: 'column', md: 'row' }}
            justifyContent="space-between"
            spacing={2}
          >
            <Box>
              <Typography variant="h4">Compare assets</Typography>
              <Typography color="text.secondary" variant="body2">
                Select at least two completed analyses. Compare highlights winner, deltas, insights, next steps.
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {activeComparison ? (
                <Button onClick={handleNewComparison} variant="outlined">
                  New comparison
                </Button>
              ) : null}
              <Button onClick={() => setDetailsOpen(true)} startIcon={<HistoryRounded />} variant="text">
                View details
              </Button>
            </Stack>
          </Stack>

          {banner ? <Alert severity={banner.type}>{banner.message}</Alert> : null}

          {activeComparison ? (
            <ComparisonResults comparison={activeComparison} />
          ) : (
            <Stack spacing={2.5}>
              <AssetSelector
                assetSearch={assetSearch}
                baselineJobId={baselineCandidate?.job.id ?? null}
                isLoading={isLoadingAnalyses}
                items={filteredAnalyses}
                onAssetSearchChange={setAssetSearch}
                onClearSelection={handleClearSelection}
                onSetBaseline={setBaselineJobId}
                onToggle={handleToggleAnalysis}
                onUpload={onOpenAnalysis}
                selectedAnalyses={selectedAnalyses}
                selectedJobIds={selectedJobIds}
              />

              <ComparisonSettings
                comparisonName={comparisonName}
                comparisonType={comparisonType}
                onComparisonNameChange={setComparisonName}
                onComparisonTypeChange={setComparisonType}
                onToggleAdvanced={() => setShowAdvancedSettings((current) => !current)}
                showAdvancedSettings={showAdvancedSettings}
              />

              <Paper className="compare-action-panel" elevation={0}>
                <Stack spacing={1.5}>
                  <Button
                    data-testid="create-analysis-comparison"
                    disabled={selectedJobIds.length < 2 || isCreatingComparison}
                    onClick={() => void handleCreateComparison()}
                    size="large"
                    startIcon={<LaunchRounded />}
                    variant="contained"
                  >
                    {isCreatingComparison ? 'Analyzing differences…' : 'Run comparison'}
                  </Button>
                  {selectedJobIds.length < 2 ? (
                    <Typography color="text.secondary" variant="body2">
                      Select at least 2 assets to compare.
                    </Typography>
                  ) : null}
                  {isCreatingComparison ? (
                    <Stack spacing={1}>
                      <LinearProgress sx={{ borderRadius: 999, height: 8 }} />
                      <Typography color="text.secondary" variant="body2">
                        Processing → Scoring → Insights
                      </Typography>
                    </Stack>
                  ) : null}
                </Stack>
              </Paper>
            </Stack>
          )}
        </Stack>
      </Box>

      <TechnicalDetailsDrawer onClose={() => setDetailsOpen(false)} open={detailsOpen}>
        <ComparisonHistoryPanel
          activeComparisonId={activeComparisonId}
          comparisonLoadingId={comparisonLoadingId}
          history={comparisonHistory}
          isLoading={isLoadingComparisons}
          onOpenComparison={handleOpenComparison}
          onRefresh={handleRefreshHistory}
        />

        <Suspense fallback={<DeferredPanelFallback title="Comparison review ops" />}>
          <CollaborationPanel
            entityId={activeComparison?.id ?? null}
            entityType="analysis_comparison"
            session={session}
            subtitle="Attach comments, ownership, and approval state to the saved comparison decision."
            title="Comparison review ops"
          />
        </Suspense>
      </TechnicalDetailsDrawer>
    </Stack>
  )
}

type CompareStepperProps = {
  activeStep: 1 | 2 | 3
}

function CompareStepperBase({ activeStep }: CompareStepperProps) {
  const steps = [
    { id: 1, label: 'Select items' },
    { id: 2, label: 'Configure' },
    { id: 3, label: 'Results' },
  ] as const

  return (
    <Box className="compare-stepper" aria-label="Compare workflow">
      {steps.map((step) => (
        <Box
          className={`compare-stepper__item ${activeStep === step.id ? 'is-active' : ''} ${
            activeStep > step.id ? 'is-complete' : ''
          }`}
          key={step.id}
        >
          <span>{step.id}</span>
          <Typography variant="subtitle2">{step.label}</Typography>
        </Box>
      ))}
    </Box>
  )
}

type AssetSelectorProps = {
  assetSearch: string
  baselineJobId: string | null
  isLoading: boolean
  items: AnalysisJobListItem[]
  onAssetSearchChange: (value: string) => void
  onClearSelection: () => void
  onSetBaseline: (jobId: string) => void
  onToggle: (item: AnalysisJobListItem) => void
  onUpload?: () => void
  selectedAnalyses: AnalysisJobListItem[]
  selectedJobIds: string[]
}

function AssetSelectorBase({
  assetSearch,
  baselineJobId,
  isLoading,
  items,
  onAssetSearchChange,
  onClearSelection,
  onSetBaseline,
  onToggle,
  onUpload,
  selectedAnalyses,
  selectedJobIds,
}: AssetSelectorProps) {
  return (
    <Paper className="compare-flow-section" elevation={0}>
      <Stack spacing={2}>
        <SectionHeader eyebrow="Step 1" title="Select items" />
        <SelectedAssetsBar
          baselineJobId={baselineJobId}
          items={selectedAnalyses}
          onRemove={onToggle}
          onSetBaseline={onSetBaseline}
        />
        <Stack
          alignItems={{ xs: 'stretch', md: 'center' }}
          direction={{ xs: 'column', md: 'row' }}
          justifyContent="space-between"
          spacing={1.5}
        >
          <TextField
            label="Find assets"
            onChange={(event) => onAssetSearchChange(event.target.value)}
            placeholder="Search filename, objective, channel"
            size="small"
            value={assetSearch}
          />
          <Stack direction="row" spacing={1}>
            <Button onClick={onUpload} startIcon={<UploadFileRounded />} variant="outlined">
              Upload
            </Button>
            <Button disabled={selectedJobIds.length === 0} onClick={onClearSelection} variant="text">
              Clear
            </Button>
          </Stack>
        </Stack>
        <CompareCandidateList
          baselineJobId={baselineJobId}
          isLoading={isLoading}
          items={items}
          onSetBaseline={onSetBaseline}
          onToggle={onToggle}
          selectedJobIds={selectedJobIds}
        />
      </Stack>
    </Paper>
  )
}

type SelectedAssetsBarProps = {
  baselineJobId: string | null
  items: AnalysisJobListItem[]
  onRemove: (item: AnalysisJobListItem) => void
  onSetBaseline: (jobId: string) => void
}

function SelectedAssetsBarBase(props: SelectedAssetsBarProps) {
  return <SelectedCandidatesPanel {...props} />
}

type ComparisonSettingsProps = {
  comparisonName: string
  comparisonType: string
  onComparisonNameChange: (value: string) => void
  onComparisonTypeChange: (value: string) => void
  onToggleAdvanced: () => void
  showAdvancedSettings: boolean
}

function ComparisonSettingsBase({
  comparisonName,
  comparisonType,
  onComparisonNameChange,
  onComparisonTypeChange,
  onToggleAdvanced,
  showAdvancedSettings,
}: ComparisonSettingsProps) {
  return (
    <Paper className="compare-flow-section" elevation={0}>
      <Stack spacing={2}>
        <SectionHeader eyebrow="Step 2" title="Configure comparison" />
        <TextField
          label="Comparison type"
          onChange={(event) => onComparisonTypeChange(event.target.value)}
          select
          size="small"
          value={comparisonType}
        >
          <MenuItem value="overall_decision">Overall winner</MenuItem>
          <MenuItem value="hook_performance">Hook performance</MenuItem>
          <MenuItem value="engagement">Engagement</MenuItem>
          <MenuItem value="structure">Structure</MenuItem>
        </TextField>
        <Button
          onClick={onToggleAdvanced}
          size="small"
          startIcon={<SettingsRounded />}
          sx={{ alignSelf: 'flex-start' }}
          variant="text"
        >
          Advanced settings
        </Button>
        <Collapse in={showAdvancedSettings}>
          <TextField
            fullWidth
            label="Comparison name"
            onChange={(event) => onComparisonNameChange(event.target.value)}
            placeholder="Spring launch hooks"
            size="small"
            value={comparisonName}
          />
        </Collapse>
      </Stack>
    </Paper>
  )
}

type SectionHeaderProps = {
  eyebrow: string
  title: string
}

function SectionHeader({ eyebrow, title }: SectionHeaderProps) {
  return (
    <Box>
      <Typography color="primary" variant="overline">
        {eyebrow}
      </Typography>
      <Typography variant="h6">{title}</Typography>
    </Box>
  )
}

type TechnicalDetailsDrawerProps = {
  children: ReactNode
  onClose: () => void
  open: boolean
}

function TechnicalDetailsDrawerBase({ children, onClose, open }: TechnicalDetailsDrawerProps) {
  return (
    <Drawer anchor="right" onClose={onClose} open={open}>
      <Box className="compare-details-drawer" role="presentation">
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={2}>
          <Typography variant="h6">Details</Typography>
          <IconButton aria-label="Close details" onClick={onClose}>
            <CloseRounded />
          </IconButton>
        </Stack>
        <Stack spacing={2}>{children}</Stack>
      </Box>
    </Drawer>
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
const CompareStepper = memo(CompareStepperBase)
const AssetSelector = memo(AssetSelectorBase)
const SelectedAssetsBar = memo(SelectedAssetsBarBase)
const ComparisonSettings = memo(ComparisonSettingsBase)
const TechnicalDetailsDrawer = memo(TechnicalDetailsDrawerBase)

export default ComparePage
