import CompareArrowsRounded from '@mui/icons-material/CompareArrowsRounded'
import HistoryRounded from '@mui/icons-material/HistoryRounded'
import InsightsRounded from '@mui/icons-material/InsightsRounded'
import LaunchRounded from '@mui/icons-material/LaunchRounded'
import SwapHorizRounded from '@mui/icons-material/SwapHorizRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Paper,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { Suspense, lazy, useEffect, useEffectEvent, useMemo, useState } from 'react'
import MetricsRadarCard from '../components/analysis/MetricsRadarCard'
import { apiRequest } from '../lib/api'
import {
  buildCompareWorkspaceStorageKey,
  readCompareWorkspaceSnapshot,
  storeCompareWorkspaceSnapshot,
} from '../lib/compareWorkspace'
import { runWhenIdle } from '../lib/defer'
import type { AuthSession } from '../lib/session'

const CollaborationPanel = lazy(() => import('../components/collaboration/CollaborationPanel'))

type ComparePageProps = {
  session: AuthSession
}

type JobState = 'queued' | 'processing' | 'completed' | 'failed'
type MediaType = 'video' | 'audio' | 'text'

type CompareBanner = {
  type: 'error' | 'success' | 'info'
  message: string
}

type AnalysisAsset = {
  id: string
  media_type: MediaType
  original_filename?: string | null
  object_key: string
  upload_status: string
  created_at: string
}

type AnalysisJob = {
  id: string
  asset_id: string
  status: JobState
  objective?: string | null
  goal_template?: string | null
  channel?: string | null
  audience_segment?: string | null
  created_at: string
}

type AnalysisSummary = {
  overall_attention_score: number
  hook_score_first_3_seconds: number
  sustained_engagement_score: number
  memory_proxy_score: number
  cognitive_load_proxy: number
  confidence?: number | null
}

type AnalysisMetricRow = {
  key: string
  label: string
  value: number
  unit: string
}

type AnalysisSegmentRow = {
  segment_index: number
  label: string
  start_time_ms: number
  end_time_ms: number
  attention_score: number
  engagement_delta: number
  note: string
}

type AnalysisRecommendation = {
  title: string
  detail: string
  priority: 'high' | 'medium' | 'low'
}

type AnalysisResult = {
  job_id: string
  summary_json: AnalysisSummary
  metrics_json: AnalysisMetricRow[]
  segments_json: AnalysisSegmentRow[]
  recommendations_json: AnalysisRecommendation[]
}

type AnalysisJobListItem = {
  job: AnalysisJob
  asset?: AnalysisAsset | null
  has_result: boolean
}

type AnalysisJobListResponse = {
  items: AnalysisJobListItem[]
}

type AnalysisComparisonHistoryItem = {
  id: string
  name: string
  created_at: string
  winning_analysis_job_id?: string | null
  baseline_job_id?: string | null
  candidate_count: number
  summary_json: Record<string, unknown>
  item_labels: string[]
}

type AnalysisComparisonHistoryResponse = {
  items: AnalysisComparisonHistoryItem[]
}

type AnalysisComparisonItem = {
  analysis_job_id: string
  job: AnalysisJob
  asset?: AnalysisAsset | null
  result: AnalysisResult
  overall_rank: number
  is_winner: boolean
  is_baseline: boolean
  scores_json: Record<string, number>
  delta_json: Record<string, number>
  rationale?: string | null
  scene_deltas_json: Array<{
    segment_index: number
    label: string
    baseline_window?: string | null
    candidate_window: string
    baseline_attention: number
    candidate_attention: number
    attention_delta: number
    engagement_delta_delta: number
    baseline_note?: string | null
    candidate_note: string
  }>
  recommendation_overlap_json: {
    shared_titles: string[]
    candidate_only_titles: string[]
    baseline_only_titles: string[]
  }
}

type AnalysisComparison = {
  id: string
  name: string
  created_at: string
  winning_analysis_job_id?: string | null
  baseline_job_id?: string | null
  summary_json: Record<string, unknown>
  comparison_context: Record<string, unknown>
  items: AnalysisComparisonItem[]
}

type CompareCacheEntry<T> = {
  sessionToken: string
  value: T
  loadedAt: number
}

const COMPARE_CACHE_TTL_MS = 30_000

let analysesCache: CompareCacheEntry<AnalysisJobListItem[]> | null = null
let comparisonsCache: CompareCacheEntry<AnalysisComparisonHistoryItem[]> | null = null
const comparisonDetailCache = new Map<string, CompareCacheEntry<AnalysisComparison>>()
const inFlightCompareRequests = new Map<string, Promise<AnalysisComparison>>()
let inFlightAnalysesRequest: Promise<AnalysisJobListItem[]> | null = null
let inFlightComparisonsRequest: Promise<AnalysisComparisonHistoryItem[]> | null = null

function isCacheFresh(cacheEntry: CompareCacheEntry<unknown> | null, sessionToken: string) {
  return (
    cacheEntry !== null &&
    cacheEntry.sessionToken === sessionToken &&
    Date.now() - cacheEntry.loadedAt <= COMPARE_CACHE_TTL_MS
  )
}

async function fetchCompletedAnalyses(sessionToken: string) {
  const cachedAnalyses = analysesCache
  if (cachedAnalyses && isCacheFresh(cachedAnalyses, sessionToken)) {
    return cachedAnalyses.value
  }
  if (inFlightAnalysesRequest) {
    return inFlightAnalysesRequest
  }

  const request = apiRequest<AnalysisJobListResponse>('/api/v1/analysis/jobs?limit=24', {
    sessionToken,
  }).then((response) => {
    const completedItems = response.items.filter((item) => item.has_result && item.job.status === 'completed')
    analysesCache = {
      sessionToken,
      value: completedItems,
      loadedAt: Date.now(),
    }
    return completedItems
  }).finally(() => {
    inFlightAnalysesRequest = null
  })

  inFlightAnalysesRequest = request
  return request
}

async function fetchComparisonHistory(sessionToken: string) {
  const cachedComparisons = comparisonsCache
  if (cachedComparisons && isCacheFresh(cachedComparisons, sessionToken)) {
    return cachedComparisons.value
  }
  if (inFlightComparisonsRequest) {
    return inFlightComparisonsRequest
  }

  const request = apiRequest<AnalysisComparisonHistoryResponse>('/api/v1/analysis/comparisons?limit=12', {
    sessionToken,
  }).then((response) => {
    comparisonsCache = {
      sessionToken,
      value: response.items,
      loadedAt: Date.now(),
    }
    return response.items
  }).finally(() => {
    inFlightComparisonsRequest = null
  })

  inFlightComparisonsRequest = request
  return request
}

async function fetchComparisonDetails(sessionToken: string, comparisonId: string) {
  const cacheKey = `${sessionToken}:${comparisonId}`
  const cachedValue = comparisonDetailCache.get(cacheKey) || null
  if (cachedValue && isCacheFresh(cachedValue, sessionToken)) {
    return cachedValue.value
  }

  const inFlightRequest = inFlightCompareRequests.get(cacheKey)
  if (inFlightRequest) {
    return inFlightRequest
  }

  const request = apiRequest<AnalysisComparison>(`/api/v1/analysis/comparisons/${comparisonId}`, {
    sessionToken,
  }).then((response) => {
    comparisonDetailCache.set(cacheKey, {
      sessionToken,
      value: response,
      loadedAt: Date.now(),
    })
    return response
  }).finally(() => {
    inFlightCompareRequests.delete(cacheKey)
  })

  inFlightCompareRequests.set(cacheKey, request)
  return request
}

function cacheComparisonHistoryEntry(sessionToken: string, comparison: AnalysisComparison) {
  const nextHistoryItem = buildHistoryItemFromComparison(comparison)
  const currentItems =
    isCacheFresh(comparisonsCache, sessionToken) && comparisonsCache !== null ? comparisonsCache.value : []
  comparisonsCache = {
    sessionToken,
    value: [nextHistoryItem, ...currentItems.filter((item) => item.id !== comparison.id)].slice(0, 12),
    loadedAt: Date.now(),
  }
}

function cacheComparisonDetail(sessionToken: string, comparison: AnalysisComparison) {
  comparisonDetailCache.set(`${sessionToken}:${comparison.id}`, {
    sessionToken,
    value: comparison,
    loadedAt: Date.now(),
  })
}

export function __resetComparePageRequestCacheForTests() {
  analysesCache = null
  comparisonsCache = null
  comparisonDetailCache.clear()
  inFlightCompareRequests.clear()
  inFlightAnalysesRequest = null
  inFlightComparisonsRequest = null
}

function ComparePage({ session }: ComparePageProps) {
  const storageScope = session.defaultProjectId || session.email
  const storageKey = buildCompareWorkspaceStorageKey(storageScope)
  const storedSnapshot = readCompareWorkspaceSnapshot(storageKey)
  const [analysisHistory, setAnalysisHistory] = useState<AnalysisJobListItem[]>([])
  const [comparisonHistory, setComparisonHistory] = useState<AnalysisComparisonHistoryItem[]>([])
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>(storedSnapshot.selectedJobIds)
  const [baselineJobId, setBaselineJobId] = useState<string | null>(storedSnapshot.baselineJobId)
  const [activeComparisonId, setActiveComparisonId] = useState<string | null>(storedSnapshot.activeComparisonId)
  const [activeComparison, setActiveComparison] = useState<AnalysisComparison | null>(null)
  const [comparisonName, setComparisonName] = useState('')
  const [banner, setBanner] = useState<CompareBanner | null>(null)
  const [isLoadingAnalyses, setIsLoadingAnalyses] = useState(true)
  const [isLoadingComparisons, setIsLoadingComparisons] = useState(true)
  const [isCreatingComparison, setIsCreatingComparison] = useState(false)
  const [comparisonLoadingId, setComparisonLoadingId] = useState<string | null>(null)
  const sessionToken = session.sessionToken

  const completedAnalyses = useMemo(
    () => analysisHistory.filter((item) => item.has_result && item.job.status === 'completed'),
    [analysisHistory],
  )
  const selectedAnalyses = useMemo(
    () => completedAnalyses.filter((item) => selectedJobIds.includes(item.job.id)),
    [completedAnalyses, selectedJobIds],
  )
  const baselineCandidate =
    selectedAnalyses.find((item) => item.job.id === baselineJobId) ?? selectedAnalyses[0] ?? null

  useEffect(() => {
    storeCompareWorkspaceSnapshot(storageKey, {
      selectedJobIds,
      baselineJobId,
      activeComparisonId,
    })
  }, [activeComparisonId, baselineJobId, selectedJobIds, storageKey])

  const loadAnalyses = useEffectEvent(async () => {
    if (!sessionToken) {
      setAnalysisHistory([])
      setIsLoadingAnalyses(false)
      return
    }

    setIsLoadingAnalyses(true)
    try {
      const completedItems = await fetchCompletedAnalyses(sessionToken)
      setAnalysisHistory(completedItems)
      setSelectedJobIds((current) => current.filter((jobId) => completedItems.some((item) => item.job.id === jobId)))
      setBaselineJobId((current) => {
        if (current && completedItems.some((item) => item.job.id === current)) {
          return current
        }
        const seededJobId =
          storedSnapshot.selectedJobIds.find((jobId) => completedItems.some((item) => item.job.id === jobId)) || null
        return seededJobId
      })
    } catch (error) {
      setBanner({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load completed analyses.',
      })
    } finally {
      setIsLoadingAnalyses(false)
    }
  })

  const loadComparisonHistory = useEffectEvent(async () => {
    if (!sessionToken) {
      setComparisonHistory([])
      setIsLoadingComparisons(false)
      return
    }

    setIsLoadingComparisons(true)
    try {
      setComparisonHistory(await fetchComparisonHistory(sessionToken))
    } catch (error) {
      setBanner({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load compare history.',
      })
    } finally {
      setIsLoadingComparisons(false)
    }
  })

  const applyActiveComparison = useEffectEvent((comparison: AnalysisComparison) => {
    setActiveComparison(comparison)
    setActiveComparisonId(comparison.id)
    setComparisonName(comparison.name)
    setSelectedJobIds(comparison.items.map((item) => item.analysis_job_id))
    setBaselineJobId(comparison.baseline_job_id || comparison.items.find((item) => item.is_baseline)?.analysis_job_id || null)
  })

  const loadComparison = useEffectEvent(async (comparisonId: string) => {
    if (!sessionToken) {
      return
    }

    setComparisonLoadingId(comparisonId)
    try {
      const comparison = await fetchComparisonDetails(sessionToken, comparisonId)
      applyActiveComparison(comparison)
    } catch (error) {
      setBanner({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load the selected comparison.',
      })
    } finally {
      setComparisonLoadingId((current) => (current === comparisonId ? null : current))
    }
  })

  useEffect(() => {
    void loadAnalyses()
    const cancelDeferredLoad = runWhenIdle(() => {
      void loadComparisonHistory()
    })
    return cancelDeferredLoad
  }, [loadAnalyses, loadComparisonHistory])

  useEffect(() => {
    if (!activeComparisonId || activeComparison?.id === activeComparisonId || !sessionToken) {
      return
    }
    void loadComparison(activeComparisonId)
  }, [activeComparison?.id, activeComparisonId, loadComparison, sessionToken])

  const handleToggleAnalysis = (item: AnalysisJobListItem) => {
    if (!item.has_result || item.job.status !== 'completed') {
      return
    }

    setSelectedJobIds((current) => {
      if (current.includes(item.job.id)) {
        const nextSelection = current.filter((jobId) => jobId !== item.job.id)
        setBaselineJobId((currentBaseline) => (currentBaseline === item.job.id ? nextSelection[0] || null : currentBaseline))
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
  }

  const handleCreateComparison = async () => {
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
          },
        },
      })
      applyActiveComparison(comparison)
      cacheComparisonDetail(sessionToken, comparison)
      cacheComparisonHistoryEntry(sessionToken, comparison)
      setComparisonHistory((current) => [
        buildHistoryItemFromComparison(comparison),
        ...current.filter((item) => item.id !== comparison.id),
      ].slice(0, 12))
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
  }

  return (
    <Stack spacing={3}>
      <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
        <Stack spacing={2.5}>
          <Chip color="primary" label="Compare workspace" sx={{ alignSelf: 'flex-start' }} />
          <Typography variant="h4">Compare 2 to 5 completed analyses and keep the winner history inside the product.</Typography>
          <Typography color="text.secondary" variant="body1">
            This workspace turns saved analysis runs into a decision view: ranked winner, score deltas, scene-level changes, and recommendation overlap against a chosen baseline.
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip icon={<CompareArrowsRounded />} label={`${selectedJobIds.length} selected`} variant="outlined" />
            <Chip icon={<SwapHorizRounded />} label={baselineCandidate ? `Baseline: ${resolveAnalysisLabel(baselineCandidate)}` : 'Pick a baseline'} variant="outlined" />
            <Chip icon={<HistoryRounded />} label={`${comparisonHistory.length} saved comparisons`} variant="outlined" />
          </Stack>
        </Stack>
      </Paper>

      {banner ? <Alert severity={banner.type}>{banner.message}</Alert> : null}

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Stack alignItems={{ xs: 'stretch', md: 'center' }} direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.5}>
              <Box>
                <Typography variant="h6">Build a comparison</Typography>
                <Typography color="text.secondary" variant="body2">
                  Select 2 to 5 completed analyses. The baseline controls delta views and recommendation overlap.
                </Typography>
              </Box>
              <Button
                disabled={selectedJobIds.length === 0}
                onClick={() => {
                  setSelectedJobIds([])
                  setBaselineJobId(null)
                  setActiveComparison(null)
                  setActiveComparisonId(null)
                }}
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
              onClick={handleCreateComparison}
              startIcon={<LaunchRounded />}
              variant="contained"
            >
              {isCreatingComparison ? 'Creating comparison…' : 'Create comparison'}
            </Button>

            <Box className="analysis-job-history">
              {isLoadingAnalyses ? (
                <Box className="analysis-empty-state">
                  <Typography color="text.secondary" variant="body2">
                    Loading completed analyses…
                  </Typography>
                </Box>
              ) : null}

              {!isLoadingAnalyses && completedAnalyses.length === 0 ? (
                <Box className="analysis-empty-state">
                  <Typography color="text.secondary" variant="body2">
                    No completed analyses are available yet. Finish at least two runs in Analysis before using compare.
                  </Typography>
                </Box>
              ) : null}

              {completedAnalyses.map((item) => {
                const isSelected = selectedJobIds.includes(item.job.id)
                const isBaseline = baselineCandidate?.job.id === item.job.id
                return (
                  <Box className={`analysis-job-history__item ${isSelected ? 'is-selected' : ''}`} key={item.job.id}>
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
                        {item.job.goal_template ? <Chip label={readableGoalTemplate(item.job.goal_template)} size="small" variant="outlined" /> : null}
                        {item.job.channel ? <Chip label={readableChannel(item.job.channel)} size="small" variant="outlined" /> : null}
                        <Chip label={item.asset?.media_type || 'analysis'} size="small" variant="outlined" />
                      </Stack>

                      <Typography color="text.secondary" variant="body2">
                        {truncateText(item.job.objective || 'No objective stored for this analysis.', 132)}
                      </Typography>

                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                        <Button onClick={() => handleToggleAnalysis(item)} size="small" variant={isSelected ? 'contained' : 'outlined'}>
                          {isSelected ? 'Selected' : 'Add to compare'}
                        </Button>
                        <Button
                          disabled={!isSelected}
                          onClick={() => setBaselineJobId(item.job.id)}
                          size="small"
                          variant="text"
                        >
                          Set as baseline
                        </Button>
                      </Stack>
                    </Stack>
                  </Box>
                )
              })}
            </Box>
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Stack alignItems={{ xs: 'stretch', md: 'center' }} direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.5}>
              <Box>
                <Typography variant="h6">Saved comparisons</Typography>
                <Typography color="text.secondary" variant="body2">
                  Reopen earlier winner calls and keep the context inside the same workspace.
                </Typography>
              </Box>
              <Button onClick={() => void loadComparisonHistory()} size="small" variant="text">
                Refresh
              </Button>
            </Stack>

            {isLoadingComparisons ? (
              <Box className="analysis-empty-state">
                <Typography color="text.secondary" variant="body2">
                  Loading compare history…
                </Typography>
              </Box>
            ) : null}

            {!isLoadingComparisons && comparisonHistory.length === 0 ? (
              <Box className="analysis-empty-state">
                <Typography color="text.secondary" variant="body2">
                  No saved comparisons yet. Create one from the completed analysis list to start building decision history.
                </Typography>
              </Box>
            ) : null}

            {comparisonHistory.length > 0 ? (
              <Box className="analysis-job-history" data-testid="compare-history-list">
                {comparisonHistory.map((item) => (
                  <Box className={`analysis-job-history__item ${activeComparisonId === item.id ? 'is-selected' : ''}`} key={item.id}>
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
                          label={comparisonLoadingId === item.id ? 'Loading' : `${item.candidate_count} items`}
                          size="small"
                          variant="outlined"
                        />
                      </Stack>
                      <Typography color="text.secondary" variant="body2">
                        {truncateText(item.item_labels.join(' • '), 120)}
                      </Typography>
                      <Button onClick={() => void loadComparison(item.id)} size="small" variant="outlined">
                        Open comparison
                      </Button>
                    </Stack>
                  </Box>
                ))}
              </Box>
            ) : null}
          </Stack>
        </Paper>
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

function SelectedCandidatesPanel({
  baselineJobId,
  items,
  onRemove,
  onSetBaseline,
}: {
  baselineJobId: string | null
  items: AnalysisJobListItem[]
  onRemove: (item: AnalysisJobListItem) => void
  onSetBaseline: (jobId: string) => void
}) {
  if (items.length === 0) {
    return (
      <Box className="analysis-empty-state">
        <Typography color="text.secondary" variant="body2">
          No analyses selected yet. Add completed runs below to build a side-by-side review.
        </Typography>
      </Box>
    )
  }

  return (
    <Box className="compare-selected-grid">
      {items.map((item) => (
        <Box className={`compare-selected-card ${baselineJobId === item.job.id ? 'is-baseline' : ''}`} key={item.job.id}>
          <Stack spacing={1.25}>
            <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1.5}>
              <Typography variant="subtitle2">{resolveAnalysisLabel(item)}</Typography>
              {baselineJobId === item.job.id ? (
                <Chip color="primary" label="Baseline" size="small" variant="outlined" />
              ) : null}
            </Stack>
            <Typography color="text.secondary" variant="body2">
              {truncateText(item.job.objective || 'No objective stored.', 92)}
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button onClick={() => onSetBaseline(item.job.id)} size="small" variant="text">
                Baseline
              </Button>
              <Button onClick={() => onRemove(item)} size="small" variant="outlined">
                Remove
              </Button>
            </Stack>
          </Stack>
        </Box>
      ))}
    </Box>
  )
}

function DeferredPanelFallback({ title }: { title: string }) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Typography variant="h6">{title}</Typography>
        <LinearProgress sx={{ borderRadius: 999, height: 8 }} />
        <Typography color="text.secondary" variant="body2">
          This workspace defers non-critical review tools until the main comparison view is ready.
        </Typography>
      </Stack>
    </Paper>
  )
}

function ComparisonResults({ comparison }: { comparison: AnalysisComparison }) {
  const winner = comparison.items.find((item) => item.is_winner) || comparison.items[0] || null
  const baseline = comparison.items.find((item) => item.is_baseline) || comparison.items[0] || null
  const challengers = comparison.items.filter((item) => !item.is_baseline)
  const metricLeaders = Array.isArray(comparison.summary_json.metric_leaders)
    ? (comparison.summary_json.metric_leaders as Array<{ metric: string; analysis_job_id: string; value: number }>)
    : []

  if (!winner || !baseline) {
    return null
  }

  return (
    <Stack spacing={3}>
      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Stack alignItems={{ xs: 'stretch', md: 'center' }} direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.5}>
            <Box>
              <Typography variant="h6">Winner call</Typography>
              <Typography color="text.secondary" variant="body2">
                The current ranking uses the persisted weighted comparison summary, not an ad hoc frontend sort.
              </Typography>
            </Box>
            <Chip icon={<InsightsRounded />} label={comparison.name} variant="outlined" />
          </Stack>

          <Box className="compare-winner-grid">
            <Box className="compare-winner-card">
              <Stack spacing={1.5}>
                <Chip color="success" label="Likely winner" size="small" sx={{ alignSelf: 'flex-start' }} />
                <Typography variant="h5">{resolveComparisonItemLabel(winner)}</Typography>
                <Typography color="text.secondary" variant="body2">
                  {winner.rationale || 'This item leads the current comparison.'}
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip label={`Composite ${formatNumber(winner.scores_json.composite)}`} size="small" variant="outlined" />
                  <Chip label={`Attention ${formatNumber(winner.scores_json.overall_attention)}`} size="small" variant="outlined" />
                  <Chip label={`Hook ${formatNumber(winner.scores_json.hook)}`} size="small" variant="outlined" />
                </Stack>
              </Stack>
            </Box>

            <Box className="analysis-inline-summary">
              <Typography variant="subtitle2">Why it leads</Typography>
              <Typography color="text.secondary" variant="body2">
                {String(comparison.summary_json.winning_rationale || winner.rationale || 'No rationale available.')}
              </Typography>
              <Stack spacing={1}>
                {metricLeaders.slice(0, 4).map((leader) => (
                  <DetailRow
                    key={`${leader.metric}-${leader.analysis_job_id}`}
                    label={readableMetric(leader.metric)}
                    value={
                      winner.analysis_job_id === leader.analysis_job_id
                        ? `${formatNumber(leader.value)} · leader`
                        : `${formatNumber(leader.value)} · ${findComparisonItemLabel(comparison.items, leader.analysis_job_id)}`
                    }
                  />
                ))}
              </Stack>
            </Box>

            <Box className="analysis-inline-summary">
              <Typography variant="subtitle2">Baseline</Typography>
              <Typography color="text.secondary" variant="body2">
                Deltas below are measured against {resolveComparisonItemLabel(baseline)}.
              </Typography>
              <Stack spacing={1}>
                <DetailRow label="Attention" value={formatNumber(baseline.result.summary_json.overall_attention_score)} />
                <DetailRow label="Hook" value={formatNumber(baseline.result.summary_json.hook_score_first_3_seconds)} />
                <DetailRow label="Memory" value={formatNumber(baseline.result.summary_json.memory_proxy_score)} />
                <DetailRow label="Cognitive load" value={formatNumber(baseline.result.summary_json.cognitive_load_proxy)} />
              </Stack>
            </Box>
          </Box>
        </Stack>
      </Paper>

      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Typography variant="h6">Ranking and score deltas</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Item</TableCell>
                <TableCell align="right">Rank</TableCell>
                <TableCell align="right">Composite</TableCell>
                <TableCell align="right">Delta vs baseline</TableCell>
                <TableCell align="right">Attention</TableCell>
                <TableCell align="right">Hook</TableCell>
                <TableCell align="right">Memory</TableCell>
                <TableCell align="right">Low load</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {comparison.items.map((item) => (
                <TableRow key={item.analysis_job_id}>
                  <TableCell>{resolveComparisonItemLabel(item)}</TableCell>
                  <TableCell align="right">{item.overall_rank}</TableCell>
                  <TableCell align="right">{formatNumber(item.scores_json.composite)}</TableCell>
                  <TableCell align="right">{item.is_baseline ? 'Baseline' : formatSignedNumber(item.delta_json.composite)}</TableCell>
                  <TableCell align="right">{formatNumber(item.scores_json.overall_attention)}</TableCell>
                  <TableCell align="right">{formatNumber(item.scores_json.hook)}</TableCell>
                  <TableCell align="right">{formatNumber(item.scores_json.memory_proxy)}</TableCell>
                  <TableCell align="right">{formatNumber(item.scores_json.low_cognitive_load)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Stack>
      </Paper>

      <ScoreGaugesComparison items={comparison.items} />

      <MetricsRadarCard
        description="Compare each result's persisted metric rows in one radial view to spot where a challenger outperforms or trails the baseline."
        emptyMessage="Radar comparison appears when at least three comparable metrics are available across the selected results."
        series={comparison.items.map((item) => ({
          label: resolveComparisonItemLabel(item),
          metrics: item.result.metrics_json,
        }))}
        testId="compare-metrics-radar"
        title="Metrics radar comparison"
      />

      {challengers.map((item) => (
        <Paper className="dashboard-card" elevation={0} key={item.analysis_job_id}>
          <Stack spacing={2}>
            <Stack alignItems={{ xs: 'stretch', md: 'center' }} direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.5}>
              <Box>
                <Typography variant="h6">{resolveComparisonItemLabel(item)} vs baseline</Typography>
                <Typography color="text.secondary" variant="body2">
                  Use this view to see where the challenger diverges from the baseline across scenes and recommendations.
                </Typography>
              </Box>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Chip label={`Composite ${formatSignedNumber(item.delta_json.composite)}`} size="small" variant="outlined" />
                <Chip label={`Attention ${formatSignedNumber(item.delta_json.overall_attention)}`} size="small" variant="outlined" />
                <Chip label={`Hook ${formatSignedNumber(item.delta_json.hook)}`} size="small" variant="outlined" />
              </Stack>
            </Stack>

            {(baseline?.result.segments_json.length ?? 0) > 0 || item.result.segments_json.length > 0 ? (
              <CompareHeatstripCard
                baseline={baseline}
                challenger={item}
              />
            ) : null}

            <Box className="dashboard-grid dashboard-grid--content">
              <Paper className="dashboard-card compare-detail-card" elevation={0}>
                <Stack spacing={2}>
                  <Typography variant="subtitle1">Scene-by-scene differences</Typography>
                  {item.scene_deltas_json.length === 0 ? (
                    <Box className="analysis-empty-state">
                      <Typography color="text.secondary" variant="body2">
                        No scene delta rows are available for this comparison.
                      </Typography>
                    </Box>
                  ) : (
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Scene</TableCell>
                          <TableCell align="right">Attention delta</TableCell>
                          <TableCell align="right">Engagement delta</TableCell>
                          <TableCell>Candidate note</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {item.scene_deltas_json.map((scene) => (
                          <TableRow key={`${item.analysis_job_id}-${scene.segment_index}`}>
                            <TableCell>{scene.label}</TableCell>
                            <TableCell align="right">{formatSignedNumber(scene.attention_delta)}</TableCell>
                            <TableCell align="right">{formatSignedNumber(scene.engagement_delta_delta)}</TableCell>
                            <TableCell>{scene.candidate_note}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </Stack>
              </Paper>

              <Paper className="dashboard-card compare-detail-card" elevation={0}>
                <Stack spacing={2}>
                  <Typography variant="subtitle1">Recommendation overlap</Typography>
                  <RecommendationOverlapSection item={item} />
                </Stack>
              </Paper>
            </Box>
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}

function RecommendationOverlapSection({ item }: { item: AnalysisComparisonItem }) {
  const overlap = item.recommendation_overlap_json

  return (
    <Stack spacing={1.5}>
      <RecommendationBucket title="Shared" items={overlap.shared_titles} />
      <RecommendationBucket title="Challenger only" items={overlap.candidate_only_titles} />
      <RecommendationBucket title="Baseline only" items={overlap.baseline_only_titles} />
    </Stack>
  )
}

function RecommendationBucket({ title, items }: { title: string; items: string[] }) {
  return (
    <Box className="analysis-inline-summary">
      <Typography variant="subtitle2">{title}</Typography>
      {items.length === 0 ? (
        <Typography color="text.secondary" variant="body2">
          No items in this bucket.
        </Typography>
      ) : (
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          {items.map((value) => (
            <Chip key={`${title}-${value}`} label={value} size="small" variant="outlined" />
          ))}
        </Stack>
      )}
    </Box>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
      <Typography sx={{ textAlign: 'right' }} variant="subtitle2">
        {value}
      </Typography>
    </Stack>
  )
}

function resolveAnalysisLabel(item: AnalysisJobListItem) {
  return item.asset?.original_filename || item.job.objective || `Analysis ${item.job.id.slice(0, 8)}`
}

function resolveComparisonItemLabel(item: AnalysisComparisonItem) {
  return item.asset?.original_filename || item.job.objective || `Analysis ${item.analysis_job_id.slice(0, 8)}`
}

function findComparisonItemLabel(items: AnalysisComparisonItem[], analysisJobId: string) {
  return resolveComparisonItemLabel(items.find((item) => item.analysis_job_id === analysisJobId) || items[0])
}

function buildHistoryItemFromComparison(comparison: AnalysisComparison): AnalysisComparisonHistoryItem {
  return {
    id: comparison.id,
    name: comparison.name,
    created_at: comparison.created_at,
    winning_analysis_job_id: comparison.winning_analysis_job_id || null,
    baseline_job_id: comparison.baseline_job_id || null,
    candidate_count: comparison.items.length,
    summary_json: comparison.summary_json,
    item_labels: comparison.items.map((item) => resolveComparisonItemLabel(item)),
  }
}

function resolveComparisonLabel(comparison: AnalysisComparison) {
  const winner = comparison.items.find((item) => item.analysis_job_id === comparison.winning_analysis_job_id)
  return winner ? resolveComparisonItemLabel(winner) : comparison.name
}

function readableGoalTemplate(value: string) {
  return value.replaceAll('_', ' ')
}

function readableChannel(value: string) {
  return value.replaceAll('_', ' ')
}

function readableMetric(value: string) {
  return value.replaceAll('_', ' ')
}

function formatTimestamp(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value
  }
  return `${value.slice(0, maxLength - 1).trimEnd()}…`
}

function formatNumber(value: number | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--'
  }
  return value.toFixed(1)
}

function formatSignedNumber(value: number | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--'
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
}

// ---------------------------------------------------------------------------
// Visualization utilities
// ---------------------------------------------------------------------------

function scoreToColor(score: number): string {
  const clamped = Math.max(0, Math.min(100, score))
  const hue = (clamped / 100) * 120
  return `hsl(${Math.round(hue)}, 70%, 45%)`
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

function ScoreGauge({
  isReady,
  label,
  size = 68,
  value,
}: {
  isReady: boolean
  label: string
  size?: number
  value: number
}) {
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
        <Box
          sx={{
            alignItems: 'center',
            display: 'flex',
            inset: 0,
            justifyContent: 'center',
            position: 'absolute',
          }}
        >
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

function ScoreGaugesComparison({ items }: { items: AnalysisComparisonItem[] }) {
  const metrics: Array<{ key: string; label: string }> = [
    { key: 'overall_attention', label: 'Attention' },
    { key: 'hook', label: 'Hook' },
    { key: 'sustained_engagement', label: 'Sustained' },
    { key: 'memory_proxy', label: 'Memory' },
    { key: 'low_cognitive_load', label: 'Low Load' },
  ]

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Typography variant="h6">Score profiles</Typography>
        <Typography color="text.secondary" variant="body2">
          Visual gauge comparison across all items. Green ≥ 70, amber ≥ 40, red below threshold.
        </Typography>
        <Box
          sx={{
            display: 'grid',
            gap: 3,
            gridTemplateColumns: `repeat(${Math.min(items.length, 4)}, 1fr)`,
          }}
        >
          {items.map((item) => (
            <Box key={item.analysis_job_id}>
              <Stack spacing={0.75} sx={{ mb: 2 }}>
                <Typography variant="subtitle2">{resolveComparisonItemLabel(item)}</Typography>
                {item.is_winner && (
                  <Chip
                    color="success"
                    label="Winner"
                    size="small"
                    sx={{ alignSelf: 'flex-start' }}
                    variant="outlined"
                  />
                )}
                {item.is_baseline && !item.is_winner && (
                  <Chip
                    color="primary"
                    label="Baseline"
                    size="small"
                    sx={{ alignSelf: 'flex-start' }}
                    variant="outlined"
                  />
                )}
              </Stack>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
                {metrics.map(({ key, label }) => (
                  <ScoreGauge
                    key={key}
                    isReady
                    label={label}
                    value={item.scores_json[key] ?? 0}
                  />
                ))}
              </Box>
            </Box>
          ))}
        </Box>
      </Stack>
    </Paper>
  )
}

function CompareSegmentHeatstrip({
  label: stripLabel,
  segments,
  stripHeight = 28,
}: {
  label?: string
  segments: AnalysisSegmentRow[]
  stripHeight?: number
}) {
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

function CompareHeatstripCard({
  baseline,
  challenger,
}: {
  baseline: AnalysisComparisonItem | null
  challenger: AnalysisComparisonItem
}) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={1.5}>
        <Typography variant="subtitle1">Attention heatstrip</Typography>
        <Typography color="text.secondary" variant="body2">
          Segment-by-segment attention for baseline and challenger. Color: red = low, green = high.
        </Typography>
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

export default ComparePage
