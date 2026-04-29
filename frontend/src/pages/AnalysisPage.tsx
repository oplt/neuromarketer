/* eslint-disable react-hooks/rules-of-hooks -- useEffectEvent analytics + loaders intentionally invoked from async handlers (legacy pattern) */
import { Suspense, lazy } from 'react'
import CloudUploadRounded from '@mui/icons-material/CloudUploadRounded'
import DeleteRounded from '@mui/icons-material/DeleteRounded'
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded'
import HistoryRounded from '@mui/icons-material/HistoryRounded'
import FileUploadRounded from '@mui/icons-material/FileUploadRounded'
import TuneRounded from '@mui/icons-material/TuneRounded'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  ButtonBase,
  Checkbox,
  Chip,
  Drawer,
  LinearProgress,
  MenuItem,
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
import {
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type ElementType,
  type ReactNode,
} from 'react'
import { apiRequest, subscribeToEventStream, uploadToApi, uploadToSignedUrl } from '../lib/api'
import { buildCompareWorkspaceStorageKey, storeCompareWorkspaceSnapshot } from '../lib/compareWorkspace'
import { runWhenIdle } from '../lib/defer'
import type { AuthSession } from '../lib/session'
import AnalyzeStepper, { type AnalyzeWizardStep } from '../components/analysis/AnalyzeStepper'
import { ProcessingStatus, ResultsStep, ReviewRunStep } from '../components/analysis/ProcessingStatus'
import RecentUploads from '../components/analysis/RecentUploads'
import ResultsActionHub from '../components/analysis/ResultsActionHub'
import SelectedSourceSummary from '../components/analysis/SelectedSourceSummary'
import ScoreGauge from '../components/analysis/results/ScoreGauge'
import {
  AnalysisTransportDiagnosticsCard,
  AttentionIntervalsCard,
  BenchmarkPercentilesCard,
  CalibrationPanel,
  ExecutiveVerdictCard,
  MinimalModalityResults,
  RecommendationsCard,
  ResultStateBanner,
  SegmentHeatstrip,
  SignalMatrixCard,
  SignalSummaryCard,
  TimelineChart,
  TimelineChartSkeleton,
  VideoFrameStrip,
} from '../components/analysis/results/ResultPanels'
import DeferredPanelFallback from '../components/analysis/shared/DeferredPanelFallback'
import DetailRow from '../components/analysis/shared/DetailRow'
import ValidationRow from '../components/analysis/shared/ValidationRow'
import {
  normalizeAnalysisResultForRender,
  resetWorkflowState,
} from '../features/analysis/resultRendering'

const AnalysisEvaluationSection = lazy(() => import('../components/analysis/AnalysisEvaluationSection'))
const CollaborationPanel = lazy(() => import('../components/collaboration/CollaborationPanel'))
import type { AnalysisEvaluationProgressSnapshot } from '../components/analysis/AnalysisEvaluationSection'
import type {
  AnalysisAsset,
  AnalysisAssetListResponse,
  AnalysisBenchmarkResponse,
  AnalysisBulkDeleteResponse,
  AnalysisCalibrationResponse,
  AnalysisClientEventName,
  AnalysisConfigResponse,
  AnalysisExecutiveVerdict,
  AnalysisGeneratedVariant,
  AnalysisGeneratedVariantListResponse,
  AnalysisGoalPresetsResponse,
  AnalysisJob,
  AnalysisJobListItem,
  AnalysisJobListResponse,
  AnalysisJobStatusResponse,
  AnalysisOutcomeImportResponse,
  AnalysisProgressEvent,
  AnalysisProgressState,
  AnalysisResult,
  AnalysisSelectionMode,
  AnalysisTransportDiagnostics,
  AnalysisUploadCompleteResponse,
  AnalysisUploadCreateResponse,
  BannerMessage,
  HistoryDrawerMode,
  LoadAnalysisJobOptions,
  MediaType,
  UploadStage,
  UploadState,
} from '../features/analysis/types'
import {
  ANALYSIS_HISTORY_LIMIT,
  defaultGoalPresets,
  mediaTypeOptions,
  placeholderHeatmapFrames,
  placeholderSegments,
  placeholderSummary,
  placeholderTimeline,
} from '../features/analysis/constants'
import {
  buildAnalysisWizardStorageKey,
  buildSelectedAssetStorageKey,
  buildSelectedJobStorageKey,
  clearSelectedAnalysisAssetId,
  clearSelectedAnalysisJobId,
  readAnalysisWizardSnapshot,
  readSelectedAnalysisAssetId,
  readSelectedAnalysisJobId,
  storeAnalysisWizardSnapshot,
  storeSelectedAnalysisAssetId,
  storeSelectedAnalysisJobId,
} from '../features/analysis/storage'
import { validateCurrentInput, validateGoalContext } from '../features/analysis/validation'
import {
  areAnalysisJobsEqual,
  areAnalysisProgressStatesEqual,
  areAnalysisResultsEqual,
  buildFrameBreakdownItems,
  buildGeneratedVariantText,
  buildQuickComparisonRows,
  buildRecommendationsPendingMessage,
  buildScenePendingMessage,
  buildScoringPendingMessage,
  buildSummaryCards,
  buildTextUploadAccept,
  buildUploadSource,
  calculateElapsedMs,
  downloadBlob,
  ensureTextFilename,
  fetchAnalysisJobDetails,
  formatDuration,
  formatFileSize,
  formatOptionalScore,
  formatSignedValue,
  formatTimestamp,
  getAnalysisResultPresentation,
  mergeLatestAnalysisAsset,
  normalizeAnalysisProgressState,
  readableChannel,
  readableGeneratedVariantType,
  readableGoalTemplate,
  readableProgressStage,
  resolveAnalysisStageAvailability,
  resolveCurrentStage,
  resolveResultState,
  resolveSuggestedGoalContext,
  resolveVisibleProgressState,
  sanitizeDownloadFilename,
  scrollToSection,
  shortenId,
  stageRows,
  truncateText,
  upsertAnalysisHistoryItem,
} from '../features/analysis/utils'

type AnalysisPageProps = {
  session: AuthSession
  onOpenCompareWorkspace?: () => void
}

const DEMO_CREATIVE_COPY = `Opening hook:
"Your ad is not failing because the product is bad. It is failing because the first three seconds do not create enough reason to keep watching."

Creative concept:
A founder records a direct-response paid social ad for a landing page analytics product. The first scene shows wasted ad spend, the second scene shows a confusing dashboard, and the final scene shows a simple pre-launch creative score.

Target audience:
Performance marketers and small agency founders who need faster creative decisions before launching Meta or TikTok campaigns.

Primary CTA:
Upload your next creative before you spend budget.`

export default function AnalysisPage({ onOpenCompareWorkspace, session }: AnalysisPageProps) {
  const storageScope = session.defaultProjectId || session.email
  const selectedAssetStorageKey = buildSelectedAssetStorageKey(storageScope)
  const selectedJobStorageKey = buildSelectedJobStorageKey(storageScope)
  const wizardStorageKey = buildAnalysisWizardStorageKey(storageScope)
  const compareWorkspaceStorageKey = buildCompareWorkspaceStorageKey(storageScope)
  const storedWizardSnapshot = readAnalysisWizardSnapshot(wizardStorageKey)
  const [config, setConfig] = useState<AnalysisConfigResponse | null>(null)
  const [goalPresets, setGoalPresets] = useState<AnalysisGoalPresetsResponse>(defaultGoalPresets)
  const [configError, setConfigError] = useState<string | null>(null)
  const [goalPresetsError, setGoalPresetsError] = useState<string | null>(null)
  const [selectedMediaType, setSelectedMediaType] = useState<MediaType>(storedWizardSnapshot?.mediaType ?? 'video')
  const [activeWizardStep, setActiveWizardStep] = useState<AnalyzeWizardStep>('upload')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [textContent, setTextContent] = useState('')
  const [textFilename, setTextFilename] = useState('analysis-notes.txt')
  const [objective, setObjective] = useState(storedWizardSnapshot?.objective ?? '')
  const [goalTemplate, setGoalTemplate] = useState(storedWizardSnapshot?.goalTemplate ?? '')
  const [channel, setChannel] = useState(storedWizardSnapshot?.channel ?? '')
  const [audienceSegment, setAudienceSegment] = useState(storedWizardSnapshot?.audienceSegment ?? '')
  const [isDragActive, setIsDragActive] = useState(false)
  const [isLoadingConfig, setIsLoadingConfig] = useState(true)
  const [isLoadingGoalPresets, setIsLoadingGoalPresets] = useState(true)
  const [bannerMessage, setBannerMessage] = useState<BannerMessage | null>(null)
  const [uploadState, setUploadState] = useState<UploadState>({
    stage: 'idle',
    progressPercent: 0,
    validationErrors: [],
  })
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null)
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [analysisPreviewResult, setAnalysisPreviewResult] = useState<AnalysisResult | null>(null)
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgressState | null>(null)
  const [evaluationProgress, setEvaluationProgress] = useState<AnalysisProgressState | null>(null)
  const [assetLibrary, setAssetLibrary] = useState<AnalysisAsset[]>([])
  const [isLoadingAssetLibrary, setIsLoadingAssetLibrary] = useState(false)
  const [isDeletingAssetLibraryItems, setIsDeletingAssetLibraryItems] = useState(false)
  const [hasLoadedAssetLibrary, setHasLoadedAssetLibrary] = useState(false)
  const [assetLibraryError, setAssetLibraryError] = useState<string | null>(null)
  const [assetLibraryRefreshNonce, setAssetLibraryRefreshNonce] = useState(0)
  const [analysisHistory, setAnalysisHistory] = useState<AnalysisJobListItem[]>([])
  const [isLoadingAnalysisHistory, setIsLoadingAnalysisHistory] = useState(false)
  const [isDeletingAnalysisHistoryItems, setIsDeletingAnalysisHistoryItems] = useState(false)
  const [hasLoadedAnalysisHistory, setHasLoadedAnalysisHistory] = useState(false)
  const [analysisHistoryError, setAnalysisHistoryError] = useState<string | null>(null)
  const [analysisHistoryRefreshNonce, setAnalysisHistoryRefreshNonce] = useState(0)
  const [activeLibraryAssetId, setActiveLibraryAssetId] = useState<string | null>(() =>
    readSelectedAnalysisAssetId(selectedAssetStorageKey),
  )
  const [activeHistoryJobId, setActiveHistoryJobId] = useState<string | null>(() =>
    readSelectedAnalysisJobId(selectedJobStorageKey),
  )
  const [selectionMode, setSelectionMode] = useState<AnalysisSelectionMode>(storedWizardSnapshot?.selectionMode ?? 'auto')
  const [loadingHistoryJobId, setLoadingHistoryJobId] = useState<string | null>(null)
  const [pendingHistorySelection, setPendingHistorySelection] = useState<AnalysisJobListItem | null>(null)
  const [analysisTransportMode, setAnalysisTransportMode] = useState<'stream' | 'polling'>('stream')
  const [analysisTransportDiagnostics, setAnalysisTransportDiagnostics] = useState<AnalysisTransportDiagnostics>({
    mode: 'stream',
    isConnected: false,
    reconnectCount: 0,
    lastError: null,
    lastConnectedAt: null,
    lastHeartbeatAt: null,
  })
  const [isHistoryDrawerOpen, setIsHistoryDrawerOpen] = useState(false)
  const [historyDrawerMode, setHistoryDrawerMode] = useState<HistoryDrawerMode>('resume')
  const [isTechnicalDetailsOpen, setIsTechnicalDetailsOpen] = useState(false)
  const [comparisonTarget, setComparisonTarget] = useState<AnalysisJobStatusResponse | null>(null)
  const [comparisonLoadingJobId, setComparisonLoadingJobId] = useState<string | null>(null)
  const [benchmarkResponse, setBenchmarkResponse] = useState<AnalysisBenchmarkResponse | null>(null)
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null)
  const [isLoadingBenchmark, setIsLoadingBenchmark] = useState(false)
  const [executiveVerdict, setExecutiveVerdict] = useState<AnalysisExecutiveVerdict | null>(null)
  const [executiveVerdictError, setExecutiveVerdictError] = useState<string | null>(null)
  const [isLoadingExecutiveVerdict, setIsLoadingExecutiveVerdict] = useState(false)
  const [calibrationResponse, setCalibrationResponse] = useState<AnalysisCalibrationResponse | null>(null)
  const [calibrationError, setCalibrationError] = useState<string | null>(null)
  const [isLoadingCalibration, setIsLoadingCalibration] = useState(false)
  const [generatedVariantsResponse, setGeneratedVariantsResponse] = useState<AnalysisGeneratedVariantListResponse | null>(null)
  const [generatedVariantsError, setGeneratedVariantsError] = useState<string | null>(null)
  const [isLoadingGeneratedVariants, setIsLoadingGeneratedVariants] = useState(false)
  const [isGeneratingVariants, setIsGeneratingVariants] = useState(false)
  const [isImportingOutcomes, setIsImportingOutcomes] = useState(false)
  const firstVisibleResultJobIdRef = useRef<string | null>(null)
  const completedResultJobIdRef = useRef<string | null>(null)
  const streamConnectedJobIdRef = useRef<string | null>(null)
  const streamFallbackJobIdRef = useRef<string | null>(null)
  const autoLoadedInsightsJobIdRef = useRef<string | null>(null)
  const latestInsightsRequestIdRef = useRef(0)
  const autoAppliedGoalAssetIdRef = useRef<string | null>(null)

  const clearGeneratedVariantsState = () => {
    setGeneratedVariantsResponse(null)
    setGeneratedVariantsError(null)
    setIsLoadingGeneratedVariants(false)
    setIsGeneratingVariants(false)
  }

  const sessionToken = session.sessionToken
  const currentMediaOption = mediaTypeOptions.find((option) => option.kind === selectedMediaType) ?? mediaTypeOptions[0]
  const availableGoalTemplates = goalPresets.goal_templates.filter((option) =>
    option.supported_media_types.includes(selectedMediaType),
  )
  const availableChannels = goalPresets.channels.filter((option) =>
    option.supported_media_types.includes(selectedMediaType),
  )
  const groupedGoalTemplates = goalPresets.preset_groups
    .map((group) => ({
      ...group,
      templates: availableGoalTemplates.filter((option) => group.template_values.includes(option.value)),
    }))
    .filter((group) => group.templates.length > 0)
  const suggestedGoalContext = resolveSuggestedGoalContext({
    suggestions: goalPresets.suggestions,
    mediaType: selectedMediaType,
    selectedAsset: uploadState.asset,
    selectedFile,
    textFilename,
  })
  const goalValidationErrors = validateGoalContext({
    channel,
    goalTemplate,
    mediaType: selectedMediaType,
    objective,
    availableChannels,
    availableGoalTemplates,
  })
  const CurrentMediaIcon = currentMediaOption.icon
  const visibleProgress = resolveVisibleProgressState(analysisProgress, evaluationProgress)
  const currentStage = resolveCurrentStage(visibleProgress?.stage, uploadState.stage, analysisJob?.status)
  const hasLocalDraft = selectedMediaType === 'text' ? Boolean(selectedFile || textContent.trim()) : Boolean(selectedFile)
  const hasGoalContext = Boolean(goalTemplate || channel || audienceSegment.trim() || objective.trim())
  const canUpload = Boolean(config && sessionToken && uploadState.stage !== 'uploading')
  const canStartAnalysis =
    Boolean(sessionToken) &&
    uploadState.stage === 'uploaded' &&
    Boolean(uploadState.asset) &&
    goalValidationErrors.length === 0 &&
    analysisJob?.status !== 'queued' &&
    analysisJob?.status !== 'processing'
  const selectedHistoryItem = analysisHistory.find((item) => item.job.id === activeHistoryJobId) ?? null
  const completedComparisonCandidates = analysisHistory.filter(
    (item) => item.has_result && item.job.id !== (analysisJob?.id ?? ''),
  )
  const resultsAsset = analysisResult || analysisJob ? uploadState.asset || selectedHistoryItem?.asset || null : null

  const applyAnalysisSnapshot = useEffectEvent(
    (
      statusResponse: AnalysisJobStatusResponse,
      options?: {
        historyItem?: AnalysisJobListItem | null
        announceSelection?: boolean
      },
    ) => {
      const historyItem = options?.historyItem ?? analysisHistory.find((item) => item.job.id === statusResponse.job.id) ?? null
      const nextAsset =
        statusResponse.asset ??
        historyItem?.asset ??
        (uploadState.asset?.id === statusResponse.job.asset_id ? uploadState.asset : null)
      const normalizedResult = normalizeAnalysisResultForRender(statusResponse.result ?? null)
      const nextProgress = normalizeAnalysisProgressState(statusResponse.job.id, statusResponse.progress)

      if (nextAsset) {
        setActiveLibraryAssetId(nextAsset.id)
        storeSelectedAnalysisAssetId(selectedAssetStorageKey, nextAsset.id)
        setAssetLibrary((current) => mergeLatestAnalysisAsset(current, nextAsset))
        setUploadState((current) => {
          if (
            current.stage === 'uploaded' &&
            current.progressPercent === 100 &&
            current.validationErrors.length === 0 &&
            current.asset?.id === nextAsset.id
          ) {
            return current
          }
          return {
            stage: 'uploaded',
            progressPercent: 100,
            validationErrors: [],
            asset: nextAsset,
          }
        })
      }

      if (nextAsset && nextAsset.media_type !== selectedMediaType) {
        setSelectedMediaType(nextAsset.media_type)
      }
      if (nextAsset?.media_type === 'text' && nextAsset.original_filename) {
        setTextFilename(ensureTextFilename(nextAsset.original_filename))
      }

      setAnalysisJob((current) => (areAnalysisJobsEqual(current, statusResponse.job) ? current : statusResponse.job))
      if (normalizedResult) {
        setAnalysisPreviewResult((current) => (current === null ? current : null))
      } else {
        if (analysisPreviewResult?.job_id && analysisPreviewResult.job_id !== statusResponse.job.id) {
          setAnalysisPreviewResult(null)
        }
      }
      if (nextProgress) {
        setAnalysisProgress((current) => (areAnalysisProgressStatesEqual(current, nextProgress) ? current : nextProgress))
      } else if (analysisProgress?.jobId && analysisProgress.jobId !== statusResponse.job.id) {
        setAnalysisProgress(null)
      } else if (statusResponse.job.status === 'failed') {
        setAnalysisProgress(null)
      }
      if (statusResponse.job.status === 'failed') {
        setAnalysisPreviewResult((current) => (current === null ? current : null))
      }
      setAnalysisResult((current) => (areAnalysisResultsEqual(current, normalizedResult) ? current : normalizedResult))
      setObjective((current) => {
        const nextObjective = statusResponse.job.objective || ''
        return current === nextObjective ? current : nextObjective
      })
      setGoalTemplate((current) => {
        const nextGoalTemplate =
          statusResponse.job.goal_template ||
          normalizedResult?.summary_json.metadata?.goal_template ||
          ''
        return current === nextGoalTemplate ? current : nextGoalTemplate
      })
      setChannel((current) => {
        const nextChannel =
          statusResponse.job.channel ||
          normalizedResult?.summary_json.metadata?.channel ||
          ''
        return current === nextChannel ? current : nextChannel
      })
      setAudienceSegment((current) => {
        const nextAudienceSegment =
          statusResponse.job.audience_segment ||
          normalizedResult?.summary_json.metadata?.audience_segment ||
          ''
        return current === nextAudienceSegment ? current : nextAudienceSegment
      })
      setActiveHistoryJobId(statusResponse.job.id)
      storeSelectedAnalysisJobId(selectedJobStorageKey, statusResponse.job.id)
      setAnalysisHistory((current) =>
        upsertAnalysisHistoryItem(
          current,
          {
            job: statusResponse.job,
            asset: nextAsset,
            has_result: Boolean(normalizedResult),
            result_created_at: normalizedResult?.created_at ?? historyItem?.result_created_at ?? null,
          },
          ANALYSIS_HISTORY_LIMIT,
        ),
      )
      setSelectionMode('job')

      if (statusResponse.job.status === 'failed' && statusResponse.job.error_message) {
        setBannerMessage({
          type: 'error',
          message: statusResponse.job.error_message,
        })
        return
      }

      if (options?.announceSelection) {
        setBannerMessage({
          type: 'info',
          message: `Loaded ${nextAsset?.original_filename || 'analysis run'} from ${formatTimestamp(statusResponse.job.created_at)}.`,
        })
      }
    },
  )

  const applyAnalysisProgress = useEffectEvent((progressEvent: AnalysisProgressEvent) => {
    setAnalysisJob((current) => (areAnalysisJobsEqual(current, progressEvent.job) ? current : progressEvent.job))

    const nextAsset = progressEvent.asset ?? null
    if (nextAsset) {
      setActiveLibraryAssetId(nextAsset.id)
      storeSelectedAnalysisAssetId(selectedAssetStorageKey, nextAsset.id)
      setAssetLibrary((current) => mergeLatestAnalysisAsset(current, nextAsset))
      setUploadState((current) => {
        if (
          current.stage === 'uploaded' &&
          current.progressPercent === 100 &&
          current.validationErrors.length === 0 &&
          current.asset?.id === nextAsset.id
        ) {
          return current
        }
        return {
          stage: 'uploaded',
          progressPercent: 100,
          validationErrors: [],
          asset: nextAsset,
        }
      })
    }
    setActiveHistoryJobId((current) => (current === progressEvent.job.id ? current : progressEvent.job.id))
    storeSelectedAnalysisJobId(selectedJobStorageKey, progressEvent.job.id)
    setAnalysisHistory((current) =>
      upsertAnalysisHistoryItem(
        current,
        {
          job: progressEvent.job,
          asset: nextAsset ?? (uploadState.asset?.id === progressEvent.job.asset_id ? uploadState.asset : null),
          has_result: false,
          result_created_at: null,
        },
        ANALYSIS_HISTORY_LIMIT,
      ),
    )
    setSelectionMode((current) => (current === 'job' ? current : 'job'))

    const previewResult = normalizeAnalysisResultForRender(progressEvent.result ?? null)
    if (previewResult) {
      setAnalysisPreviewResult((current) =>
        areAnalysisResultsEqual(current, previewResult) ? current : previewResult,
      )
    }

    const nextProgress = normalizeAnalysisProgressState(progressEvent.job.id, progressEvent)
    if (nextProgress) {
      setAnalysisProgress((current) => (areAnalysisProgressStatesEqual(current, nextProgress) ? current : nextProgress))
    }
  })

  const handleEvaluationProgressSnapshot = useEffectEvent((progressSnapshot: AnalysisEvaluationProgressSnapshot | null) => {
    if (!progressSnapshot) {
      setEvaluationProgress(null)
      return
    }

    setEvaluationProgress((current) => {
      if (
        current?.jobId === progressSnapshot.jobId &&
        current.stage === progressSnapshot.stage &&
        current.stageLabel === progressSnapshot.stageLabel
      ) {
        return current
      }

      return {
        jobId: progressSnapshot.jobId,
        stage: progressSnapshot.stage,
        stageLabel: progressSnapshot.stageLabel,
        diagnostics:
          analysisProgress?.jobId === progressSnapshot.jobId
            ? analysisProgress.diagnostics
            : current?.diagnostics,
      }
    })
  })

  const loadAnalysisJob = useEffectEvent(async (jobId: string, options?: LoadAnalysisJobOptions) => {
    if (!sessionToken) {
      return
    }

    const historyItem = options?.historyItem ?? analysisHistory.find((item) => item.job.id === jobId) ?? null

    if (options?.showSelectionLoading) {
      setLoadingHistoryJobId(jobId)
    }

    try {
      const statusResponse = await fetchAnalysisJobDetails({
        jobId,
        sessionToken,
      })
      applyAnalysisSnapshot(statusResponse, {
        historyItem,
        announceSelection: options?.announceSelection,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load the selected analysis.',
      })
      void trackAnalysisClientEvent({
        eventName: 'analysis_load_failed',
        goalTemplateValue: historyItem?.job.goal_template || goalTemplate || null,
        channelValue: historyItem?.job.channel || channel || null,
        jobId,
        metadata: {
          source: options?.historyItem ? 'history' : 'direct',
        },
      })
    } finally {
      if (options?.showSelectionLoading) {
        setLoadingHistoryJobId((current) => (current === jobId ? null : current))
      }
    }
  })

  const loadAssetLibrary = useEffectEvent(async () => {
    if (!sessionToken) {
      setAssetLibrary([])
      setAssetLibraryError(null)
      setIsLoadingAssetLibrary(false)
      setHasLoadedAssetLibrary(true)
      return
    }

    setIsLoadingAssetLibrary(true)
    try {
      const response = await apiRequest<AnalysisAssetListResponse>(
        `/api/v1/analysis/assets?media_type=${encodeURIComponent(selectedMediaType)}&limit=12`,
        {
          sessionToken,
        },
      )
      setAssetLibrary(response.items)
      setAssetLibraryError(null)

      const storedAssetId = readSelectedAnalysisAssetId(selectedAssetStorageKey)
      const preferredAssetId =
        activeLibraryAssetId || (selectionMode === 'asset' ? storedAssetId : null)
      const preferredAsset =
        preferredAssetId != null
          ? response.items.find((asset) => asset.id === preferredAssetId && asset.upload_status === 'uploaded')
          : null
      const hasLocalDraft = selectedMediaType === 'text' ? Boolean(selectedFile || textContent.trim()) : Boolean(selectedFile)

      if (
        preferredAsset &&
        !hasLocalDraft &&
        uploadState.stage !== 'uploading' &&
        analysisJob == null &&
        selectionMode === 'asset'
      ) {
        setActiveLibraryAssetId(preferredAsset.id)
        setUploadState((current) =>
          current.asset?.id === preferredAsset.id && current.stage === 'uploaded'
            ? current
            : {
                stage: 'uploaded',
                progressPercent: 100,
                validationErrors: [],
                asset: preferredAsset,
              },
        )
      }
      setHasLoadedAssetLibrary(true)
    } catch (error) {
      setAssetLibraryError(error instanceof Error ? error.message : 'Unable to load uploaded analysis assets.')
      setHasLoadedAssetLibrary(true)
    } finally {
      setIsLoadingAssetLibrary(false)
    }
  })

  const loadAnalysisHistory = useEffectEvent(async () => {
    if (!sessionToken) {
      setAnalysisHistory([])
      setAnalysisHistoryError(null)
      setIsLoadingAnalysisHistory(false)
      setHasLoadedAnalysisHistory(true)
      return
    }

    setIsLoadingAnalysisHistory(true)
    try {
      const response = await apiRequest<AnalysisJobListResponse>(
        `/api/v1/analysis/jobs?media_type=${encodeURIComponent(selectedMediaType)}&limit=${ANALYSIS_HISTORY_LIMIT}`,
        {
          sessionToken,
        },
      )
      setAnalysisHistory(response.items)
      setAnalysisHistoryError(null)
      setHasLoadedAnalysisHistory(true)

      const storedJobId = readSelectedAnalysisJobId(selectedJobStorageKey)
      const preferredJobId =
        activeHistoryJobId || (selectionMode === 'job' ? storedJobId : null)
      const preferredHistoryItem =
        (analysisJob ? response.items.find((item) => item.job.id === analysisJob.id) : null) ||
        (preferredJobId ? response.items.find((item) => item.job.id === preferredJobId) : null) ||
        null

      if (!preferredHistoryItem) {
        setActiveHistoryJobId(null)
        if (selectionMode === 'job') {
          clearSelectedAnalysisJobId(selectedJobStorageKey)
        }
        return
      }

      if (
        selectionMode === 'job' &&
        !analysisJob &&
        !analysisResult &&
        uploadState.stage !== 'uploading' &&
        !hasLocalDraft
      ) {
        await loadAnalysisJob(preferredHistoryItem.job.id, {
          historyItem: preferredHistoryItem,
        })
        return
      }

      setActiveHistoryJobId(preferredHistoryItem.job.id)
      storeSelectedAnalysisJobId(selectedJobStorageKey, preferredHistoryItem.job.id)
    } catch (error) {
      setAnalysisHistoryError(error instanceof Error ? error.message : 'Unable to load recent analyses.')
      setHasLoadedAnalysisHistory(true)
    } finally {
      setIsLoadingAnalysisHistory(false)
    }
  })

  const handleDeleteAnalysisHistoryItems = useEffectEvent(async (jobIds: string[]) => {
    if (!sessionToken || jobIds.length === 0) {
      return
    }

    setIsDeletingAnalysisHistoryItems(true)
    try {
      const response = await apiRequest<AnalysisBulkDeleteResponse>('/api/v1/analysis/jobs', {
        method: 'DELETE',
        sessionToken,
        body: { ids: jobIds },
      })
      const deletedIds = new Set(response.deleted_ids)
      setAnalysisHistory((current) => current.filter((item) => !deletedIds.has(item.job.id)))
      if (analysisJob && deletedIds.has(analysisJob.id)) {
        clearSelectedAnalysisJobId(selectedJobStorageKey)
        setActiveHistoryJobId(null)
        resetWorkflowState(
          setUploadState,
          setAnalysisJob,
          setAnalysisResult,
          setAnalysisPreviewResult,
          setAnalysisProgress,
          setBannerMessage,
        )
        setEvaluationProgress(null)
        setComparisonTarget(null)
        clearGeneratedVariantsState()
      }
      setBannerMessage({
        type: 'success',
        message: `Deleted ${response.deleted_count} analysis ${response.deleted_count === 1 ? 'result' : 'results'}.`,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to delete selected analysis results.',
      })
    } finally {
      setIsDeletingAnalysisHistoryItems(false)
    }
  })

  const handleDeleteAssetLibraryItems = useEffectEvent(async (assetIds: string[]) => {
    if (!sessionToken || assetIds.length === 0) {
      return
    }

    setIsDeletingAssetLibraryItems(true)
    try {
      const response = await apiRequest<AnalysisBulkDeleteResponse>('/api/v1/analysis/assets', {
        method: 'DELETE',
        sessionToken,
        body: { ids: assetIds },
      })
      const deletedIds = new Set(response.deleted_ids)
      setAssetLibrary((current) => current.filter((asset) => !deletedIds.has(asset.id)))
      if (activeLibraryAssetId && deletedIds.has(activeLibraryAssetId)) {
        setActiveLibraryAssetId(null)
        clearSelectedAnalysisAssetId(selectedAssetStorageKey)
      }
      if (uploadState.asset && deletedIds.has(uploadState.asset.id)) {
        setUploadState({
          stage: 'idle',
          progressPercent: 0,
          validationErrors: [],
        })
      }
      setBannerMessage({
        type: 'success',
        message: `Deleted ${response.deleted_count} uploaded ${response.deleted_count === 1 ? 'asset' : 'assets'}.`,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to delete selected uploads.',
      })
    } finally {
      setIsDeletingAssetLibraryItems(false)
    }
  })

  const trackAnalysisClientEvent = useEffectEvent(
    async ({
      eventName,
      goalTemplateValue,
      channelValue,
      jobId,
      metadata,
    }: {
      eventName: AnalysisClientEventName
      goalTemplateValue?: string | null
      channelValue?: string | null
      jobId?: string | null
      metadata?: Record<string, unknown>
    }) => {
      if (!sessionToken) {
        return
      }

      try {
        await apiRequest('/api/v1/analysis/events', {
          method: 'POST',
          sessionToken,
          body: {
            event_name: eventName,
            media_type: selectedMediaType,
            goal_template: goalTemplateValue || null,
            channel: channelValue || null,
            audience_segment: audienceSegment.trim() || null,
            job_id: jobId || null,
            metadata_json: {
              selection_mode: selectionMode,
              transport_mode: analysisTransportMode,
              ...metadata,
            },
          },
        })
      } catch {
        // Client analytics events should never block the analysis workflow.
      }
    },
  )

  const loadAnalysisInsights = useEffectEvent(async (jobId: string) => {
    if (!sessionToken) {
      return
    }

    const requestId = latestInsightsRequestIdRef.current + 1
    latestInsightsRequestIdRef.current = requestId

    setIsLoadingBenchmark(true)
    setIsLoadingExecutiveVerdict(true)
    setIsLoadingCalibration(true)
    setIsLoadingGeneratedVariants(true)
    setBenchmarkError(null)
    setExecutiveVerdictError(null)
    setCalibrationError(null)
    setGeneratedVariantsError(null)

    const [benchmarkResult, verdictResult, calibrationResult, variantsResult] = await Promise.allSettled([
      apiRequest<AnalysisBenchmarkResponse>(`/api/v1/analysis/jobs/${jobId}/benchmarks`, { sessionToken }),
      apiRequest<AnalysisExecutiveVerdict>(`/api/v1/analysis/jobs/${jobId}/verdict`, { sessionToken }),
      apiRequest<AnalysisCalibrationResponse>(`/api/v1/analysis/jobs/${jobId}/calibration`, { sessionToken }),
      apiRequest<AnalysisGeneratedVariantListResponse>(`/api/v1/analysis/jobs/${jobId}/variants`, { sessionToken }),
    ])

    if (latestInsightsRequestIdRef.current !== requestId) {
      return
    }

    if (benchmarkResult.status === 'fulfilled') {
      setBenchmarkResponse(benchmarkResult.value)
    } else {
      setBenchmarkResponse(null)
      setBenchmarkError(
        benchmarkResult.reason instanceof Error
          ? benchmarkResult.reason.message
          : 'Unable to load benchmark context.',
      )
    }

    if (verdictResult.status === 'fulfilled') {
      setExecutiveVerdict(verdictResult.value)
    } else {
      setExecutiveVerdict(null)
      setExecutiveVerdictError(
        verdictResult.reason instanceof Error
          ? verdictResult.reason.message
          : 'Unable to load the executive verdict.',
      )
    }

    if (calibrationResult.status === 'fulfilled') {
      setCalibrationResponse(calibrationResult.value)
    } else {
      setCalibrationResponse(null)
      setCalibrationError(
        calibrationResult.reason instanceof Error
          ? calibrationResult.reason.message
          : 'Unable to load calibration observations.',
      )
    }

    if (variantsResult.status === 'fulfilled') {
      setGeneratedVariantsResponse(variantsResult.value)
    } else {
      setGeneratedVariantsResponse(null)
      setGeneratedVariantsError(
        variantsResult.reason instanceof Error
          ? variantsResult.reason.message
          : 'Unable to load generated variants.',
      )
    }

    setIsLoadingBenchmark(false)
    setIsLoadingExecutiveVerdict(false)
    setIsLoadingCalibration(false)
    setIsLoadingGeneratedVariants(false)
  })

  useEffect(() => {
    storeAnalysisWizardSnapshot(wizardStorageKey, {
      mediaType: selectedMediaType,
      objective,
      goalTemplate,
      channel,
      audienceSegment,
      selectionMode,
    })
  }, [audienceSegment, channel, goalTemplate, objective, selectedMediaType, selectionMode, wizardStorageKey])

  useEffect(() => {
    const availableTemplateValues = new Set(availableGoalTemplates.map((option) => option.value))
    const availableChannelValues = new Set(availableChannels.map((option) => option.value))

    if (goalTemplate && !availableTemplateValues.has(goalTemplate)) {
      setGoalTemplate('')
    }
    if (channel && !availableChannelValues.has(channel)) {
      setChannel('')
    }
  }, [availableChannels, availableGoalTemplates, channel, goalTemplate])

  useEffect(() => {
    if (uploadState.stage !== 'uploaded' || !uploadState.asset) {
      autoAppliedGoalAssetIdRef.current = null
      return
    }

    const assetId = uploadState.asset.id
    if (autoAppliedGoalAssetIdRef.current === assetId) {
      return
    }

    const hasValidGoalTemplate = availableGoalTemplates.some((option) => option.value === goalTemplate)
    const hasValidChannel = availableChannels.some((option) => option.value === channel)
    if (hasValidGoalTemplate && hasValidChannel) {
      autoAppliedGoalAssetIdRef.current = assetId
      return
    }

    const suggestedContext = resolveSuggestedGoalContext({
      suggestions: goalPresets.suggestions,
      mediaType: selectedMediaType,
      selectedAsset: uploadState.asset,
      selectedFile,
      textFilename,
    })
    if (!suggestedContext) {
      return
    }

    const suggestedTemplateSupported = availableGoalTemplates.some(
      (option) => option.value === suggestedContext.goal_template,
    )
    const suggestedChannelSupported = availableChannels.some(
      (option) => option.value === suggestedContext.channel,
    )
    if (!suggestedTemplateSupported || !suggestedChannelSupported) {
      return
    }

    if (!hasValidGoalTemplate) {
      setGoalTemplate(suggestedContext.goal_template)
    }
    if (!hasValidChannel) {
      setChannel(suggestedContext.channel)
    }
    autoAppliedGoalAssetIdRef.current = assetId
  }, [
    availableChannels,
    availableGoalTemplates,
    channel,
    goalPresets.suggestions,
    goalTemplate,
    selectedFile,
    selectedMediaType,
    textFilename,
    uploadState.asset,
    uploadState.stage,
  ])

  useEffect(() => {
    const loadConfig = async () => {
      if (!sessionToken) {
        setConfigError('Sign out and sign in again to enable uploads for this workspace.')
        setIsLoadingConfig(false)
        return
      }

      try {
        const nextConfig = await apiRequest<AnalysisConfigResponse>('/api/v1/analysis/config', {
          sessionToken,
        })
        setConfig(nextConfig)
        setConfigError(null)
      } catch (error) {
        setConfigError(error instanceof Error ? error.message : 'Unable to load analysis upload settings.')
      } finally {
        setIsLoadingConfig(false)
      }
    }

    void loadConfig()
  }, [sessionToken])

  useEffect(() => {
    const loadGoalPresets = async () => {
      if (!sessionToken) {
        setGoalPresets(defaultGoalPresets)
        setGoalPresetsError('Sign out and sign in again to load goal presets for this workspace.')
        setIsLoadingGoalPresets(false)
        return
      }

      try {
        const response = await apiRequest<AnalysisGoalPresetsResponse>('/api/v1/analysis/goal-presets', {
          sessionToken,
        })
        setGoalPresets(response)
        setGoalPresetsError(null)
      } catch (error) {
        setGoalPresets(defaultGoalPresets)
        setGoalPresetsError(error instanceof Error ? error.message : 'Unable to load goal presets. Using local defaults.')
      } finally {
        setIsLoadingGoalPresets(false)
      }
    }

    void loadGoalPresets()
  }, [sessionToken])

  useEffect(() => {
    void loadAssetLibrary()
  }, [assetLibraryRefreshNonce, selectedMediaType, sessionToken])

  useEffect(() => {
    if (hasLoadedAnalysisHistory && analysisHistoryRefreshNonce === 0) {
      return
    }
    const cancelDeferredLoad = runWhenIdle(() => {
      void loadAnalysisHistory()
    })
    return cancelDeferredLoad
  }, [analysisHistoryRefreshNonce, hasLoadedAnalysisHistory, loadAnalysisHistory, selectedMediaType, sessionToken])

  useEffect(() => {
    if (!isHistoryDrawerOpen || isLoadingAnalysisHistory || hasLoadedAnalysisHistory) {
      return
    }
    void loadAnalysisHistory()
  }, [hasLoadedAnalysisHistory, isHistoryDrawerOpen, isLoadingAnalysisHistory, loadAnalysisHistory])

  useEffect(() => {
    setAnalysisTransportMode('stream')
    setAnalysisTransportDiagnostics({
      mode: 'stream',
      isConnected: false,
      reconnectCount: 0,
      lastError: null,
      lastConnectedAt: null,
      lastHeartbeatAt: null,
    })
    streamConnectedJobIdRef.current = null
    streamFallbackJobIdRef.current = null
  }, [analysisJob?.id])

  useEffect(() => {
    setEvaluationProgress(null)
  }, [analysisJob?.id])

  useEffect(() => {
    const resultJobId = analysisResult?.job_id ?? null

    if (!analysisJob?.id || analysisJob.status !== 'completed' || !resultJobId) {
      autoLoadedInsightsJobIdRef.current = null
      latestInsightsRequestIdRef.current += 1
      setBenchmarkResponse(null)
      setExecutiveVerdict(null)
      setCalibrationResponse(null)
      setGeneratedVariantsResponse(null)
      setBenchmarkError(null)
      setExecutiveVerdictError(null)
      setCalibrationError(null)
      setGeneratedVariantsError(null)
      setIsLoadingGeneratedVariants(false)
      setIsGeneratingVariants(false)
      return
    }

    if (autoLoadedInsightsJobIdRef.current === resultJobId) {
      return
    }

    autoLoadedInsightsJobIdRef.current = resultJobId
    void loadAnalysisInsights(resultJobId)
  }, [analysisJob?.id, analysisJob?.status, analysisResult?.job_id])

  useEffect(() => {
    if (!analysisJob || !sessionToken) {
      return
    }
    const hasFinalResultForActiveJob = analysisResult?.job_id === analysisJob.id
    if (analysisJob.status === 'failed') {
      return
    }
    if (analysisJob.status === 'completed' && hasFinalResultForActiveJob) {
      return
    }
    if (analysisJob.status === 'completed' && analysisTransportMode !== 'polling') {
      setAnalysisTransportMode('polling')
    }

    if (analysisTransportMode === 'polling') {
      const intervalId = window.setInterval(() => {
        void loadAnalysisJob(analysisJob.id)
      }, 4_000)

      return () => {
        window.clearInterval(intervalId)
      }
    }

    const unsubscribe = subscribeToEventStream<AnalysisJobStatusResponse | AnalysisProgressEvent>({
      path: `/api/v1/analysis/jobs/${analysisJob.id}/events`,
      sessionToken,
      onMessage: ({ event, data }) => {
        if (streamConnectedJobIdRef.current !== analysisJob.id) {
          streamConnectedJobIdRef.current = analysisJob.id
          setAnalysisTransportDiagnostics((current) => ({
            ...current,
            mode: 'stream',
            isConnected: true,
            lastError: null,
            lastConnectedAt: new Date().toISOString(),
            lastHeartbeatAt: current.lastHeartbeatAt,
          }))
          void trackAnalysisClientEvent({
            eventName: 'analysis_stream_connected',
            goalTemplateValue: analysisJob.goal_template || goalTemplate || null,
            channelValue: analysisJob.channel || channel || null,
            jobId: analysisJob.id,
            metadata: {
              transport_mode: 'stream',
            },
          })
        }
        if (event === 'heartbeat') {
          setAnalysisTransportDiagnostics((current) => ({
            ...current,
            mode: 'stream',
            isConnected: true,
            lastError: null,
            lastHeartbeatAt: new Date().toISOString(),
          }))
          return
        }
        if (event === 'progress') {
          applyAnalysisProgress(data as AnalysisProgressEvent)
          return
        }
        applyAnalysisSnapshot(data as AnalysisJobStatusResponse)
      },
      onError: (error) => {
        setAnalysisTransportMode('polling')
        setAnalysisTransportDiagnostics((current) => ({
          mode: 'polling',
          isConnected: false,
          reconnectCount: current.reconnectCount + 1,
          lastError: error.message,
          lastConnectedAt: current.lastConnectedAt,
          lastHeartbeatAt: current.lastHeartbeatAt,
        }))
        streamConnectedJobIdRef.current = null
        if (streamFallbackJobIdRef.current !== analysisJob.id) {
          streamFallbackJobIdRef.current = analysisJob.id
          void trackAnalysisClientEvent({
            eventName: 'analysis_stream_fallback',
            goalTemplateValue: analysisJob.goal_template || goalTemplate || null,
            channelValue: analysisJob.channel || channel || null,
            jobId: analysisJob.id,
            metadata: {
              transport_mode: 'polling',
              stream_error: error.message,
            },
          })
        }
      },
    })

    return () => {
      unsubscribe()
    }
  // Use primitive deps (id + status) instead of the full object so that progress
  // events — which replace `analysisJob` with a new object of the same id/status —
  // do NOT tear down and re-open the stream on every message.
  }, [analysisJob?.id, analysisJob?.status, analysisResult?.job_id, analysisTransportMode, sessionToken])

  useEffect(() => {
    if (!pendingHistorySelection) {
      return
    }

    const selectedHistoryItem = pendingHistorySelection
    void loadAnalysisJob(selectedHistoryItem.job.id, {
      historyItem: selectedHistoryItem,
      announceSelection: true,
      showSelectionLoading: true,
    }).finally(() => {
      setPendingHistorySelection((current) =>
        current?.job.id === selectedHistoryItem.job.id ? null : current,
      )
    })
  }, [pendingHistorySelection])

  const visibleAnalysisResult = analysisResult ?? analysisPreviewResult
  const stageAvailability = resolveAnalysisStageAvailability({
    analysisResult,
    analysisPreviewResult,
    currentStage,
  })

  useEffect(() => {
    if (!visibleAnalysisResult) {
      return
    }

    const jobId = visibleAnalysisResult.job_id
    if (firstVisibleResultJobIdRef.current === jobId) {
      return
    }

    firstVisibleResultJobIdRef.current = jobId
    void trackAnalysisClientEvent({
      eventName: 'first_result_seen',
      goalTemplateValue:
        analysisJob?.goal_template || visibleAnalysisResult.summary_json?.metadata?.goal_template || goalTemplate || null,
      channelValue:
        analysisJob?.channel || visibleAnalysisResult.summary_json?.metadata?.channel || channel || null,
      jobId,
      metadata: {
        result_kind: analysisResult?.job_id === jobId ? 'final' : 'partial',
        progress_stage: analysisProgress?.stage || null,
        recommendation_count: (visibleAnalysisResult.recommendations_json ?? []).length,
        time_to_first_result_ms:
          analysisProgress?.diagnostics?.timeToFirstResultMs ??
          calculateElapsedMs(analysisJob?.created_at ?? null, visibleAnalysisResult.created_at),
        queue_wait_ms: analysisProgress?.diagnostics?.queueWaitMs ?? null,
        processing_duration_ms: analysisProgress?.diagnostics?.processingDurationMs ?? null,
      },
    })
  }, [
    analysisJob?.channel,
    analysisJob?.goal_template,
    analysisProgress?.diagnostics?.processingDurationMs,
    analysisProgress?.stage,
    analysisResult?.job_id,
    channel,
    goalTemplate,
    trackAnalysisClientEvent,
    visibleAnalysisResult,
  ])

  useEffect(() => {
    if (!analysisResult || analysisJob?.status !== 'completed') {
      return
    }

    const jobId = analysisResult.job_id
    if (completedResultJobIdRef.current === jobId) {
      return
    }

    completedResultJobIdRef.current = jobId
    void trackAnalysisClientEvent({
      eventName: 'analysis_completed',
      goalTemplateValue:
        analysisJob.goal_template || analysisResult.summary_json?.metadata?.goal_template || goalTemplate || null,
      channelValue:
        analysisJob.channel || analysisResult.summary_json?.metadata?.channel || channel || null,
      jobId,
      metadata: {
        recommendation_count: (analysisResult.recommendations_json ?? []).length,
        timeline_points: (analysisResult.timeline_json ?? []).length,
        result_delivery_ms:
          analysisProgress?.diagnostics?.resultDeliveryMs ??
          calculateElapsedMs(analysisJob.created_at, analysisResult.created_at),
        queue_wait_ms: analysisProgress?.diagnostics?.queueWaitMs ?? null,
        processing_duration_ms:
          analysisProgress?.diagnostics?.processingDurationMs ??
          calculateElapsedMs(analysisJob.started_at ?? null, analysisResult.created_at),
      },
    })
  }, [analysisJob, analysisProgress?.diagnostics?.processingDurationMs, analysisProgress?.diagnostics?.queueWaitMs, analysisProgress?.diagnostics?.resultDeliveryMs, analysisResult, channel, goalTemplate, trackAnalysisClientEvent])

  const handleMediaTypeChange = (nextMediaType: MediaType) => {
    if (nextMediaType === selectedMediaType) {
      return
    }

    setSelectedMediaType(nextMediaType)
    setActiveWizardStep('upload')
    setSelectionMode('auto')
    setSelectedFile(null)
    setTextContent('')
    setTextFilename('analysis-notes.txt')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    resetWorkflowState(
      setUploadState,
      setAnalysisJob,
      setAnalysisResult,
      setAnalysisPreviewResult,
      setAnalysisProgress,
      setBannerMessage,
    )
  }

  const handleBinaryFileSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    event.target.value = ''
    setSelectedFile(file)
    setActiveWizardStep('upload')
    setSelectionMode('asset')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    resetWorkflowState(
      setUploadState,
      setAnalysisJob,
      setAnalysisResult,
      setAnalysisPreviewResult,
      setAnalysisProgress,
      setBannerMessage,
    )
  }

  const handleTextFileSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    event.target.value = ''

    setSelectedFile(file)
    setActiveWizardStep('upload')
    setTextContent('')
    setTextFilename(ensureTextFilename(file.name))
    setSelectionMode('asset')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    resetWorkflowState(
      setUploadState,
      setAnalysisJob,
      setAnalysisResult,
      setAnalysisPreviewResult,
      setAnalysisProgress,
      setBannerMessage,
    )
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragActive(false)

    const file = event.dataTransfer.files?.[0]
    if (!file) {
      return
    }

    setSelectedFile(file)
    setActiveWizardStep('upload')
    setSelectionMode('asset')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    resetWorkflowState(
      setUploadState,
      setAnalysisJob,
      setAnalysisResult,
      setAnalysisPreviewResult,
      setAnalysisProgress,
      setBannerMessage,
    )
  }

  const handleSelectUploadedAsset = (asset: AnalysisAsset) => {
    if (asset.upload_status !== 'uploaded') {
      return
    }

    setSelectedFile(null)
    setTextContent('')
    setTextFilename(ensureTextFilename(asset.original_filename || 'analysis-notes.txt'))
    setAnalysisJob(null)
    setAnalysisResult(null)
    setAnalysisPreviewResult(null)
    setAnalysisProgress(null)
    setSelectionMode('asset')
    setActiveLibraryAssetId(asset.id)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    storeSelectedAnalysisAssetId(selectedAssetStorageKey, asset.id)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    setUploadState({
      stage: 'uploaded',
      progressPercent: 100,
      validationErrors: [],
      asset,
    })
    setActiveWizardStep('goal')
    setBannerMessage({
      type: 'info',
      message: `${asset.original_filename || 'Uploaded asset'} is selected from your stored media library.`,
    })
  }

  const handleUpload = async () => {
    if (!config || !sessionToken) {
      return
    }

    setUploadState({
      stage: 'validating',
      progressPercent: 0,
      validationErrors: [],
    })

    const validationErrors = validateCurrentInput({
      config,
      mediaType: selectedMediaType,
      selectedFile,
      textContent,
    })
    if (validationErrors.length > 0) {
      void trackAnalysisClientEvent({
        eventName: 'upload_validation_failed',
        goalTemplateValue: goalTemplate || null,
        channelValue: channel || null,
        metadata: {
          validation_error_count: validationErrors.length,
          validation_errors: validationErrors,
        },
      })
      setUploadState({
        stage: 'failed',
        progressPercent: 0,
        validationErrors,
        errorMessage: validationErrors[0],
      })
      return
    }

    const uploadSource = buildUploadSource({
      mediaType: selectedMediaType,
      selectedFile,
      textContent,
      textFilename,
    })
    if (!uploadSource) {
      return
    }

    setBannerMessage(null)
    setAnalysisJob(null)
    setAnalysisResult(null)
    setAnalysisPreviewResult(null)
    setAnalysisProgress(null)
    setSelectionMode('asset')
    setActiveLibraryAssetId(null)
    setActiveHistoryJobId(null)
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    clearSelectedAnalysisAssetId(selectedAssetStorageKey)
    clearSelectedAnalysisJobId(selectedJobStorageKey)
    setUploadState({
      stage: 'uploading',
      progressPercent: 0,
      validationErrors: [],
    })
    void trackAnalysisClientEvent({
      eventName: 'upload_started',
      goalTemplateValue: goalTemplate || null,
      channelValue: channel || null,
      metadata: {
        file_name: uploadSource.fileName,
        mime_type: uploadSource.mimeType,
        size_bytes: uploadSource.sizeBytes,
        source_kind:
          selectedMediaType === 'text' ? (selectedFile ? 'uploaded_document' : 'draft_text') : 'local_file',
      },
    })

    try {
      const initResponse = await apiRequest<AnalysisUploadCreateResponse>('/api/v1/analysis/uploads', {
        method: 'POST',
        sessionToken,
        body: {
          media_type: selectedMediaType,
          original_filename: uploadSource.fileName,
          mime_type: uploadSource.mimeType,
          size_bytes: uploadSource.sizeBytes,
        },
      })

      let completedResponse: AnalysisUploadCompleteResponse
      let usedBackendFallback = false

      try {
        await uploadToSignedUrl({
          file: uploadSource.file,
          url: initResponse.upload_url,
          contentType: uploadSource.mimeType,
          onProgress: (progressPercent) => {
            setUploadState((current) => ({
              ...current,
              stage: 'uploading',
              progressPercent,
              validationErrors: [],
            }))
          },
        })

        completedResponse = await apiRequest<AnalysisUploadCompleteResponse>(
          `/api/v1/analysis/uploads/${initResponse.upload_session.id}/complete`,
          {
            method: 'POST',
            sessionToken,
            body: {
              upload_token: initResponse.upload_session.upload_token,
            },
          },
        )
      } catch (directUploadError) {
        usedBackendFallback = true
        setBannerMessage({
          type: 'info',
          message: 'Direct browser upload was blocked. Retrying through the backend upload proxy.',
        })
        completedResponse = await uploadToApi<AnalysisUploadCompleteResponse>({
          path: `/api/v1/analysis/uploads/${initResponse.upload_session.id}/fallback`,
          sessionToken,
          file: uploadSource.file,
          fileName: uploadSource.fileName,
          fields: {
            upload_token: initResponse.upload_session.upload_token,
          },
          onProgress: (progressPercent) => {
            setUploadState((current) => ({
              ...current,
              stage: 'uploading',
              progressPercent,
              validationErrors: [],
            }))
          },
        }).catch((fallbackError) => {
          const directMessage =
            directUploadError instanceof Error ? directUploadError.message : 'Direct upload failed.'
          const fallbackMessage =
            fallbackError instanceof Error ? fallbackError.message : 'Backend upload failed.'
          throw new Error(`${directMessage} Fallback upload also failed: ${fallbackMessage}`)
        })
      }

      setUploadState({
        stage: 'uploaded',
        progressPercent: 100,
        validationErrors: [],
        asset: completedResponse.asset,
        uploadSession: completedResponse.upload_session,
      })
      setActiveWizardStep('goal')
      setSelectionMode('asset')
      setActiveLibraryAssetId(completedResponse.asset.id)
      storeSelectedAnalysisAssetId(selectedAssetStorageKey, completedResponse.asset.id)
      setAssetLibrary((current) => mergeLatestAnalysisAsset(current, completedResponse.asset))
      setBannerMessage({
        type: usedBackendFallback ? 'info' : 'success',
        message: usedBackendFallback
          ? 'Upload completed through the backend proxy. The asset is ready to queue for analysis.'
          : 'Upload completed. The asset is ready to queue for analysis.',
      })
      void trackAnalysisClientEvent({
        eventName: 'upload_completed',
        goalTemplateValue: goalTemplate || null,
        channelValue: channel || null,
        metadata: {
          asset_id: completedResponse.asset.id,
          upload_session_id: completedResponse.upload_session.id,
          used_backend_fallback: usedBackendFallback,
        },
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Upload failed.'
      setUploadState({
        stage: 'failed',
        progressPercent: 0,
        validationErrors: [message],
        errorMessage: message,
      })
      setBannerMessage({
        type: 'error',
        message,
      })
    }
  }

  const handleStartAnalysis = async () => {
    if (!sessionToken || !uploadState.asset) {
      return
    }

    const isRetry = analysisJob?.status === 'failed'
    setBannerMessage(null)
    clearGeneratedVariantsState()
    setAnalysisPreviewResult(null)
    setAnalysisProgress(null)
    try {
      const response = await apiRequest<AnalysisJobStatusResponse>('/api/v1/analysis/jobs', {
        method: 'POST',
        sessionToken,
        body: {
          asset_id: uploadState.asset.id,
          objective: objective.trim() || null,
          goal_template: goalTemplate || null,
          channel: channel || null,
          audience_segment: audienceSegment.trim() || null,
        },
      })
      const normalizedResult = normalizeAnalysisResultForRender(response.result ?? null)
      setAnalysisJob(response.job)
      setAnalysisResult(normalizedResult)
      setActiveWizardStep('results')
      if (response.asset) {
        setUploadState((current) => ({
          ...current,
          stage: 'uploaded',
          progressPercent: 100,
          validationErrors: [],
          asset: response.asset || current.asset,
        }))
      }
      setSelectionMode('job')
      setActiveHistoryJobId(response.job.id)
      storeSelectedAnalysisJobId(selectedJobStorageKey, response.job.id)
      setAnalysisHistory((current) =>
        upsertAnalysisHistoryItem(
          current,
          {
            job: response.job,
            asset: uploadState.asset || null,
            has_result: Boolean(normalizedResult),
            result_created_at: normalizedResult?.created_at ?? null,
          },
          ANALYSIS_HISTORY_LIMIT,
        ),
      )
      void trackAnalysisClientEvent({
        eventName: isRetry ? 'analysis_retry_clicked' : 'analysis_started',
        goalTemplateValue: response.job.goal_template || goalTemplate || null,
        channelValue: response.job.channel || channel || null,
        jobId: response.job.id,
        metadata: {
          asset_id: uploadState.asset.id,
          objective_length: objective.trim().length,
        },
      })
      setBannerMessage({
        type: 'info',
        message:
          response.job.status === 'queued'
            ? 'Analysis job queued. Status will update automatically.'
            : 'Analysis job started.',
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to queue the analysis job.',
      })
    }
  }

  const handleSelectAnalysisHistoryItem = (item: AnalysisJobListItem) => {
    setSelectedFile(null)
    setTextContent('')
    setSelectionMode('job')
    setComparisonTarget(null)
    clearGeneratedVariantsState()
    setAnalysisResult(null)
    setAnalysisPreviewResult(null)
    setAnalysisProgress(null)
    setEvaluationProgress(null)
    if (item.asset?.media_type === 'text' && item.asset.original_filename) {
      setTextFilename(ensureTextFilename(item.asset.original_filename))
    }
    setIsHistoryDrawerOpen(false)
    setActiveWizardStep('results')
    setPendingHistorySelection(item)
  }

  const openHistoryDrawer = (mode: HistoryDrawerMode = 'resume') => {
    setHistoryDrawerMode(mode)
    setIsHistoryDrawerOpen(true)
    if (mode === 'compare') {
      void trackAnalysisClientEvent({
        eventName: 'quick_compare_opened',
        goalTemplateValue: goalTemplate || analysisJob?.goal_template || null,
        channelValue: channel || analysisJob?.channel || null,
        jobId: analysisJob?.id ?? null,
      })
    }
  }

  const handleSelectComparisonTarget = async (item: AnalysisJobListItem) => {
    if (!sessionToken || item.job.id === analysisJob?.id) {
      return
    }

    setComparisonLoadingJobId(item.job.id)
    try {
      const statusResponse = await fetchAnalysisJobDetails({
        jobId: item.job.id,
        sessionToken,
      })
      setComparisonTarget({
        ...statusResponse,
        asset: statusResponse.asset ?? item.asset ?? null,
        result: normalizeAnalysisResultForRender(statusResponse.result ?? null),
      })
      setIsHistoryDrawerOpen(false)
      setBannerMessage({
        type: 'info',
        message: `Prepared a quick comparison against ${item.asset?.original_filename || shortenId(item.job.id)}.`,
      })
      void trackAnalysisClientEvent({
        eventName: 'quick_compare_loaded',
        goalTemplateValue: goalTemplate || analysisJob?.goal_template || statusResponse.job.goal_template || null,
        channelValue: channel || analysisJob?.channel || statusResponse.job.channel || null,
        jobId: statusResponse.job.id,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load the comparison target.',
      })
    } finally {
      setComparisonLoadingJobId((current) => (current === item.job.id ? null : current))
    }
  }

  const handleExportCurrentAnalysis = () => {
    if (!analysisJob || !analysisResult) {
      return
    }

    void trackAnalysisClientEvent({
      eventName: 'export_clicked',
      goalTemplateValue: analysisJob.goal_template || goalTemplate || null,
      channelValue: analysisJob.channel || channel || null,
      jobId: analysisJob.id,
      metadata: {
        recommendation_count: (analysisResult.recommendations_json ?? []).length,
      },
    })

    const summary = analysisResult.summary_json
    const recommendations = (analysisResult.recommendations_json ?? []).slice(0, 5)
    const strongestMetrics = [...(analysisResult.metrics_json ?? [])]
      .sort((left, right) => right.value - left.value)
      .slice(0, 5)
    const weakestSegments = [...(analysisResult.segments_json ?? [])]
      .sort((left, right) => left.attention_score - right.attention_score)
      .slice(0, 3)
    const verdict =
      executiveVerdict?.headline ||
      (summary.overall_attention_score >= 72
        ? 'Ship with monitoring'
        : summary.overall_attention_score >= 55
          ? 'Iterate before spend'
          : 'High risk: fix before launch')
    const benchmarkLine = benchmarkResponse
      ? `${benchmarkResponse.cohort_label} (${benchmarkResponse.cohort_size} peer runs)`
      : 'Benchmark pending'
    const calibrationLine = calibrationResponse?.summary.observation_count
      ? `${calibrationResponse.summary.observation_count} imported outcome observations`
      : 'No imported outcome calibration yet'

    const reportMarkdown = [
      `# NeuroMarketer Creative Analysis Report`,
      '',
      `**Verdict:** ${verdict}`,
      `**Exported:** ${new Date().toISOString()}`,
      `**Workspace:** ${session.organizationName || 'Primary workspace'}`,
      `**Project:** ${session.defaultProjectName || 'Default Analysis Project'}`,
      `**Asset:** ${resultsAsset?.original_filename || resultsAsset?.object_key || 'Selected creative'}`,
      `**Channel:** ${analysisJob.channel ? readableChannel(analysisJob.channel) : 'Not specified'}`,
      `**Goal:** ${analysisJob.goal_template ? readableGoalTemplate(analysisJob.goal_template) : 'Not specified'}`,
      '',
      '## Executive Summary',
      executiveVerdict?.summary ||
        'This is a directional pre-flight read. Import post-launch outcomes before treating it as calibrated performance proof.',
      '',
      '## Key Scores',
      `- Overall attention: ${summary.overall_attention_score.toFixed(1)}/100`,
      `- Hook strength first 3 seconds: ${summary.hook_score_first_3_seconds.toFixed(1)}/100`,
      `- Sustained engagement: ${summary.sustained_engagement_score.toFixed(1)}/100`,
      `- Memory proxy: ${summary.memory_proxy_score.toFixed(1)}/100`,
      `- Cognitive load risk: ${summary.cognitive_load_proxy.toFixed(1)}/100`,
      `- Confidence: ${formatOptionalScore(summary.confidence)}`,
      '',
      '## Benchmark And Calibration Context',
      `- Benchmark: ${benchmarkLine}`,
      `- Calibration: ${calibrationLine}`,
      '',
      '## Strongest Metrics',
      ...(strongestMetrics.length
        ? strongestMetrics.map(
            (metric) =>
              `- ${metric.label}: ${metric.value.toFixed(metric.unit === 'seconds' ? 2 : 1)} ${metric.unit} - ${metric.detail || metric.source}`,
          )
        : ['- Metrics unavailable.']),
      '',
      '## Fix First',
      ...(recommendations.length
        ? recommendations.map((recommendation) => {
            const timestamp =
              recommendation.timestamp_ms != null ? `${formatDuration(recommendation.timestamp_ms)} - ` : ''
            return `- ${timestamp}${recommendation.title}: ${recommendation.detail}`
          })
        : ['- No recommendations were generated. Review low-attention intervals manually.']),
      '',
      '## Weakest Attention Windows',
      ...(weakestSegments.length
        ? weakestSegments.map(
            (segment) =>
              `- ${segment.label} (${formatDuration(segment.start_time_ms)}-${formatDuration(segment.end_time_ms)}): attention ${segment.attention_score.toFixed(1)}/100. ${segment.note}`,
          )
        : ['- Segment data unavailable.']),
      '',
      '## Method Note',
      'NeuroMarketer combines TRIBE v2 multimodal event extraction, internal post-processing, benchmark context, and optional LLM critique. Scores are decision support, not guaranteed campaign outcomes.',
      '',
    ].join('\n')

    const fileStem = sanitizeDownloadFilename(resultsAsset?.original_filename || `analysis-${analysisJob.id}`)
    downloadBlob({
      filename: `${fileStem}-neuromarketer-report.md`,
      mimeType: 'text/markdown',
      content: reportMarkdown,
    })
    setBannerMessage({
      type: 'success',
      message: 'Downloaded a shareable Markdown analysis report.',
    })
  }

  const handleGenerateVariants = async () => {
    if (!analysisJob || !analysisResult || !sessionToken) {
      return
    }

    setIsGeneratingVariants(true)
    setGeneratedVariantsError(null)
    try {
      const response = await apiRequest<AnalysisGeneratedVariantListResponse>(
        `/api/v1/analysis/jobs/${analysisJob.id}/variants`,
        {
          method: 'POST',
          sessionToken,
          body: {
            variant_types: ['hook_rewrite', 'cta_rewrite', 'shorter_script', 'alternate_thumbnail'],
            replace_existing: true,
          },
        },
      )
      setGeneratedVariantsResponse(response)
      setBannerMessage({
        type: 'success',
        message: `Generated ${response.items.length} action-ready variant${response.items.length === 1 ? '' : 's'} from the current analysis.`,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to generate action-ready variants.'
      setGeneratedVariantsError(message)
      setBannerMessage({
        type: 'error',
        message,
      })
    } finally {
      setIsGeneratingVariants(false)
    }
  }

  const handleDownloadGeneratedVariant = (variant: AnalysisGeneratedVariant) => {
    if (!analysisJob) {
      return
    }

    const fileStem = sanitizeDownloadFilename(resultsAsset?.original_filename || `analysis-${analysisJob.id}`)
    downloadBlob({
      filename: `${fileStem}-${variant.variant_type}.txt`,
      mimeType: 'text/plain;charset=utf-8',
      content: buildGeneratedVariantText({
        asset: resultsAsset,
        job: analysisJob,
        variant,
      }),
    })
  }

  const handleCopyGeneratedVariant = async (variant: AnalysisGeneratedVariant) => {
    if (!analysisJob || !navigator.clipboard) {
      return
    }

    try {
      await navigator.clipboard.writeText(
        buildGeneratedVariantText({
          asset: resultsAsset,
          job: analysisJob,
          variant,
        }),
      )
      setBannerMessage({
        type: 'success',
        message: `Copied the ${readableGeneratedVariantType(variant.variant_type)} to the clipboard.`,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to copy the generated variant.',
      })
    }
  }

  const handleImportOutcomeFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !sessionToken || !analysisJob) {
      return
    }

    setIsImportingOutcomes(true)
    try {
      const response = await uploadToApi<AnalysisOutcomeImportResponse>({
        path: '/api/v1/analysis/outcomes/import',
        sessionToken,
        file,
        fileName: file.name,
      })
      await loadAnalysisInsights(analysisJob.id)
      setBannerMessage({
        type: response.failed_rows > 0 ? 'info' : 'success',
        message:
          response.failed_rows > 0
            ? `Imported ${response.imported_events} outcomes and ${response.imported_observations} calibration observations. ${response.failed_rows} rows were skipped.`
            : `Imported ${response.imported_events} outcomes and ${response.imported_observations} calibration observations.`,
      })
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to import the CSV outcome file.',
      })
    } finally {
      setIsImportingOutcomes(false)
    }
  }

  const handleApplySuggestedGoalContext = () => {
    if (!suggestedGoalContext) {
      return
    }

    setGoalTemplate(suggestedGoalContext.goal_template)
    setChannel(suggestedGoalContext.channel)
    setBannerMessage({
      type: 'info',
      message: `Applied the recommended ${readableGoalTemplate(suggestedGoalContext.goal_template)} setup for this ${selectedMediaType} asset.`,
    })
    void trackAnalysisClientEvent({
      eventName: 'goal_suggestion_applied',
      goalTemplateValue: suggestedGoalContext.goal_template,
      channelValue: suggestedGoalContext.channel,
      jobId: analysisJob?.id ?? null,
    })
  }

  const summary = visibleAnalysisResult?.summary_json ?? placeholderSummary
  const resultMediaType = visibleAnalysisResult?.summary_json?.modality ?? resultsAsset?.media_type ?? selectedMediaType
  const resultPresentation = getAnalysisResultPresentation(resultMediaType)
  const timelinePoints = visibleAnalysisResult?.timeline_json ?? placeholderTimeline
  const segmentsRows = visibleAnalysisResult?.segments_json ?? placeholderSegments
  const heatmapFrames = visibleAnalysisResult?.visualizations_json?.heatmap_frames ?? placeholderHeatmapFrames
  const frameBreakdownItems = buildFrameBreakdownItems({
    timelinePoints,
    segmentsRows,
    heatmapFrames,
    mediaType: resultMediaType,
  })
  const highAttentionIntervals = visibleAnalysisResult?.visualizations_json?.high_attention_intervals ?? []
  const lowAttentionIntervals = visibleAnalysisResult?.visualizations_json?.low_attention_intervals ?? []
  const recommendations = visibleAnalysisResult?.recommendations_json ?? []
  const summaryCards = buildSummaryCards(summary)
  const resultState = resolveResultState({
    analysisJob,
    analysisResult,
    analysisPreviewResult,
    uploadState,
  })
  const analysisCompleted = Boolean(analysisResult)
  const isVideoResult = resultMediaType === 'video'
  const isAnalysisRunning = analysisJob?.status === 'queued' || analysisJob?.status === 'processing'
  const evaluationJobId = analysisJob?.id ?? analysisResult?.job_id ?? null
  const summarySectionMessage = buildScoringPendingMessage(stageAvailability, currentStage)
  const sceneSectionMessage = buildScenePendingMessage(stageAvailability, currentStage)
  const recommendationsSectionMessage = buildRecommendationsPendingMessage(stageAvailability, currentStage)

  return (
    <Stack className="analyze-page" spacing={3}>
      <Box className="analyze-page__shell">
        <Stack className="analyze-page__header" spacing={2.5}>
          <Stack alignItems={{ xs: 'flex-start', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={2}>
            <Box>
              <Typography variant="h5">Analyze Creative Performance</Typography>
              <Typography color="text.secondary" variant="body2">
                Upload video, audio, or text, choose a review goal, and run an AI creative analysis.
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Button onClick={() => openHistoryDrawer('resume')} startIcon={<HistoryRounded />} variant="outlined">
                Recent analyses
              </Button>
              <Button onClick={() => setIsTechnicalDetailsOpen(true)} startIcon={<TuneRounded />} variant="text">
                View technical details
              </Button>
            </Stack>
          </Stack>

          <AnalyzeStepper
            activeStep={activeWizardStep}
            hasGoalContext={goalValidationErrors.length === 0 && hasGoalContext}
            hasResults={analysisCompleted}
            hasStoredAsset={uploadState.stage === 'uploaded' || hasLocalDraft}
            onStepChange={setActiveWizardStep}
          />
        </Stack>

        {bannerMessage ? <Alert severity={bannerMessage.type}>{bannerMessage.message}</Alert> : null}
        {configError ? <Alert severity="error">{configError}</Alert> : null}
        {isLoadingConfig ? <Alert severity="info">Loading analysis upload settings…</Alert> : null}

        {activeWizardStep === 'upload' ? (
          <UploadStep
            CurrentMediaIcon={CurrentMediaIcon}
            activeLibraryAssetId={activeLibraryAssetId}
            assetLibrary={assetLibrary}
            assetLibraryError={assetLibraryError}
            canUpload={canUpload}
            config={config}
            currentMediaOption={currentMediaOption}
            hasLoadedAssetLibrary={hasLoadedAssetLibrary}
            isDragActive={isDragActive}
            isLoadingAssetLibrary={isLoadingAssetLibrary}
            isDeletingAssets={isDeletingAssetLibraryItems}
            onBinaryFileSelection={handleBinaryFileSelection}
            onDeleteAssets={handleDeleteAssetLibraryItems}
            onDrop={handleDrop}
            onMediaTypeChange={handleMediaTypeChange}
            onReloadAssets={() => setAssetLibraryRefreshNonce((current) => current + 1)}
            onSelectAsset={handleSelectUploadedAsset}
            onTextChange={(value) => {
              setSelectedFile(null)
              setActiveWizardStep('upload')
              setTextContent(value)
              setTextFilename('analysis-notes.txt')
              setSelectionMode(value.trim() ? 'asset' : 'auto')
              setActiveHistoryJobId(null)
              setComparisonTarget(null)
              clearGeneratedVariantsState()
              clearSelectedAnalysisAssetId(selectedAssetStorageKey)
              clearSelectedAnalysisJobId(selectedJobStorageKey)
              resetWorkflowState(
                setUploadState,
                setAnalysisJob,
                setAnalysisResult,
                setAnalysisPreviewResult,
                setAnalysisProgress,
                setBannerMessage,
              )
            }}
            onTextFileSelection={handleTextFileSelection}
            onToggleDrag={setIsDragActive}
            onUpload={handleUpload}
            selectedAsset={uploadState.asset}
            selectedFile={selectedFile}
            selectedMediaType={selectedMediaType}
            textContent={textContent}
            textFilename={textFilename}
            uploadState={uploadState}
          />
        ) : null}

        {activeWizardStep === 'goal' ? (
          <GoalStep
            audienceSegment={audienceSegment}
            availableChannels={availableChannels}
            channel={channel}
            goalTemplate={goalTemplate}
            goalValidationErrors={goalValidationErrors}
            groupedGoalTemplates={groupedGoalTemplates}
            isLoadingGoalPresets={isLoadingGoalPresets}
            goalPresetsError={goalPresetsError}
            objective={objective}
            onApplySuggestion={handleApplySuggestedGoalContext}
            onAudienceSegmentChange={setAudienceSegment}
            onBack={() => setActiveWizardStep('upload')}
            onChannelChange={setChannel}
            onGoalTemplateChange={(value, defaultChannel) => {
              setGoalTemplate((current) => (current === value ? '' : value))
              if (defaultChannel && availableChannels.some((option) => option.value === defaultChannel)) {
                setChannel((current) => current || defaultChannel)
              }
            }}
            onNext={() => setActiveWizardStep('review')}
            onObjectiveChange={setObjective}
            suggestedGoalContext={suggestedGoalContext}
            uploadReady={uploadState.stage === 'uploaded'}
          />
        ) : null}

        {activeWizardStep === 'review' ? (
          <ReviewRunStep
            analysisJob={analysisJob}
            canStartAnalysis={canStartAnalysis}
            channel={channel}
            goalTemplate={goalTemplate}
            goalValidationErrors={goalValidationErrors}
            onBack={() => setActiveWizardStep('goal')}
            onStartAnalysis={handleStartAnalysis}
            selectedAsset={uploadState.asset}
            selectedMediaType={selectedMediaType}
          />
        ) : null}

        {activeWizardStep === 'results' && !analysisCompleted ? (
          <ProcessingStatus
            analysisJob={analysisJob}
            currentStage={currentStage}
            isRunning={isAnalysisRunning}
            onBack={() => setActiveWizardStep('review')}
            onOpenDetails={() => setIsTechnicalDetailsOpen(true)}
            progress={visibleProgress}
            resultState={resultState}
          />
        ) : null}
      </Box>

      {activeWizardStep === 'results' && analysisCompleted ? (
        <ResultsStep>
          <ResultStateBanner
            analysisJob={analysisJob}
            diagnostics={analysisTransportDiagnostics}
            progressLabel={analysisProgress?.stageLabel ?? null}
            resultState={resultState}
            sessionToken={sessionToken}
            onRerunSuccess={(updatedJob) => {
              setAnalysisJob(updatedJob)
            }}
          />

          <ExecutiveVerdictCard
            benchmark={benchmarkResponse}
            benchmarkError={benchmarkError}
            calibration={calibrationResponse}
            executiveVerdict={executiveVerdict}
            executiveVerdictError={executiveVerdictError}
            hasResults={Boolean(analysisResult)}
            isLoadingBenchmark={isLoadingBenchmark}
            isLoadingExecutiveVerdict={isLoadingExecutiveVerdict}
            recommendations={recommendations}
            summary={summary}
          />

          <ResultsActionHub
        analysisJob={analysisJob}
        analysisResult={analysisResult}
        compareCandidateCount={completedComparisonCandidates.length}
        generatedVariantCount={generatedVariantsResponse?.items.length ?? 0}
        isGeneratingVariants={isGeneratingVariants}
        onCompare={() => {
          void trackAnalysisClientEvent({
            eventName: 'compare_clicked',
            goalTemplateValue: analysisJob?.goal_template || goalTemplate || null,
            channelValue: analysisJob?.channel || channel || null,
            jobId: analysisJob?.id ?? null,
            metadata: {
              compare_candidate_count: completedComparisonCandidates.length,
              comparison_entry_point: onOpenCompareWorkspace ? 'workspace' : 'quick_compare',
            },
          })
          if (analysisJob?.id && onOpenCompareWorkspace) {
            storeCompareWorkspaceSnapshot(compareWorkspaceStorageKey, {
              selectedJobIds: [analysisJob.id],
              baselineJobId: analysisJob.id,
              activeComparisonId: null,
            })
            onOpenCompareWorkspace()
            return
          }
          openHistoryDrawer('compare')
        }}
        onExport={handleExportCurrentAnalysis}
        onGenerate={handleGenerateVariants}
      />

      {comparisonTarget?.result && analysisResult ? (
        <QuickComparisonCard
          baselineAsset={resultsAsset}
          baselineJob={analysisJob}
          baselineResult={analysisResult}
          comparisonAsset={comparisonTarget.asset ?? null}
          comparisonJob={comparisonTarget.job}
          comparisonResult={comparisonTarget.result}
          onClear={() => setComparisonTarget(null)}
        />
      ) : null}

      <Accordion className="analysis-compact-accordion" elevation={0}>
        <AccordionSummary expandIcon={<ExpandMoreRounded />}>
          <Box>
            <Typography variant="h6">Advanced actions</Typography>
            <Typography color="text.secondary" variant="body2">
              Variants, diagnostics, calibration, benchmarks, and review operations.
            </Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={3}>
            <GeneratedVariantsPanel
              asset={resultsAsset}
              errorMessage={generatedVariantsError}
              hasResults={Boolean(analysisResult)}
              isGenerating={isGeneratingVariants}
              isLoading={isLoadingGeneratedVariants}
              items={generatedVariantsResponse?.items ?? []}
              job={analysisJob}
              onCopy={handleCopyGeneratedVariant}
              onDownload={handleDownloadGeneratedVariant}
              onGenerate={handleGenerateVariants}
            />

            <Box className="dashboard-grid dashboard-grid--content">
              <AnalysisTransportDiagnosticsCard
                analysisJob={analysisJob}
                diagnostics={analysisTransportDiagnostics}
                progress={visibleProgress}
              />
            </Box>

            <Box className="dashboard-grid dashboard-grid--content">
              <BenchmarkPercentilesCard
                benchmark={benchmarkResponse}
                errorMessage={benchmarkError}
                hasResults={Boolean(analysisResult)}
                isLoading={isLoadingBenchmark}
              />

              <CalibrationPanel
                calibration={calibrationResponse}
                errorMessage={calibrationError}
                hasResults={Boolean(analysisResult)}
                isImporting={isImportingOutcomes}
                isLoading={isLoadingCalibration}
                onImportCsv={handleImportOutcomeFile}
              />
            </Box>

            <Suspense fallback={<DeferredPanelFallback title="Review ops" />}>
              <CollaborationPanel
                allowTimestampComments
                entityId={analysisJob?.id ?? null}
                entityType="analysis_job"
                session={session}
                subtitle="Keep review status, assignee handoff, and approval state attached to this run."
                title="Review ops"
              />
            </Suspense>
          </Stack>
        </AccordionDetails>
      </Accordion>

      <Box className="dashboard-grid dashboard-grid--metrics analysis-summary-grid">
        {summaryCards.map((card) => (
          <Paper className="dashboard-card dashboard-card--metric" elevation={0} key={card.key}>
            <Stack spacing={1.5}>
              <Typography color="text.secondary" variant="overline">
                {card.label}
              </Typography>
              <ScoreGauge isReady={stageAvailability.primaryScoringReady} label="" size={80} value={card.value} />
              <Typography color="text.secondary" variant="body2">
                {stageAvailability.primaryScoringReady ? card.helper : summarySectionMessage}
              </Typography>
            </Stack>
          </Paper>
        ))}
      </Box>

      {!isVideoResult ? (
        <MinimalModalityResults
          asset={resultsAsset}
          heatmapFrames={heatmapFrames}
          highAttentionIntervals={highAttentionIntervals}
          lowAttentionIntervals={lowAttentionIntervals}
          isReady={stageAvailability.primaryScoringReady}
          loadingLabel={summarySectionMessage}
          mediaType={resultMediaType}
          recommendations={recommendations}
          segments={segmentsRows}
          summary={summary}
          timelinePoints={timelinePoints}
        />
      ) : null}

      {isVideoResult ? (
      <Accordion className="analysis-compact-accordion" elevation={0}>
        <AccordionSummary expandIcon={<ExpandMoreRounded />}>
          <Box>
            <Typography variant="h6">Advanced scoring details</Typography>
            <Typography color="text.secondary" variant="body2">
              Signal summary, timeline, key moments, and a compact diagnostic matrix.
            </Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={3}>
            <Box className="dashboard-grid dashboard-grid--content">
              <SignalSummaryCard
                cards={summaryCards}
                isReady={stageAvailability.primaryScoringReady}
                loadingLabel={summarySectionMessage}
              />

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">{resultPresentation.timelineTitle}</Typography>
            <Typography color="text.secondary" variant="body2">
              {resultPresentation.timelineDescription} Scene boundaries and high/low attention bands are overlaid for faster diagnosis.
            </Typography>
            {stageAvailability.primaryScoringReady ? (
              <TimelineChart
                points={timelinePoints}
                segments={segmentsRows}
                highAttentionIntervals={highAttentionIntervals}
                lowAttentionIntervals={lowAttentionIntervals}
              />
            ) : (
              <TimelineChartSkeleton label={summarySectionMessage} />
            )}
          </Stack>
        </Paper>
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Key moments</Typography>
            <Typography color="text.secondary" variant="body2">
              Highest peaks, weakest dips, and opening moments selected from the processed timeline.
            </Typography>
            <VideoFrameStrip
              frames={frameBreakdownItems}
              hasResults={stageAvailability.sceneStructureReady}
              isScoringReady={stageAvailability.primaryScoringReady}
              asset={resultsAsset}
              presentation={resultPresentation}
              sessionToken={sessionToken || null}
            />
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">{resultPresentation.matrixTitle}</Typography>
            <Typography color="text.secondary" variant="body2">
              {resultPresentation.matrixDescription} Rows are sorted by weakest decision signal first.
            </Typography>
            <SignalMatrixCard
              segments={segmentsRows}
              isReady={stageAvailability.sceneStructureReady && stageAvailability.primaryScoringReady}
            />
          </Stack>
        </Paper>
      </Box>

      <Accordion className="analysis-compact-accordion" elevation={0}>
        <AccordionSummary expandIcon={<ExpandMoreRounded />}>
          <Box>
            <Typography variant="subtitle1">Raw scene details</Typography>
            <Typography color="text.secondary" variant="body2">
              Full segment table kept for audit and export checks.
            </Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={2}>
            <SegmentHeatstrip
              segments={segmentsRows}
              isReady={stageAvailability.sceneStructureReady && stageAvailability.primaryScoringReady}
            />
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{resultPresentation.segmentFallbackPrefix}</TableCell>
                  <TableCell>Window</TableCell>
                  <TableCell align="right">Attention</TableCell>
                  <TableCell align="right">Delta</TableCell>
                  <TableCell>Note</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {stageAvailability.sceneStructureReady
                  ? segmentsRows.map((segment) => (
                      <TableRow key={`${segment.label}-${segment.start_time_ms}`}>
                        <TableCell>{segment.label}</TableCell>
                        <TableCell>
                          {formatDuration(segment.start_time_ms)} - {formatDuration(segment.end_time_ms)}
                        </TableCell>
                        <TableCell align="right">
                          {stageAvailability.primaryScoringReady ? (
                            Math.round(segment.attention_score)
                          ) : (
                            <Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={44} />
                          )}
                        </TableCell>
                        <TableCell align="right">
                          {stageAvailability.primaryScoringReady ? (
                            formatSignedValue(segment.engagement_delta)
                          ) : (
                            <Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={58} />
                          )}
                        </TableCell>
                        <TableCell>{segment.note || sceneSectionMessage}</TableCell>
                      </TableRow>
                    ))
                  : Array.from({ length: 4 }).map((_, index) => (
                      <TableRow key={`segment-skeleton-${index}`}>
                        <TableCell><Skeleton height={22} sx={{ transform: 'none' }} width="64%" /></TableCell>
                        <TableCell><Skeleton height={22} sx={{ transform: 'none' }} width="78%" /></TableCell>
                        <TableCell align="right"><Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={44} /></TableCell>
                        <TableCell align="right"><Skeleton height={22} sx={{ transform: 'none', ml: 'auto' }} width={58} /></TableCell>
                        <TableCell><Skeleton height={22} sx={{ transform: 'none' }} width="90%" /></TableCell>
                      </TableRow>
                    ))}
              </TableBody>
            </Table>
            {!stageAvailability.sceneStructureReady ? (
              <Typography color="text.secondary" variant="body2">
                {sceneSectionMessage}
              </Typography>
            ) : null}
          </Stack>
        </AccordionDetails>
      </Accordion>
          </Stack>
        </AccordionDetails>
      </Accordion>
      ) : null}

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">
              {isVideoResult ? 'High and low attention intervals' : 'Strongest and weakest sections'}
            </Typography>
            <AttentionIntervalsCard
              hasResults={stageAvailability.primaryScoringReady}
              highAttentionIntervals={highAttentionIntervals}
              lowAttentionIntervals={lowAttentionIntervals}
              loadingLabel={summarySectionMessage}
            />
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Recommendations</Typography>
            <RecommendationsCard
              hasResults={Boolean(analysisResult)}
              isPartial={!analysisResult && Boolean(analysisPreviewResult)}
              isReady={stageAvailability.recommendationsReady}
              loadingLabel={recommendationsSectionMessage}
              recommendations={recommendations}
              recommendationTimeLabel={resultPresentation.recommendationTimeLabel}
              summary={summary}
            />
          </Stack>
        </Paper>
      </Box>

          <Suspense fallback={<DeferredPanelFallback title="LLM evaluations" />}>
            <AnalysisEvaluationSection
              analysisCompleted={analysisCompleted}
              jobId={evaluationJobId}
              onProgressSnapshot={handleEvaluationProgressSnapshot}
              sessionToken={sessionToken || null}
            />
          </Suspense>
        </ResultsStep>
      ) : null}

      <Drawer
        PaperProps={{
          className: 'analysis-history-drawer',
        }}
        anchor="right"
        onClose={() => setIsHistoryDrawerOpen(false)}
        open={isHistoryDrawerOpen}
      >
        <RecentAnalysesPanel
          activeJobId={activeHistoryJobId}
          drawerMode={historyDrawerMode}
          errorMessage={analysisHistoryError}
          hasLoaded={hasLoadedAnalysisHistory}
          isLoading={isLoadingAnalysisHistory}
          items={analysisHistory}
          loadingJobId={historyDrawerMode === 'compare' ? comparisonLoadingJobId : loadingHistoryJobId}
          isDeleting={isDeletingAnalysisHistoryItems}
          onClose={() => setIsHistoryDrawerOpen(false)}
          onDeleteJobs={handleDeleteAnalysisHistoryItems}
          onJumpToAssetStep={() => {
            setIsHistoryDrawerOpen(false)
            scrollToSection('analysis-step-1')
          }}
          onReload={() => setAnalysisHistoryRefreshNonce((current) => current + 1)}
          onSelectCompareTarget={handleSelectComparisonTarget}
          onSelectJob={handleSelectAnalysisHistoryItem}
        />
      </Drawer>

      <TechnicalDetailsDrawer
        analysisJob={analysisJob}
        config={config}
        currentMediaTitle={currentMediaOption.title}
        currentStage={currentStage}
        diagnostics={analysisTransportDiagnostics}
        goalTemplate={goalTemplate}
        channel={channel}
        audienceSegment={audienceSegment}
        objective={objective}
        onClose={() => setIsTechnicalDetailsOpen(false)}
        open={isTechnicalDetailsOpen}
        progress={visibleProgress}
        selectedAsset={uploadState.asset}
        selectedMediaType={selectedMediaType}
        session={session}
        sessionToken={sessionToken}
        uploadStage={uploadState.stage}
      />
    </Stack>
  )
}

function UploadStep({
  CurrentMediaIcon,
  activeLibraryAssetId,
  assetLibrary,
  assetLibraryError,
  canUpload,
  config,
  currentMediaOption,
  hasLoadedAssetLibrary,
  isDragActive,
  isDeletingAssets,
  isLoadingAssetLibrary,
  onBinaryFileSelection,
  onDeleteAssets,
  onDrop,
  onMediaTypeChange,
  onReloadAssets,
  onSelectAsset,
  onTextChange,
  onTextFileSelection,
  onToggleDrag,
  onUpload,
  selectedAsset,
  selectedFile,
  selectedMediaType,
  textContent,
  textFilename,
  uploadState,
}: {
  CurrentMediaIcon: ElementType
  activeLibraryAssetId: string | null
  assetLibrary: AnalysisAsset[]
  assetLibraryError: string | null
  canUpload: boolean
  config: AnalysisConfigResponse | null
  currentMediaOption: typeof mediaTypeOptions[number]
  hasLoadedAssetLibrary: boolean
  isDragActive: boolean
  isDeletingAssets: boolean
  isLoadingAssetLibrary: boolean
  onBinaryFileSelection: (event: ChangeEvent<HTMLInputElement>) => void
  onDeleteAssets: (assetIds: string[]) => void
  onDrop: (event: DragEvent<HTMLDivElement>) => void
  onMediaTypeChange: (mediaType: MediaType) => void
  onReloadAssets: () => void
  onSelectAsset: (asset: AnalysisAsset) => void
  onTextChange: (value: string) => void
  onTextFileSelection: (event: ChangeEvent<HTMLInputElement>) => void
  onToggleDrag: (isActive: boolean) => void
  onUpload: () => void
  selectedAsset?: AnalysisAsset
  selectedFile: File | null
  selectedMediaType: MediaType
  textContent: string
  textFilename: string
  uploadState: UploadState
}) {
  const uploadDisabledReason = !config
    ? 'Upload settings are still loading.'
    : uploadState.stage === 'uploading'
      ? 'Upload is already in progress.'
      : ''

  return (
    <Paper className="dashboard-card analyze-step-card analysis-upload-card" elevation={0} id="analysis-step-1">
      <Stack spacing={3}>
        <Stack direction="row" spacing={1.5}>
          <Box className="analysis-upload-card__icon" sx={{ bgcolor: `${currentMediaOption.tone}1a`, color: currentMediaOption.tone }}>
            <CurrentMediaIcon />
          </Box>
          <Box>
            <Typography variant="h5">Upload media</Typography>
            <Typography color="text.secondary" variant="body2">
              Choose the creative asset you want to analyze.
            </Typography>
          </Box>
        </Stack>

        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          {mediaTypeOptions.map((option) => {
            const Icon = option.icon
            const isSelected = option.kind === selectedMediaType
            return (
              <Button
                color="inherit"
                key={option.kind}
                onClick={() => onMediaTypeChange(option.kind)}
                sx={{
                  borderRadius: 999,
                  border: `1px solid ${isSelected ? option.tone : 'rgba(24, 34, 48, 0.08)'}`,
                  bgcolor: isSelected ? `${option.tone}12` : 'transparent',
                  color: isSelected ? option.tone : 'text.primary',
                  px: 2,
                }}
                variant="text"
              >
                <Stack alignItems="center" direction="row" spacing={1}>
                  <Icon fontSize="small" />
                  <span>{option.title}</span>
                </Stack>
              </Button>
            )
          })}
        </Stack>

        {selectedMediaType === 'text' ? (
          <Stack spacing={2}>
            <TextField
              minRows={8}
              multiline
              onChange={(event) => onTextChange(event.target.value)}
              placeholder="Paste transcript copy, concept notes, or product narrative here."
              value={textContent}
            />
            <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={2}>
              <Typography color="text.secondary" variant="body2">
                {textContent.length} / {config?.max_text_characters ?? '...'} characters
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <Button onClick={() => onTextChange(DEMO_CREATIVE_COPY)} variant="outlined">
                  Use demo copy
                </Button>
                <Button component="label" startIcon={<FileUploadRounded />} variant="outlined">
                  Upload document
                  <input
                    accept={buildTextUploadAccept(config ? config.allowed_mime_types.text : [])}
                    hidden
                    onChange={onTextFileSelection}
                    type="file"
                  />
                </Button>
              </Stack>
            </Stack>
            <Alert severity="info">
              Demo shortcut: choose Text, use the sample copy, then upload and run analysis for a screenshot-ready flow.
            </Alert>
          </Stack>
        ) : (
          <Box
            className={`analysis-dropzone ${isDragActive ? 'is-active' : ''}`}
            onDragEnter={(event) => {
              event.preventDefault()
              onToggleDrag(true)
            }}
            onDragLeave={(event) => {
              event.preventDefault()
              onToggleDrag(false)
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={onDrop}
          >
            <Stack alignItems="center" spacing={1.5}>
              <CloudUploadRounded color="primary" />
              <Typography variant="h6">Drop a {selectedMediaType} file here</Typography>
              <Typography color="text.secondary" sx={{ textAlign: 'center' }} variant="body2">
                Accepted formats: {(config?.allowed_mime_types[selectedMediaType] || []).join(', ') || 'Loading…'}
              </Typography>
              <Button component="label" startIcon={<FileUploadRounded />} variant="contained">
                Choose file
                <input
                  accept={(config?.allowed_mime_types[selectedMediaType] || []).join(',')}
                  hidden
                  onChange={onBinaryFileSelection}
                  type="file"
                />
              </Button>
            </Stack>
          </Box>
        )}

        {(selectedAsset || selectedFile || textContent.trim()) ? (
          <SelectedSourceSummary
            mediaType={selectedMediaType}
            selectedAsset={selectedAsset}
            selectedFile={selectedFile}
            textContent={textContent}
            textFilename={textFilename}
          />
        ) : null}

        <RecentUploads
          activeAssetId={activeLibraryAssetId}
          assets={assetLibrary}
          errorMessage={assetLibraryError}
          hasLoaded={hasLoadedAssetLibrary}
          isDeleting={isDeletingAssets}
          isLoading={isLoadingAssetLibrary}
          onDeleteAssets={onDeleteAssets}
          onReload={onReloadAssets}
          onSelectAsset={onSelectAsset}
        />

        {uploadState.stage === 'uploading' ? (
          <Stack spacing={1}>
            <LinearProgress value={uploadState.progressPercent} variant="determinate" />
            <Typography color="text.secondary" variant="body2">
              Uploading: {uploadState.progressPercent}%
            </Typography>
          </Stack>
        ) : null}

        {uploadState.validationErrors.length > 0 ? (
          <Alert severity="error">
            {uploadState.validationErrors.map((errorMessage) => (
              <span key={errorMessage}>{errorMessage}</span>
            ))}
          </Alert>
        ) : null}

        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <Button disabled={!canUpload} onClick={onUpload} startIcon={<CloudUploadRounded />} variant="contained">
            {uploadState.stage === 'uploaded' ? 'Upload replacement' : 'Upload media'}
          </Button>
          {!canUpload && uploadDisabledReason ? (
            <Typography color="text.secondary" variant="body2">{uploadDisabledReason}</Typography>
          ) : null}
        </Stack>
      </Stack>
    </Paper>
  )
}

function GoalStep({
  audienceSegment,
  availableChannels,
  channel,
  goalTemplate,
  goalValidationErrors,
  groupedGoalTemplates,
  isLoadingGoalPresets,
  goalPresetsError,
  objective,
  onApplySuggestion,
  onAudienceSegmentChange,
  onBack,
  onChannelChange,
  onGoalTemplateChange,
  onNext,
  onObjectiveChange,
  suggestedGoalContext,
  uploadReady,
}: {
  audienceSegment: string
  availableChannels: Array<{ label: string; value: string }>
  channel: string
  goalTemplate: string
  goalValidationErrors: string[]
  groupedGoalTemplates: Array<{
    id: string
    label: string
    description: string
    templates: Array<{ value: string; label: string; description: string; default_channel?: string | null }>
  }>
  isLoadingGoalPresets: boolean
  goalPresetsError: string | null
  objective: string
  onApplySuggestion: () => void
  onAudienceSegmentChange: (value: string) => void
  onBack: () => void
  onChannelChange: (value: string) => void
  onGoalTemplateChange: (value: string, defaultChannel?: string | null) => void
  onNext: () => void
  onObjectiveChange: (value: string) => void
  suggestedGoalContext: ReturnType<typeof resolveSuggestedGoalContext>
  uploadReady: boolean
}) {
  const visibleTemplates = groupedGoalTemplates.flatMap((group) => group.templates).slice(0, 5)
  const canContinue = uploadReady && goalValidationErrors.length === 0 && Boolean(goalTemplate || channel || objective.trim())

  return (
    <Paper className="dashboard-card analyze-step-card" elevation={0} id="analysis-step-2">
      <Stack spacing={3}>
        <Box>
          <Typography variant="h5">Set goal</Typography>
          <Typography color="text.secondary" variant="body2">
            Pick the lens for this review.
          </Typography>
        </Box>
        {isLoadingGoalPresets ? <Alert severity="info">Loading goal presets…</Alert> : null}
        {goalPresetsError ? <Alert severity="warning">{goalPresetsError}</Alert> : null}
        {suggestedGoalContext ? (
          <Alert
            action={<Button onClick={onApplySuggestion} size="small" variant="outlined">Apply</Button>}
            severity="info"
          >
            Suggested: {readableGoalTemplate(suggestedGoalContext.goal_template)} for {readableChannel(suggestedGoalContext.channel)}.
          </Alert>
        ) : null}

        <Box className="analysis-goal-template-grid">
          {visibleTemplates.map((option) => {
            const isSelected = goalTemplate === option.value
            return (
              <ButtonBase
                className={`analysis-goal-card ${isSelected ? 'is-selected' : ''}`.trim()}
                key={option.value}
                onClick={() => onGoalTemplateChange(option.value, option.default_channel)}
              >
                <Stack spacing={0.75}>
                  <Typography variant="subtitle2">{option.label}</Typography>
                  <Typography color="text.secondary" variant="body2">{option.description}</Typography>
                  {option.default_channel ? (
                    <Chip label={readableChannel(option.default_channel)} size="small" sx={{ alignSelf: 'flex-start' }} variant="outlined" />
                  ) : null}
                </Stack>
              </ButtonBase>
            )
          })}
        </Box>

        <Accordion className="analysis-compact-accordion" elevation={0}>
          <AccordionSummary expandIcon={<ExpandMoreRounded />}>
            <Stack spacing={0.25}>
              <Typography variant="subtitle2">Advanced settings</Typography>
              <Typography color="text.secondary" variant="body2">Channel, audience, and custom objective.</Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={2}>
              <Box className="analysis-goal-grid">
                <TextField label="Channel" onChange={(event) => onChannelChange(event.target.value)} select value={channel}>
                  <MenuItem value="">Select a channel</MenuItem>
                  {availableChannels.map((option) => (
                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="Audience segment"
                  onChange={(event) => onAudienceSegmentChange(event.target.value)}
                  placeholder={suggestedGoalContext?.audience_placeholder || 'Example: Gen Z shoppers'}
                  value={audienceSegment}
                />
              </Box>
              <TextField
                label="Objective"
                minRows={3}
                multiline
                onChange={(event) => onObjectiveChange(event.target.value)}
                placeholder="Example: Evaluate whether the opening hook is strong enough for paid social."
                value={objective}
              />
            </Stack>
          </AccordionDetails>
        </Accordion>

        {goalValidationErrors.length > 0 && uploadReady ? <Alert severity="warning">{goalValidationErrors.join(' ')}</Alert> : null}
        {!uploadReady ? <Alert severity="info">Upload or select media before choosing a goal.</Alert> : null}

        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Button onClick={onBack} variant="outlined">Back</Button>
          <Button disabled={!canContinue} onClick={onNext} variant="contained">
            Continue to review
          </Button>
        </Stack>
      </Stack>
    </Paper>
  )
}

function TechnicalDetailsDrawer({
  analysisJob,
  config,
  currentMediaTitle,
  currentStage,
  diagnostics,
  goalTemplate,
  channel,
  audienceSegment,
  objective,
  onClose,
  open,
  progress,
  selectedAsset,
  selectedMediaType,
  session,
  sessionToken,
  uploadStage,
}: {
  analysisJob: AnalysisJob | null
  config: AnalysisConfigResponse | null
  currentMediaTitle: string
  currentStage: string
  diagnostics: AnalysisTransportDiagnostics
  goalTemplate: string
  channel: string
  audienceSegment: string
  objective: string
  onClose: () => void
  open: boolean
  progress: AnalysisProgressState | null
  selectedAsset?: AnalysisAsset
  selectedMediaType: MediaType
  session: AuthSession
  sessionToken?: string | null
  uploadStage: UploadStage
}) {
  return (
    <Drawer
      PaperProps={{ className: 'analysis-history-drawer analysis-technical-drawer' }}
      anchor="right"
      onClose={onClose}
      open={open}
    >
      <Stack className="analysis-history-drawer__content" spacing={2.5}>
        <Stack direction="row" justifyContent="space-between" spacing={2}>
          <Box>
            <Typography variant="h6">Technical details</Typography>
            <Typography color="text.secondary" variant="body2">Flow status, payload, and worker metadata.</Typography>
          </Box>
          <Button onClick={onClose} size="small" variant="outlined">Close</Button>
        </Stack>

        <TechnicalDetailsSection
          defaultExpanded
          description="Current workflow phase and each backend processing stage."
          title="Full flow status"
        >
            <Chip className={`analysis-status-chip is-${currentStage}`} label={readableProgressStage(currentStage)} sx={{ alignSelf: 'flex-start' }} />
            {progress?.stageLabel ? <Typography color="text.secondary" variant="body2">{progress.stageLabel}</Typography> : null}
            {stageRows(currentStage).map((row) => (
              <Box className={`analysis-stage-row ${row.isActive ? 'is-active' : ''}`} key={row.label}>
                <Typography variant="subtitle2">{row.label}</Typography>
                <Typography color="text.secondary" variant="body2">{row.detail}</Typography>
              </Box>
            ))}
        </TechnicalDetailsSection>

        <TechnicalDetailsSection
          description="Workspace, goal, asset, and queued-job values sent with this analysis."
          title="Current payload"
        >
            <DetailRow label="Workspace" value={session.organizationName || 'Primary workspace'} />
            <DetailRow label="Project" value={session.defaultProjectName || 'Default Analysis Project'} />
            <DetailRow label="Selected media" value={currentMediaTitle} />
            <DetailRow label="Goal template" value={goalTemplate ? readableGoalTemplate(goalTemplate) : 'Not specified'} />
            <DetailRow label="Channel" value={channel ? readableChannel(channel) : 'Not specified'} />
            <DetailRow label="Audience segment" value={audienceSegment.trim() ? audienceSegment.trim() : 'Not specified'} />
            <DetailRow label="Objective" value={objective.trim() || 'Not specified'} />
            <DetailRow label="Selected asset" value={selectedAsset?.original_filename || selectedAsset?.object_key || 'No stored asset selected'} />
            <DetailRow label="Upload status" value={selectedAsset?.upload_status || uploadStage} />
            <DetailRow label="Stored object" value={selectedAsset?.object_key || 'Not uploaded'} />
            <DetailRow label="Queued job" value={analysisJob ? `${shortenId(analysisJob.id)} (${analysisJob.status})` : 'Not started'} />
        </TechnicalDetailsSection>

        <TechnicalDetailsSection
          description="Transport mode, heartbeat health, and delivery timing markers."
          title="Delivery diagnostics"
        >
          <AnalysisTransportDiagnosticsCard analysisJob={analysisJob} diagnostics={diagnostics} progress={progress} />
        </TechnicalDetailsSection>

        <TechnicalDetailsSection
          description="Session, upload constraints, allowed MIME types, and stream state."
          title="Debug metadata"
        >
            <ValidationRow label="Session token" value={sessionToken ? 'Attached' : 'Sign in again'} />
            <ValidationRow label="Max file size" value={config ? formatFileSize(config.max_file_size_bytes) : 'Loading…'} />
            <ValidationRow
              label="Allowed mime types"
              value={config ? config.allowed_mime_types[selectedMediaType].join(', ') : 'Loading…'}
            />
            <ValidationRow label="Event transport" value={diagnostics.mode} />
            <ValidationRow label="Reconnects" value={String(diagnostics.reconnectCount)} />
        </TechnicalDetailsSection>
      </Stack>
    </Drawer>
  )
}

function TechnicalDetailsSection({
  children,
  defaultExpanded = false,
  description,
  title,
}: {
  children: ReactNode
  defaultExpanded?: boolean
  description: string
  title: string
}) {
  return (
    <Accordion className="analysis-compact-accordion" defaultExpanded={defaultExpanded} elevation={0}>
      <AccordionSummary expandIcon={<ExpandMoreRounded />}>
        <Box>
          <Typography variant="h6">{title}</Typography>
          <Typography color="text.secondary" variant="body2">
            {description}
          </Typography>
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>{children}</Stack>
      </AccordionDetails>
    </Accordion>
  )
}
function RecentAnalysesPanel({
  activeJobId,
  drawerMode,
  errorMessage,
  hasLoaded,
  isDeleting,
  isLoading,
  items,
  loadingJobId,
  onClose,
  onDeleteJobs,
  onJumpToAssetStep,
  onReload,
  onSelectCompareTarget,
  onSelectJob,
}: {
  activeJobId: string | null
  drawerMode: HistoryDrawerMode
  errorMessage: string | null
  hasLoaded: boolean
  isDeleting: boolean
  isLoading: boolean
  items: AnalysisJobListItem[]
  loadingJobId: string | null
  onClose: () => void
  onDeleteJobs: (jobIds: string[]) => void
  onJumpToAssetStep: () => void
  onReload: () => void
  onSelectCompareTarget: (item: AnalysisJobListItem) => void
  onSelectJob: (item: AnalysisJobListItem) => void
}) {
  const isCompareMode = drawerMode === 'compare'
  const [checkedJobIds, setCheckedJobIds] = useState<string[]>([])
  const checkedCount = checkedJobIds.length
  const checkedJobs = new Set(checkedJobIds)
  const handleToggleCheckedJob = (jobId: string) => {
    setCheckedJobIds((current) =>
      current.includes(jobId) ? current.filter((id) => id !== jobId) : [...current, jobId],
    )
  }
  const handleDeleteCheckedJobs = () => {
    onDeleteJobs(checkedJobIds)
    setCheckedJobIds([])
  }

  return (
    <Stack className="analysis-history-drawer__content" spacing={2.5}>
      <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
        <Box>
          <Typography variant="h6">{isCompareMode ? 'Choose a comparison target' : 'Recent analyses'}</Typography>
          <Typography color="text.secondary" variant="body2">
            {isCompareMode
              ? 'Pick a completed run for side-by-side comparison.'
              : 'Open a completed or in-flight run from this panel.'}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          {!isCompareMode ? (
            <Button
              color="error"
              disabled={checkedCount === 0 || isDeleting}
              onClick={handleDeleteCheckedJobs}
              size="small"
              startIcon={<DeleteRounded />}
              variant="outlined"
            >
              {isDeleting ? 'Deleting…' : `Delete checked${checkedCount ? ` (${checkedCount})` : ''}`}
            </Button>
          ) : null}
          <Button onClick={onReload} size="small" variant="text">
            Refresh list
          </Button>
          <Button onClick={onClose} size="small" variant="outlined">
            Close
          </Button>
        </Stack>
      </Stack>

      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

      {isLoading && items.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            Loading recent analyses…
          </Typography>
        </Box>
      ) : null}

      {!isLoading && hasLoaded && items.length === 0 ? (
        <Box className="analysis-empty-state">
          <Stack spacing={1.5}>
            <Typography color="text.secondary" variant="body2">
              No analysis jobs yet for this media type.
            </Typography>
            <Button onClick={onJumpToAssetStep} size="small" variant="contained">
              Go to Step 1
            </Button>
          </Stack>
        </Box>
      ) : null}

      {items.length > 0 ? (
        <Box className="analysis-job-history" data-testid="analysis-history-list">
          {items.map((item) => {
            const isSelected = item.job.id === activeJobId
            const isLoadingSelection = item.job.id === loadingJobId
            const primaryLabel =
              item.asset?.original_filename || item.asset?.object_key || `Analysis ${shortenId(item.job.id)}`

            return (
              <ButtonBase
                className={`analysis-job-history__item ${isSelected ? 'is-selected' : ''}`}
                data-testid={`analysis-history-item-${item.job.id}`}
                key={item.job.id}
                onClick={() => {
                  if (isCompareMode && !item.has_result) {
                    return
                  }
                  if (isCompareMode) {
                    onSelectCompareTarget(item)
                    return
                  }
                  onSelectJob(item)
                }}
                sx={{ borderRadius: '20px', width: '100%', textAlign: 'left' }}
              >
                <Box sx={{ width: '100%' }}>
                  <Stack spacing={1.25}>
                    <Stack alignItems="flex-start" direction="row" justifyContent="space-between" spacing={1.5}>
                      <Stack alignItems="flex-start" direction="row" spacing={1} sx={{ minWidth: 0 }}>
                        {!isCompareMode ? (
                          <Checkbox
                            checked={checkedJobs.has(item.job.id)}
                            disabled={isDeleting || item.job.status === 'queued' || item.job.status === 'processing'}
                            inputProps={{ 'aria-label': `Select ${primaryLabel} for deletion` }}
                            onClick={(event) => event.stopPropagation()}
                            onChange={() => handleToggleCheckedJob(item.job.id)}
                            size="small"
                            sx={{ mt: -0.75 }}
                          />
                        ) : null}
                        <Box sx={{ minWidth: 0 }}>
                          <Typography sx={{ wordBreak: 'break-word' }} variant="subtitle2">
                            {primaryLabel}
                          </Typography>
                          <Typography color="text.secondary" sx={{ wordBreak: 'break-word' }} variant="body2">
                            {formatTimestamp(item.job.created_at)}
                          </Typography>
                        </Box>
                      </Stack>
                      <Chip
                        className={`analysis-status-chip is-${item.job.status}`}
                        label={isLoadingSelection ? 'loading' : item.job.status}
                        size="small"
                        variant="outlined"
                      />
                    </Stack>

                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip
                        color={item.has_result ? 'success' : item.job.status === 'failed' ? 'error' : 'default'}
                        label={item.has_result ? 'Results ready' : item.job.status === 'failed' ? 'Failed' : 'No result yet'}
                        size="small"
                        variant="outlined"
                      />
                      <Chip label={item.asset?.media_type || 'analysis'} size="small" variant="outlined" />
                      {isCompareMode ? (
                        <Chip
                          color={item.has_result ? 'primary' : 'default'}
                          label={item.has_result ? 'Compare' : 'Unavailable'}
                          size="small"
                          variant="outlined"
                        />
                      ) : null}
                    </Stack>

                    <Typography color="text.secondary" variant="body2">
                      {truncateText(item.job.objective || 'No analysis objective was stored for this run.', 132)}
                    </Typography>
                  </Stack>
                </Box>
              </ButtonBase>
            )
          })}
        </Box>
      ) : null}
    </Stack>
  )
}

function QuickComparisonCard({
  baselineAsset,
  baselineJob,
  baselineResult,
  comparisonAsset,
  comparisonJob,
  comparisonResult,
  onClear,
}: {
  baselineAsset: AnalysisAsset | null
  baselineJob: AnalysisJob | null
  baselineResult: AnalysisResult
  comparisonAsset: AnalysisAsset | null
  comparisonJob: AnalysisJob
  comparisonResult: AnalysisResult
  onClear: () => void
}) {
  const comparisonRows = buildQuickComparisonRows(baselineResult, comparisonResult)
  const winner = comparisonRows.reduce(
    (current, row) => {
      if (row.baselineValue > row.comparisonValue) {
        return { baseline: current.baseline + 1, comparison: current.comparison }
      }
      if (row.comparisonValue > row.baselineValue) {
        return { baseline: current.baseline, comparison: current.comparison + 1 }
      }
      return current
    },
    { baseline: 0, comparison: 0 },
  )
  const winnerLabel =
    winner.baseline === winner.comparison
      ? 'The two runs are effectively tied on the primary dashboard metrics.'
      : winner.baseline > winner.comparison
        ? `${baselineAsset?.original_filename || shortenId(baselineJob?.id || 'baseline')} currently leads the quick compare snapshot.`
        : `${comparisonAsset?.original_filename || shortenId(comparisonJob.id)} currently leads the quick compare snapshot.`

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">Quick comparison</Typography>
            <Typography color="text.secondary" variant="body2">
              Use this as a fast call before the dedicated compare workspace lands.
            </Typography>
          </Box>
          <Button onClick={onClear} size="small" variant="outlined">
            Clear comparison
          </Button>
        </Stack>
        <Alert severity="info">{winnerLabel}</Alert>
        <Box className="analysis-compare-grid">
          <CompareSummaryColumn
            title={baselineAsset?.original_filename || `Current run ${shortenId(baselineJob?.id || 'current')}`}
            subtitle={baselineJob?.objective || 'Current analysis'}
          />
          <CompareSummaryColumn
            title={comparisonAsset?.original_filename || `Comparison ${shortenId(comparisonJob.id)}`}
            subtitle={comparisonJob.objective || 'Comparison analysis'}
          />
        </Box>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Metric</TableCell>
              <TableCell align="right">Current</TableCell>
              <TableCell align="right">Compare</TableCell>
              <TableCell align="right">Delta</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {comparisonRows.map((row) => (
              <TableRow key={row.label}>
                <TableCell>{row.label}</TableCell>
                <TableCell align="right">{row.baselineValue.toFixed(1)}</TableCell>
                <TableCell align="right">{row.comparisonValue.toFixed(1)}</TableCell>
                <TableCell align="right">{formatSignedValue(row.baselineValue - row.comparisonValue)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Stack>
    </Paper>
  )
}

function CompareSummaryColumn({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <Box className="analysis-inline-summary">
      <Typography variant="subtitle2">{title}</Typography>
      <Typography color="text.secondary" variant="body2">
        {truncateText(subtitle, 120)}
      </Typography>
    </Box>
  )
}

function GeneratedVariantsPanel({
  asset,
  errorMessage,
  hasResults,
  isGenerating,
  isLoading,
  items,
  job,
  onCopy,
  onDownload,
  onGenerate,
}: {
  asset: AnalysisAsset | null
  errorMessage: string | null
  hasResults: boolean
  isGenerating: boolean
  isLoading: boolean
  items: AnalysisGeneratedVariant[]
  job: AnalysisJob | null
  onCopy: (variant: AnalysisGeneratedVariant) => void
  onDownload: (variant: AnalysisGeneratedVariant) => void
  onGenerate: () => void
}) {
  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">Generated variants</Typography>
            <Typography color="text.secondary" variant="body2">
              Convert recommendations into ready-to-review rewrites.
            </Typography>
          </Box>
          <Button disabled={!hasResults || isGenerating} onClick={onGenerate} size="small" variant="contained">
            {isGenerating ? 'Generating…' : items.length > 0 ? 'Regenerate variants' : 'Generate variants'}
          </Button>
        </Stack>

        {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

        {isLoading ? (
          <Alert severity="info">Loading saved generated variants…</Alert>
        ) : null}

        {!hasResults ? (
          <Box className="analysis-empty-state">
            <Typography color="text.secondary" variant="body2">
              Complete a run first, then generate variants.
            </Typography>
          </Box>
        ) : null}

        {hasResults && !isLoading && items.length === 0 ? (
          <Box className="analysis-empty-state">
            <Stack spacing={1.5}>
              <Typography color="text.secondary" variant="body2">
                No variants saved for this run yet.
              </Typography>
              <Button disabled={isGenerating} onClick={onGenerate} size="small" variant="outlined">
                Generate variants
              </Button>
            </Stack>
          </Box>
        ) : null}

        {items.length > 0 ? (
          <Stack spacing={2}>
            {items.map((variant) => (
              <Box
                key={variant.id}
                sx={{
                  border: '1px solid rgba(24, 34, 48, 0.08)',
                  borderRadius: '20px',
                  p: 2,
                  bgcolor: 'rgba(248, 250, 252, 0.72)',
                }}
              >
                <Stack spacing={2}>
                  <Stack
                    alignItems={{ xs: 'stretch', md: 'center' }}
                    direction={{ xs: 'column', md: 'row' }}
                    justifyContent="space-between"
                    spacing={1.5}
                  >
                    <Box>
                      <Typography variant="subtitle1">{variant.title}</Typography>
                      <Typography color="text.secondary" variant="body2">
                        {variant.summary}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip label={readableGeneratedVariantType(variant.variant_type)} size="small" variant="outlined" />
                      {variant.source_suggestion_title ? (
                        <Chip label={truncateText(variant.source_suggestion_title, 42)} size="small" variant="outlined" />
                      ) : null}
                      <Button onClick={() => onCopy(variant)} size="small" variant="text">
                        Copy
                      </Button>
                      <Button onClick={() => onDownload(variant)} size="small" variant="outlined">
                        Download
                      </Button>
                    </Stack>
                  </Stack>

                  {variant.focus_recommendations.length > 0 ? (
                    <Box className="analysis-inline-summary">
                      <Typography variant="subtitle2">Variant focus</Typography>
                      <Stack spacing={0.5}>
                        {variant.focus_recommendations.map((recommendation) => (
                          <Typography color="text.secondary" key={`${variant.id}-${recommendation}`} variant="body2">
                            {recommendation}
                          </Typography>
                        ))}
                      </Stack>
                    </Box>
                  ) : null}

                  <Box
                    sx={{
                      display: 'grid',
                      gap: 1.25,
                      gridTemplateColumns: {
                        xs: '1fr',
                        md: 'repeat(2, minmax(0, 1fr))',
                      },
                    }}
                  >
                    {variant.sections.map((section) => (
                      <Box
                        key={section.key}
                        sx={{
                          border: '1px solid rgba(24, 34, 48, 0.08)',
                          borderRadius: '16px',
                          p: 1.5,
                          bgcolor: '#fff',
                        }}
                      >
                        <Typography variant="subtitle2">{section.label}</Typography>
                        <Typography color="text.secondary" sx={{ whiteSpace: 'pre-line' }} variant="body2">
                          {section.value}
                        </Typography>
                      </Box>
                    ))}
                  </Box>

                  <Alert severity="info">
                    Compare generated variant vs original: {variant.compare_summary}
                  </Alert>

                  <Box className="analysis-compare-grid">
                    <CompareSummaryColumn
                      title={asset?.original_filename || `Original ${job ? shortenId(job.id) : 'analysis'}`}
                      subtitle={job?.objective || 'Current analysis'}
                    />
                    <CompareSummaryColumn
                      title={variant.title}
                      subtitle="Projected generated variant"
                    />
                  </Box>

                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Metric</TableCell>
                        <TableCell align="right">Original</TableCell>
                        <TableCell align="right">Variant</TableCell>
                        <TableCell align="right">Delta</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {variant.compare_metrics.map((metric) => (
                        <TableRow key={`${variant.id}-${metric.key}`}>
                          <TableCell>{metric.label}</TableCell>
                          <TableCell align="right">{metric.original_value.toFixed(1)}</TableCell>
                          <TableCell align="right">{metric.variant_value.toFixed(1)}</TableCell>
                          <TableCell align="right">{formatSignedValue(metric.delta)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Stack>
              </Box>
            ))}
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  )
}
