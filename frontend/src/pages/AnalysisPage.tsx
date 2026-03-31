import AudiotrackRounded from '@mui/icons-material/AudiotrackRounded'
import AutoGraphRounded from '@mui/icons-material/AutoGraphRounded'
import CloudUploadRounded from '@mui/icons-material/CloudUploadRounded'
import DescriptionRounded from '@mui/icons-material/DescriptionRounded'
import FileUploadRounded from '@mui/icons-material/FileUploadRounded'
import PlayCircleRounded from '@mui/icons-material/PlayCircleRounded'
import VideoLibraryRounded from '@mui/icons-material/VideoLibraryRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  Paper,
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
  useState,
  type ChangeEvent,
  type Dispatch,
  type DragEvent,
  type SetStateAction,
} from 'react'
import AnalysisEvaluationSection from '../components/analysis/AnalysisEvaluationSection'
import { apiRequest, uploadToApi, uploadToSignedUrl } from '../lib/api'
import type { AuthSession } from '../lib/session'

type AnalysisPageProps = {
  session: AuthSession
}

type MediaType = 'video' | 'audio' | 'text'
type JobState = 'queued' | 'processing' | 'completed' | 'failed'
type UploadStage = 'idle' | 'validating' | 'uploading' | 'uploaded' | 'failed'
type RecommendationPriority = 'high' | 'medium' | 'low'

type AnalysisConfigResponse = {
  max_file_size_bytes: number
  max_text_characters: number
  allowed_media_types: MediaType[]
  allowed_mime_types: Record<MediaType, string[]>
}

type AnalysisAsset = {
  id: string
  creative_id?: string | null
  creative_version_id?: string | null
  media_type: MediaType
  original_filename?: string | null
  mime_type?: string | null
  size_bytes?: number | null
  bucket: string
  object_key: string
  object_uri: string
  checksum?: string | null
  upload_status: string
  created_at: string
}

type AnalysisAssetListResponse = {
  items: AnalysisAsset[]
}

type AnalysisUploadSession = {
  id: string
  upload_token: string
  upload_status: string
  created_at: string
}

type AnalysisUploadCreateResponse = {
  upload_session: AnalysisUploadSession
  asset: AnalysisAsset
  upload_url: string
  upload_headers: Record<string, string>
}

type AnalysisUploadCompleteResponse = {
  upload_session: AnalysisUploadSession
  asset: AnalysisAsset
}

type AnalysisJob = {
  id: string
  asset_id: string
  status: JobState
  objective?: string | null
  started_at?: string | null
  finished_at?: string | null
  error_message?: string | null
  created_at: string
}

type AnalysisSummary = {
  modality: MediaType
  overall_attention_score: number
  hook_score_first_3_seconds: number
  sustained_engagement_score: number
  memory_proxy_score: number
  cognitive_load_proxy: number
  confidence?: number | null
  completeness?: number | null
  notes?: string[]
  metadata?: {
    objective?: string | null
    source_label?: string | null
    segment_count?: number | null
    duration_ms?: number | null
  }
}

type AnalysisMetricRow = {
  key: string
  label: string
  value: number
  unit: string
  source: string
  detail?: string | null
  confidence?: number | null
}

type AnalysisTimelinePoint = {
  timestamp_ms: number
  engagement_score: number
  attention_score: number
  memory_proxy: number
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

type AnalysisInterval = {
  label: string
  start_time_ms: number
  end_time_ms: number
  average_attention_score: number
}

type AnalysisHeatmapFrame = {
  timestamp_ms: number
  label: string
  scene_label: string
  grid_rows: number
  grid_columns: number
  intensity_map: number[][]
  strongest_zone: string
  caption: string
}

type AnalysisRecommendation = {
  title: string
  detail: string
  priority: RecommendationPriority
  timestamp_ms?: number | null
  confidence?: number | null
}

type AnalysisResult = {
  job_id: string
  summary_json: AnalysisSummary
  metrics_json: AnalysisMetricRow[]
  timeline_json: AnalysisTimelinePoint[]
  segments_json: AnalysisSegmentRow[]
  visualizations_json: {
    visualization_mode: string
    heatmap_frames: AnalysisHeatmapFrame[]
    high_attention_intervals: AnalysisInterval[]
    low_attention_intervals: AnalysisInterval[]
  }
  recommendations_json: AnalysisRecommendation[]
  created_at: string
}

type AnalysisJobStatusResponse = {
  job: AnalysisJob
  result?: AnalysisResult | null
}

type UploadState = {
  stage: UploadStage
  progressPercent: number
  validationErrors: string[]
  errorMessage?: string
  asset?: AnalysisAsset
  uploadSession?: AnalysisUploadSession
}

type BannerMessage = {
  type: 'error' | 'success' | 'info'
  message: string
}

type UploadSource = {
  file: Blob
  fileName: string
  mimeType: string
  sizeBytes: number
}

type SummaryCard = {
  key: string
  label: string
  value: number
  helper: string
}

const mediaTypeOptions: Array<{
  kind: MediaType
  title: string
  subtitle: string
  icon: typeof VideoLibraryRounded
  tone: string
}> = [
  {
    kind: 'video',
    title: 'Video',
    subtitle: 'MP4, MOV, or WebM source footage for timestamped creative analysis.',
    icon: VideoLibraryRounded,
    tone: '#3b5bdb',
  },
  {
    kind: 'audio',
    title: 'Audio',
    subtitle: 'Voiceovers and audio-led assets for retention and pacing analysis.',
    icon: AudiotrackRounded,
    tone: '#0f766e',
  },
  {
    kind: 'text',
    title: 'Text',
    subtitle: 'Paste copy or import a `.txt` file for TRIBE-compatible text analysis.',
    icon: DescriptionRounded,
    tone: '#f97316',
  },
]

const placeholderSummary: AnalysisSummary = {
  modality: 'video',
  overall_attention_score: 0,
  hook_score_first_3_seconds: 0,
  sustained_engagement_score: 0,
  memory_proxy_score: 0,
  cognitive_load_proxy: 0,
  confidence: null,
  completeness: null,
  notes: [],
  metadata: {
    objective: null,
    source_label: null,
    segment_count: 0,
    duration_ms: 0,
  },
}

const placeholderMetrics: AnalysisMetricRow[] = [
  {
    key: 'overall_attention_score',
    label: 'Overall Attention',
    value: 0,
    unit: '/100',
    source: 'pending',
    detail: 'Waiting for processed output.',
  },
  {
    key: 'hook_score_first_3_seconds',
    label: 'Hook Score First 3 Seconds',
    value: 0,
    unit: '/100',
    source: 'pending',
    detail: 'Waiting for processed output.',
  },
  {
    key: 'memory_proxy_score',
    label: 'Memory Proxy',
    value: 0,
    unit: '/100',
    source: 'pending',
    detail: 'Waiting for processed output.',
  },
]

const placeholderTimeline: AnalysisTimelinePoint[] = [
  { timestamp_ms: 0, engagement_score: 0, attention_score: 0, memory_proxy: 0 },
  { timestamp_ms: 1500, engagement_score: 0, attention_score: 0, memory_proxy: 0 },
  { timestamp_ms: 3000, engagement_score: 0, attention_score: 0, memory_proxy: 0 },
]

const placeholderSegments: AnalysisSegmentRow[] = [
  {
    segment_index: 0,
    label: 'Scene 01',
    start_time_ms: 0,
    end_time_ms: 1500,
    attention_score: 0,
    engagement_delta: 0,
    note: 'Upload and queue an analysis job to populate segment notes.',
  },
]

const placeholderHeatmapFrames: AnalysisHeatmapFrame[] = [
  {
    timestamp_ms: 0,
    label: 'Keyframe 1',
    scene_label: 'Scene 01',
    grid_rows: 3,
    grid_columns: 3,
    intensity_map: [
      [0, 0, 0],
      [0, 0, 0],
      [0, 0, 0],
    ],
    strongest_zone: 'middle_center',
    caption: 'Fallback 2D grid overlay will appear here after inference.',
  },
]

function AnalysisPage({ session }: AnalysisPageProps) {
  const [config, setConfig] = useState<AnalysisConfigResponse | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
  const [selectedMediaType, setSelectedMediaType] = useState<MediaType>('video')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [textContent, setTextContent] = useState('')
  const [textFilename, setTextFilename] = useState('analysis-notes.txt')
  const [objective, setObjective] = useState('')
  const [isDragActive, setIsDragActive] = useState(false)
  const [isLoadingConfig, setIsLoadingConfig] = useState(true)
  const [bannerMessage, setBannerMessage] = useState<BannerMessage | null>(null)
  const [uploadState, setUploadState] = useState<UploadState>({
    stage: 'idle',
    progressPercent: 0,
    validationErrors: [],
  })
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null)
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null)
  const [assetLibrary, setAssetLibrary] = useState<AnalysisAsset[]>([])
  const [isLoadingAssetLibrary, setIsLoadingAssetLibrary] = useState(false)
  const [hasLoadedAssetLibrary, setHasLoadedAssetLibrary] = useState(false)
  const [assetLibraryError, setAssetLibraryError] = useState<string | null>(null)
  const [assetLibraryRefreshNonce, setAssetLibraryRefreshNonce] = useState(0)
  const selectedAssetStorageKey = buildSelectedAssetStorageKey(session.defaultProjectId || session.email)
  const [activeLibraryAssetId, setActiveLibraryAssetId] = useState<string | null>(() =>
    readSelectedAnalysisAssetId(buildSelectedAssetStorageKey(session.defaultProjectId || session.email)),
  )

  const sessionToken = session.sessionToken
  const currentMediaOption = mediaTypeOptions.find((option) => option.kind === selectedMediaType) ?? mediaTypeOptions[0]
  const CurrentMediaIcon = currentMediaOption.icon
  const currentStage = resolveCurrentStage(uploadState.stage, analysisJob?.status)
  const canUpload = Boolean(config && sessionToken && uploadState.stage !== 'uploading')
  const canStartAnalysis =
    Boolean(sessionToken) &&
    uploadState.stage === 'uploaded' &&
    Boolean(uploadState.asset) &&
    analysisJob?.status !== 'queued' &&
    analysisJob?.status !== 'processing'

  const pollAnalysisJob = useEffectEvent(async (jobId: string) => {
    if (!sessionToken) {
      return
    }

    try {
      const statusResponse = await apiRequest<AnalysisJobStatusResponse>(`/api/v1/analysis/jobs/${jobId}`, {
        sessionToken,
      })
      setAnalysisJob(statusResponse.job)

      if (statusResponse.result) {
        setAnalysisResult(statusResponse.result)
      } else if (statusResponse.job.status === 'completed') {
        const result = await apiRequest<AnalysisResult>(`/api/v1/analysis/jobs/${jobId}/results`, {
          sessionToken,
        })
        setAnalysisResult(result)
      }

      if (statusResponse.job.status === 'failed' && statusResponse.job.error_message) {
        setBannerMessage({
          type: 'error',
          message: statusResponse.job.error_message,
        })
      }
    } catch (error) {
      setBannerMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to refresh analysis status.',
      })
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

      const preferredAssetId = activeLibraryAssetId || readSelectedAnalysisAssetId(selectedAssetStorageKey)
      const preferredAsset =
        preferredAssetId != null
          ? response.items.find((asset) => asset.id === preferredAssetId && asset.upload_status === 'uploaded')
          : null
      const hasLocalDraft = selectedMediaType === 'text' ? Boolean(textContent.trim()) : Boolean(selectedFile)

      if (preferredAsset && !hasLocalDraft && uploadState.stage !== 'uploading' && analysisJob == null) {
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
    void loadAssetLibrary()
  }, [assetLibraryRefreshNonce, selectedMediaType, sessionToken])

  useEffect(() => {
    if (!analysisJob || !sessionToken) {
      return
    }
    if (analysisJob.status === 'completed' || analysisJob.status === 'failed') {
      if (analysisJob.status === 'completed' && !analysisResult) {
        void pollAnalysisJob(analysisJob.id)
      }
      return
    }

    const intervalId = window.setInterval(() => {
      void pollAnalysisJob(analysisJob.id)
    }, 4_000)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [analysisJob, analysisResult, sessionToken])

  const handleMediaTypeChange = (nextMediaType: MediaType) => {
    if (nextMediaType === selectedMediaType) {
      return
    }

    setSelectedMediaType(nextMediaType)
    setSelectedFile(null)
    setTextContent('')
    setTextFilename('analysis-notes.txt')
    setActiveLibraryAssetId(null)
    resetWorkflowState(setUploadState, setAnalysisJob, setAnalysisResult, setBannerMessage)
  }

  const handleBinaryFileSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    event.target.value = ''
    setSelectedFile(file)
    setActiveLibraryAssetId(null)
    resetWorkflowState(setUploadState, setAnalysisJob, setAnalysisResult, setBannerMessage)
  }

  const handleTextFileSelection = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    event.target.value = ''

    try {
      const nextTextContent = await file.text()
      setTextContent(nextTextContent)
      setTextFilename(ensureTxtFilename(file.name))
      setActiveLibraryAssetId(null)
      resetWorkflowState(setUploadState, setAnalysisJob, setAnalysisResult, setBannerMessage)
    } catch {
      setBannerMessage({
        type: 'error',
        message: 'Unable to read the selected text file.',
      })
    }
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragActive(false)

    const file = event.dataTransfer.files?.[0]
    if (!file) {
      return
    }

    setSelectedFile(file)
    setActiveLibraryAssetId(null)
    resetWorkflowState(setUploadState, setAnalysisJob, setAnalysisResult, setBannerMessage)
  }

  const handleSelectUploadedAsset = (asset: AnalysisAsset) => {
    if (asset.upload_status !== 'uploaded') {
      return
    }

    setSelectedFile(null)
    setTextContent('')
    setTextFilename(ensureTxtFilename(asset.original_filename || 'analysis-notes.txt'))
    setAnalysisJob(null)
    setAnalysisResult(null)
    setActiveLibraryAssetId(asset.id)
    storeSelectedAnalysisAssetId(selectedAssetStorageKey, asset.id)
    setUploadState({
      stage: 'uploaded',
      progressPercent: 100,
      validationErrors: [],
      asset,
    })
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
    setActiveLibraryAssetId(null)
    setUploadState({
      stage: 'uploading',
      progressPercent: 0,
      validationErrors: [],
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
      setActiveLibraryAssetId(completedResponse.asset.id)
      storeSelectedAnalysisAssetId(selectedAssetStorageKey, completedResponse.asset.id)
      setAssetLibrary((current) => mergeLatestAnalysisAsset(current, completedResponse.asset))
      setBannerMessage({
        type: usedBackendFallback ? 'info' : 'success',
        message: usedBackendFallback
          ? 'Upload completed through the backend proxy. The asset is ready to queue for analysis.'
          : 'Upload completed. The asset is ready to queue for analysis.',
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

    setBannerMessage(null)
    try {
      const response = await apiRequest<AnalysisJobStatusResponse>('/api/v1/analysis/jobs', {
        method: 'POST',
        sessionToken,
        body: {
          asset_id: uploadState.asset.id,
          objective: objective.trim() || null,
        },
      })
      setAnalysisJob(response.job)
      setAnalysisResult(response.result || null)
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

  const summary = analysisResult?.summary_json ?? placeholderSummary
  const metricsRows = analysisResult?.metrics_json ?? placeholderMetrics
  const timelinePoints = analysisResult?.timeline_json ?? placeholderTimeline
  const segmentsRows = analysisResult?.segments_json ?? placeholderSegments
  const heatmapFrames = analysisResult?.visualizations_json.heatmap_frames ?? placeholderHeatmapFrames
  const highAttentionIntervals = analysisResult?.visualizations_json.high_attention_intervals ?? []
  const lowAttentionIntervals = analysisResult?.visualizations_json.low_attention_intervals ?? []
  const recommendations = analysisResult?.recommendations_json ?? []
  const summaryCards = buildSummaryCards(summary)
  const resultState = resolveResultState({
    analysisJob,
    analysisResult,
    uploadState,
  })
  const analysisCompleted = Boolean(analysisResult && (!analysisJob || analysisJob.status === 'completed'))
  const evaluationJobId = analysisResult?.job_id ?? analysisJob?.id ?? null

  return (
    <Stack spacing={3}>
      <Box className="dashboard-grid dashboard-grid--analysis">
        <Stack spacing={3}>
          <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
            <Stack spacing={2.5}>
              <Chip color="primary" label="Analysis workspace" sx={{ alignSelf: 'flex-start' }} />
              <Typography variant="h4">Upload media, confirm storage, then run TRIBE-backed analysis.</Typography>
              <Typography color="text.secondary" variant="body1">
                Uploads go directly to object storage, the worker resolves assets from R2-compatible storage,
                and the dashboard converts model output into marketer-friendly charts, segments, heatmaps, and recommendations.
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                {mediaTypeOptions.map((option) => {
                  const Icon = option.icon
                  const isSelected = option.kind === selectedMediaType
                  return (
                    <Button
                      color="inherit"
                      key={option.kind}
                      onClick={() => handleMediaTypeChange(option.kind)}
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
            </Stack>
          </Paper>

          <Paper className="dashboard-card analysis-upload-card" elevation={0}>
            <Stack spacing={2.5}>
              <Stack direction="row" spacing={1.5}>
                <Box
                  className="analysis-upload-card__icon"
                  sx={{ bgcolor: `${currentMediaOption.tone}1a`, color: currentMediaOption.tone }}
                >
                  <CurrentMediaIcon />
                </Box>
                <Box>
                  <Typography variant="h6">{currentMediaOption.title} input</Typography>
                  <Typography color="text.secondary" variant="body2">
                    {currentMediaOption.subtitle}
                  </Typography>
                </Box>
              </Stack>

              {selectedMediaType === 'text' ? (
                <Stack spacing={2}>
                  <TextField
                    minRows={8}
                    multiline
                    onChange={(event) => {
                      setTextContent(event.target.value)
                      resetWorkflowState(setUploadState, setAnalysisJob, setAnalysisResult, setBannerMessage)
                    }}
                    placeholder="Paste transcript copy, concept notes, or product narrative here."
                    value={textContent}
                  />
                  <Stack
                    alignItems={{ xs: 'stretch', sm: 'center' }}
                    direction={{ xs: 'column', sm: 'row' }}
                    justifyContent="space-between"
                    spacing={2}
                  >
                    <Typography color="text.secondary" variant="body2">
                      {textContent.length} / {config?.max_text_characters ?? '...'} characters
                    </Typography>
                    <Button component="label" startIcon={<FileUploadRounded />} variant="outlined">
                      Import `.txt`
                      <input accept=".txt,text/plain" hidden onChange={handleTextFileSelection} type="file" />
                    </Button>
                  </Stack>
                </Stack>
              ) : (
                <Box
                  className={`analysis-dropzone ${isDragActive ? 'is-active' : ''}`}
                  onDragEnter={(event) => {
                    event.preventDefault()
                    setIsDragActive(true)
                  }}
                  onDragLeave={(event) => {
                    event.preventDefault()
                    setIsDragActive(false)
                  }}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={handleDrop}
                >
                  <Stack alignItems="center" spacing={1.5}>
                    <CloudUploadRounded color="primary" />
                    <Typography variant="h6">Drop a {selectedMediaType} file here</Typography>
                    <Typography color="text.secondary" sx={{ textAlign: 'center' }} variant="body2">
                      Accepted mime types: {(config?.allowed_mime_types[selectedMediaType] || []).join(', ')}
                    </Typography>
                    <Button component="label" startIcon={<FileUploadRounded />} variant="outlined">
                      Choose file
                      <input
                        accept={(config?.allowed_mime_types[selectedMediaType] || []).join(',')}
                        hidden
                        onChange={handleBinaryFileSelection}
                        type="file"
                      />
                    </Button>
                  </Stack>
                </Box>
              )}

              <SelectedSourceSummary
                mediaType={selectedMediaType}
                selectedAsset={uploadState.asset}
                selectedFile={selectedFile}
                textContent={textContent}
                textFilename={textFilename}
              />

              <UploadedMediaLibrary
                activeAssetId={activeLibraryAssetId}
                assets={assetLibrary}
                errorMessage={assetLibraryError}
                hasLoaded={hasLoadedAssetLibrary}
                isLoading={isLoadingAssetLibrary}
                onReload={() => setAssetLibraryRefreshNonce((current) => current + 1)}
                onSelectAsset={handleSelectUploadedAsset}
              />

              {uploadState.stage === 'uploading' ? (
                <Stack spacing={1}>
                  <LinearProgress value={uploadState.progressPercent} variant="determinate" />
                  <Typography color="text.secondary" variant="body2">
                    Uploading directly to object storage: {uploadState.progressPercent}%
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

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                <Button
                  disabled={!canUpload}
                  onClick={handleUpload}
                  startIcon={<CloudUploadRounded />}
                  variant="contained"
                >
                  {uploadState.stage === 'uploaded' ? 'Upload replacement' : 'Upload media'}
                </Button>
                <Button
                  disabled={!canStartAnalysis}
                  onClick={handleStartAnalysis}
                  startIcon={<PlayCircleRounded />}
                  variant="outlined"
                >
                  {analysisJob?.status === 'failed' ? 'Retry analysis' : 'Start analysis'}
                </Button>
              </Stack>
            </Stack>
          </Paper>

          <Paper className="dashboard-card" elevation={0}>
            <Stack spacing={2}>
              <Typography variant="h6">Analysis objective</Typography>
              <Typography color="text.secondary" variant="body2">
                This context is stored with the queued job and reused when the worker builds the dashboard recommendations.
              </Typography>
              <TextField
                minRows={4}
                multiline
                onChange={(event) => setObjective(event.target.value)}
                placeholder="Example: Evaluate whether the opening hook is strong enough for a paid social launch."
                value={objective}
              />
            </Stack>
          </Paper>
        </Stack>

        <Stack spacing={3}>
          {bannerMessage ? <Alert severity={bannerMessage.type}>{bannerMessage.message}</Alert> : null}
          {configError ? <Alert severity="error">{configError}</Alert> : null}
          {isLoadingConfig ? <Alert severity="info">Loading analysis upload settings…</Alert> : null}

          <Paper className="dashboard-card" elevation={0}>
            <Stack spacing={2}>
              <Typography variant="h6">Flow status</Typography>
              <Chip
                className={`analysis-status-chip is-${currentStage}`}
                label={currentStage.toUpperCase()}
                sx={{ alignSelf: 'flex-start' }}
              />
              {stageRows(currentStage).map((row) => (
                <Box className={`analysis-stage-row ${row.isActive ? 'is-active' : ''}`} key={row.label}>
                  <Typography variant="subtitle2">{row.label}</Typography>
                  <Typography color="text.secondary" variant="body2">
                    {row.detail}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </Paper>

          <Paper className="dashboard-card" elevation={0}>
            <Stack spacing={2}>
              <Typography variant="h6">Current payload</Typography>
              <DetailRow label="Workspace" value={session.organizationName || 'Primary workspace'} />
              <DetailRow label="Project" value={session.defaultProjectName || 'Default Analysis Project'} />
              <DetailRow label="Selected media" value={currentMediaOption.title} />
              <DetailRow
                label="Selected asset"
                value={uploadState.asset?.original_filename || uploadState.asset?.object_key || 'No stored asset selected'}
              />
              <DetailRow label="Upload status" value={uploadState.asset?.upload_status || uploadState.stage} />
              <DetailRow
                label="Stored object"
                value={uploadState.asset?.object_key ? uploadState.asset.object_key : 'Not uploaded'}
              />
              <DetailRow
                label="Queued job"
                value={analysisJob ? `${shortenId(analysisJob.id)} (${analysisJob.status})` : 'Not started'}
              />
            </Stack>
          </Paper>

          <Paper className="dashboard-card" elevation={0}>
            <Stack spacing={2}>
              <Typography variant="h6">Storage validation</Typography>
              <Typography color="text.secondary" variant="body2">
                The upload session is only marked ready after the backend confirms the object exists in storage
                and creates a version reference for the async TRIBE worker.
              </Typography>
              <Stack spacing={1.25}>
                <ValidationRow label="Session token" value={sessionToken ? 'Attached' : 'Sign in again'} />
                <ValidationRow
                  label="Max file size"
                  value={config ? formatFileSize(config.max_file_size_bytes) : 'Loading…'}
                />
                <ValidationRow
                  label="Allowed mime types"
                  value={config ? config.allowed_mime_types[selectedMediaType].join(', ') : 'Loading…'}
                />
              </Stack>
            </Stack>
          </Paper>
        </Stack>
      </Box>

      <Box className="dashboard-grid dashboard-grid--metrics">
        {summaryCards.map((card) => (
          <Paper className="dashboard-card dashboard-card--metric" elevation={0} key={card.key}>
            <Stack direction="row" justifyContent="space-between" spacing={2}>
              <Box>
                <Typography color="text.secondary" variant="overline">
                  {card.label}
                </Typography>
                <Typography variant="h3">{analysisResult ? Math.round(card.value) : '--'}</Typography>
              </Box>
              <Chip icon={<AutoGraphRounded />} label="/100" size="small" variant="outlined" />
            </Stack>
            <Typography color="text.secondary" variant="body2">
              {analysisResult ? card.helper : 'Results will populate after the worker completes.'}
            </Typography>
          </Paper>
        ))}
      </Box>

      <ResultStateBanner resultState={resultState} analysisJob={analysisJob} />

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Metrics table</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Metric</TableCell>
                  <TableCell align="right">Value</TableCell>
                  <TableCell>Confidence</TableCell>
                  <TableCell>Source</TableCell>
                  <TableCell>Detail</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {metricsRows.map((metric) => (
                  <TableRow key={metric.key}>
                    <TableCell>{metric.label}</TableCell>
                    <TableCell align="right">
                      {analysisResult ? metric.value.toFixed(metric.unit === 'seconds' ? 2 : 1) : '--'} {metric.unit}
                    </TableCell>
                    <TableCell>{analysisResult ? formatOptionalScore(metric.confidence) : '--'}</TableCell>
                    <TableCell>{metric.source}</TableCell>
                    <TableCell>{analysisResult ? metric.detail || 'Derived dashboard metric' : 'Pending job output'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Timeline chart</Typography>
            <Typography color="text.secondary" variant="body2">
              Attention, engagement, and memory proxies aligned to processed timestamps.
            </Typography>
            <TimelineChart points={timelinePoints} />
          </Stack>
        </Paper>
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Scene / segment table</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Scene</TableCell>
                  <TableCell>Window</TableCell>
                  <TableCell align="right">Attention</TableCell>
                  <TableCell align="right">Delta</TableCell>
                  <TableCell>Note</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {segmentsRows.map((segment) => (
                  <TableRow key={`${segment.label}-${segment.start_time_ms}`}>
                    <TableCell>{segment.label}</TableCell>
                    <TableCell>
                      {formatDuration(segment.start_time_ms)} - {formatDuration(segment.end_time_ms)}
                    </TableCell>
                    <TableCell align="right">{analysisResult ? Math.round(segment.attention_score) : '--'}</TableCell>
                    <TableCell align="right">{analysisResult ? formatSignedValue(segment.engagement_delta) : '--'}</TableCell>
                    <TableCell>{analysisResult ? segment.note : 'Pending segmentation'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Attention heatmap overlays</Typography>
            <Typography color="text.secondary" variant="body2">
              Brain plots are intentionally replaced with grid-based timestamp overlays derived from the processed timeline.
            </Typography>
            <HeatmapFramesCard frames={heatmapFrames} hasResults={Boolean(analysisResult)} />
          </Stack>
        </Paper>
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">High and low attention intervals</Typography>
            <AttentionIntervalsCard
              hasResults={Boolean(analysisResult)}
              highAttentionIntervals={highAttentionIntervals}
              lowAttentionIntervals={lowAttentionIntervals}
            />
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Recommendations</Typography>
            <RecommendationsCard
              hasResults={Boolean(analysisResult)}
              recommendations={recommendations}
              summary={summary}
            />
          </Stack>
        </Paper>
      </Box>

      <AnalysisEvaluationSection
        analysisCompleted={analysisCompleted}
        jobId={evaluationJobId}
        sessionToken={sessionToken || null}
      />
    </Stack>
  )
}

function SelectedSourceSummary({
  mediaType,
  selectedAsset,
  selectedFile,
  textContent,
  textFilename,
}: {
  mediaType: MediaType
  selectedAsset?: AnalysisAsset
  selectedFile: File | null
  textContent: string
  textFilename: string
}) {
  if (selectedAsset && mediaType === selectedAsset.media_type && !selectedFile && !textContent.trim()) {
    return (
      <Box className="analysis-upload-card__file">
        <Box>
          <Typography variant="subtitle2">{selectedAsset.original_filename || 'Stored analysis asset'}</Typography>
          <Typography color="text.secondary" variant="body2">
            Ready from uploaded media library
            {selectedAsset.size_bytes ? ` · ${formatFileSize(selectedAsset.size_bytes)}` : ''}
          </Typography>
        </Box>
        <Chip color="success" label="Uploaded asset" size="small" variant="outlined" />
      </Box>
    )
  }

  if (mediaType === 'text') {
    return (
      <Box className="analysis-upload-card__file">
        <Box>
          <Typography variant="subtitle2">{textFilename}</Typography>
          <Typography color="text.secondary" variant="body2">
            {textContent.trim() ? `${textContent.length} characters prepared for upload` : 'No text prepared yet.'}
          </Typography>
        </Box>
        <Chip label="Text" size="small" variant="outlined" />
      </Box>
    )
  }

  return (
    <Box className="analysis-upload-card__file">
      <Box>
        <Typography variant="subtitle2">{selectedFile?.name || 'No file selected yet.'}</Typography>
        <Typography color="text.secondary" variant="body2">
          {selectedFile ? formatFileSize(selectedFile.size) : 'Pick or drop a file to continue.'}
        </Typography>
      </Box>
      <Chip label={selectedFile?.type || mediaType.toUpperCase()} size="small" variant="outlined" />
    </Box>
  )
}

function UploadedMediaLibrary({
  activeAssetId,
  assets,
  errorMessage,
  hasLoaded,
  isLoading,
  onReload,
  onSelectAsset,
}: {
  activeAssetId: string | null
  assets: AnalysisAsset[]
  errorMessage: string | null
  hasLoaded: boolean
  isLoading: boolean
  onReload: () => void
  onSelectAsset: (asset: AnalysisAsset) => void
}) {
  return (
    <Stack spacing={1.5}>
      <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
        <Box>
          <Typography variant="subtitle2">Uploaded media</Typography>
          <Typography color="text.secondary" variant="body2">
            `Choose file` can only browse your local device. Reuse anything already stored in Cloudflare R2 from this list.
          </Typography>
        </Box>
        <Button onClick={onReload} size="small" variant="text">
          Refresh list
        </Button>
      </Stack>

      {errorMessage ? <Alert severity="error">{errorMessage}</Alert> : null}

      {isLoading && assets.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            Loading uploaded assets…
          </Typography>
        </Box>
      ) : null}

      {!isLoading && hasLoaded && assets.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            No uploaded media is available for this input type yet.
          </Typography>
        </Box>
      ) : null}

      {assets.length > 0 ? (
        <Box className="analysis-asset-library">
          {assets.map((asset) => {
            const isSelected = asset.id === activeAssetId
            const isReady = asset.upload_status === 'uploaded'
            return (
              <Box className={`analysis-asset-library__item ${isSelected ? 'is-selected' : ''}`} key={asset.id}>
                <Stack
                  alignItems={{ xs: 'stretch', md: 'center' }}
                  direction={{ xs: 'column', md: 'row' }}
                  justifyContent="space-between"
                  spacing={1.5}
                >
                  <Box sx={{ minWidth: 0 }}>
                    <Typography sx={{ wordBreak: 'break-word' }} variant="subtitle2">
                      {asset.original_filename || asset.object_key}
                    </Typography>
                    <Typography color="text.secondary" sx={{ wordBreak: 'break-word' }} variant="body2">
                      {formatFileSize(asset.size_bytes || 0)} · uploaded {formatTimestamp(asset.created_at)}
                    </Typography>
                    <Typography color="text.secondary" sx={{ wordBreak: 'break-word' }} variant="caption">
                      {asset.object_key}
                    </Typography>
                  </Box>
                  <Stack alignItems={{ xs: 'stretch', md: 'center' }} direction={{ xs: 'column', md: 'row' }} spacing={1}>
                    <Button
                      disabled={!isReady}
                      onClick={() => onSelectAsset(asset)}
                      size="small"
                      variant={isSelected ? 'contained' : 'outlined'}
                    >
                      {isSelected ? 'Selected' : 'Use asset'}
                    </Button>
                  </Stack>
                </Stack>
              </Box>
            )
          })}
        </Box>
      ) : null}
    </Stack>
  )
}

function ResultStateBanner({
  resultState,
  analysisJob,
}: {
  resultState: 'empty' | 'loading' | 'partial' | 'ready' | 'failed'
  analysisJob: AnalysisJob | null
}) {
  if (resultState === 'ready') {
    return null
  }
  if (resultState === 'failed') {
    return <Alert severity="error">{analysisJob?.error_message || 'Analysis failed before results were produced.'}</Alert>
  }
  if (resultState === 'partial') {
    return <Alert severity="warning">The job completed, but the dashboard payload is still being fetched.</Alert>
  }
  if (resultState === 'loading') {
    return <Alert severity="info">The worker is building events, running TRIBE inference, and postprocessing dashboard outputs.</Alert>
  }
  return <Alert severity="info">Upload and queue an asset to populate summary cards, intervals, recommendations, and overlays.</Alert>
}

function TimelineChart({ points }: { points: AnalysisTimelinePoint[] }) {
  const width = 520
  const height = 200
  const engagementPath = buildSeriesPath(points, width, height, 'engagement_score')
  const attentionPath = buildSeriesPath(points, width, height, 'attention_score')
  const memoryPath = buildSeriesPath(points, width, height, 'memory_proxy')

  return (
    <Box className="analysis-timeline-chart">
      <svg aria-label="analysis timeline chart" viewBox={`0 0 ${width} ${height}`}>
        <path className="analysis-timeline-chart__grid" d={`M 0 ${height - 1} H ${width}`} />
        <path className="analysis-timeline-chart__line analysis-timeline-chart__line--engagement" d={engagementPath} />
        <path className="analysis-timeline-chart__line analysis-timeline-chart__line--attention" d={attentionPath} />
        <path className="analysis-timeline-chart__line analysis-timeline-chart__line--memory" d={memoryPath} />
      </svg>
      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        <LegendSwatch color="#f97316" label="Engagement" />
        <LegendSwatch color="#3b5bdb" label="Attention" />
        <LegendSwatch color="#14b8a6" label="Memory Proxy" />
      </Stack>
      <Stack direction="row" justifyContent="space-between" spacing={1}>
        {points.slice(0, 4).map((point) => (
          <Typography color="text.secondary" key={point.timestamp_ms} variant="caption">
            {formatDuration(point.timestamp_ms)}
          </Typography>
        ))}
      </Stack>
    </Box>
  )
}

function HeatmapFramesCard({
  frames,
  hasResults,
}: {
  frames: AnalysisHeatmapFrame[]
  hasResults: boolean
}) {
  return (
    <Box className="analysis-heatmap-frame-list">
      {frames.map((frame) => (
        <Box className="analysis-heatmap-frame" key={`${frame.label}-${frame.timestamp_ms}`}>
          <Stack direction="row" justifyContent="space-between" spacing={2}>
            <Box>
              <Typography variant="subtitle2">{frame.label}</Typography>
              <Typography color="text.secondary" variant="body2">
                {frame.scene_label} at {formatDuration(frame.timestamp_ms)}
              </Typography>
            </Box>
            <Chip label={formatZoneLabel(frame.strongest_zone)} size="small" variant="outlined" />
          </Stack>

          <Box
            className="analysis-heatmap-frame__grid"
            sx={{ gridTemplateColumns: `repeat(${frame.grid_columns}, minmax(44px, 1fr))` }}
          >
            {frame.intensity_map.flatMap((row, rowIndex) =>
              row.map((value, columnIndex) => (
                <Box
                  className="analysis-heatmap-frame__cell"
                  key={`${frame.timestamp_ms}-${rowIndex}-${columnIndex}`}
                  sx={{
                    bgcolor: `rgba(59, 91, 219, ${Math.max(0.08, Math.min(0.9, value / 100))})`,
                  }}
                >
                  <Typography variant="caption">{hasResults ? Math.round(value) : '--'}</Typography>
                </Box>
              )),
            )}
          </Box>

          <Typography color="text.secondary" variant="body2">
            {frame.caption}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}

function AttentionIntervalsCard({
  highAttentionIntervals,
  lowAttentionIntervals,
  hasResults,
}: {
  highAttentionIntervals: AnalysisInterval[]
  lowAttentionIntervals: AnalysisInterval[]
  hasResults: boolean
}) {
  return (
    <Box className="analysis-interval-grid">
      <IntervalColumn
        title="High attention"
        intervals={highAttentionIntervals}
        emptyLabel={hasResults ? 'No standout high-attention interval detected.' : 'Intervals will appear after analysis.'}
        tone="#0f766e"
      />
      <IntervalColumn
        title="Low attention"
        intervals={lowAttentionIntervals}
        emptyLabel={hasResults ? 'No low-attention dip detected.' : 'Intervals will appear after analysis.'}
        tone="#c2410c"
      />
    </Box>
  )
}

function IntervalColumn({
  title,
  intervals,
  emptyLabel,
  tone,
}: {
  title: string
  intervals: AnalysisInterval[]
  emptyLabel: string
  tone: string
}) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2">{title}</Typography>
      {intervals.length === 0 ? (
        <Box className="analysis-empty-state">
          <Typography color="text.secondary" variant="body2">
            {emptyLabel}
          </Typography>
        </Box>
      ) : (
        intervals.map((interval) => (
          <Box className="analysis-interval-card" key={`${title}-${interval.start_time_ms}`}>
            <Stack direction="row" justifyContent="space-between" spacing={2}>
              <Typography variant="subtitle2">
                {formatDuration(interval.start_time_ms)} - {formatDuration(interval.end_time_ms)}
              </Typography>
              <Chip
                label={`${Math.round(interval.average_attention_score)}/100`}
                size="small"
                sx={{ color: tone, borderColor: `${tone}55` }}
                variant="outlined"
              />
            </Stack>
            <Typography color="text.secondary" variant="body2">
              {interval.label}
            </Typography>
          </Box>
        ))
      )}
    </Stack>
  )
}

function RecommendationsCard({
  recommendations,
  hasResults,
  summary,
}: {
  recommendations: AnalysisRecommendation[]
  hasResults: boolean
  summary: AnalysisSummary
}) {
  if (!hasResults) {
    return (
      <Box className="analysis-empty-state">
        <Typography color="text.secondary" variant="body2">
          Recommendations are generated after postprocessing turns the TRIBE output into marketer-facing intervals and metrics.
        </Typography>
      </Box>
    )
  }

  if (recommendations.length === 0) {
    return (
      <Box className="analysis-empty-state">
        <Typography color="text.secondary" variant="body2">
          No recommendations were generated for this run. Summary confidence: {formatOptionalScore(summary.confidence)}.
        </Typography>
      </Box>
    )
  }

  return (
    <Stack spacing={1.5}>
      {recommendations.map((recommendation) => (
        <Box className="analysis-recommendation" key={`${recommendation.title}-${recommendation.timestamp_ms ?? 'na'}`}>
          <Stack direction="row" justifyContent="space-between" spacing={1.5}>
            <Typography variant="subtitle2">{recommendation.title}</Typography>
            <Chip
              className={`analysis-priority-chip analysis-priority-chip--${recommendation.priority}`}
              label={recommendation.priority}
              size="small"
              variant="outlined"
            />
          </Stack>
          <Typography color="text.secondary" variant="body2">
            {recommendation.detail}
          </Typography>
          <Stack direction="row" spacing={1.5}>
            <Typography color="text.secondary" variant="caption">
              {recommendation.timestamp_ms != null ? `Timestamp ${formatDuration(recommendation.timestamp_ms)}` : 'General recommendation'}
            </Typography>
            <Typography color="text.secondary" variant="caption">
              Confidence {formatOptionalScore(recommendation.confidence)}
            </Typography>
          </Stack>
        </Box>
      ))}
    </Stack>
  )
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <Stack alignItems="center" direction="row" spacing={1}>
      <Box sx={{ width: 12, height: 12, borderRadius: 999, bgcolor: color }} />
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
    </Stack>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
      <Typography sx={{ textAlign: 'right', wordBreak: 'break-word' }} variant="subtitle2">
        {value}
      </Typography>
    </Stack>
  )
}

function ValidationRow({ label, value }: { label: string; value: string }) {
  return (
    <Box className="analysis-stage-row">
      <Typography variant="subtitle2">{label}</Typography>
      <Typography color="text.secondary" variant="body2">
        {value}
      </Typography>
    </Box>
  )
}

function resetWorkflowState(
  setUploadState: Dispatch<SetStateAction<UploadState>>,
  setAnalysisJob: Dispatch<SetStateAction<AnalysisJob | null>>,
  setAnalysisResult: Dispatch<SetStateAction<AnalysisResult | null>>,
  setBannerMessage: Dispatch<SetStateAction<BannerMessage | null>>,
) {
  setUploadState({
    stage: 'idle',
    progressPercent: 0,
    validationErrors: [],
  })
  setAnalysisJob(null)
  setAnalysisResult(null)
  setBannerMessage(null)
}

function mergeLatestAnalysisAsset(currentAssets: AnalysisAsset[], nextAsset: AnalysisAsset) {
  return [nextAsset, ...currentAssets.filter((asset) => asset.id !== nextAsset.id)].slice(0, 12)
}

function buildSelectedAssetStorageKey(scope: string) {
  return `neuromarketer.analysis.selected-asset.${scope}`
}

function readSelectedAnalysisAssetId(storageKey: string) {
  if (typeof window === 'undefined') {
    return null
  }
  return window.sessionStorage.getItem(storageKey)
}

function storeSelectedAnalysisAssetId(storageKey: string, assetId: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(storageKey, assetId)
}

function validateCurrentInput({
  config,
  mediaType,
  selectedFile,
  textContent,
}: {
  config: AnalysisConfigResponse
  mediaType: MediaType
  selectedFile: File | null
  textContent: string
}) {
  const errors: string[] = []

  if (mediaType === 'text') {
    const trimmedText = textContent.trim()
    if (!trimmedText) {
      errors.push('Text analysis requires content in the textarea or a `.txt` import.')
    }
    if (trimmedText.length > config.max_text_characters) {
      errors.push(`Text analysis is limited to ${config.max_text_characters.toLocaleString()} characters.`)
    }
    return errors
  }

  if (!selectedFile) {
    errors.push(`Select a ${mediaType} file before starting the upload.`)
    return errors
  }

  if (selectedFile.size > config.max_file_size_bytes) {
    errors.push(`File size exceeds ${formatFileSize(config.max_file_size_bytes)}.`)
  }

  if (!config.allowed_mime_types[mediaType].includes(selectedFile.type)) {
    errors.push(`Unsupported ${mediaType} mime type: ${selectedFile.type || 'unknown'}.`)
  }

  return errors
}

function buildUploadSource({
  mediaType,
  selectedFile,
  textContent,
  textFilename,
}: {
  mediaType: MediaType
  selectedFile: File | null
  textContent: string
  textFilename: string
}): UploadSource | null {
  if (mediaType === 'text') {
    const trimmedText = textContent.trim()
    if (!trimmedText) {
      return null
    }
    const file = new Blob([trimmedText], { type: 'text/plain' })
    return {
      file,
      fileName: ensureTxtFilename(textFilename),
      mimeType: 'text/plain',
      sizeBytes: file.size,
    }
  }

  if (!selectedFile) {
    return null
  }

  return {
    file: selectedFile,
    fileName: selectedFile.name,
    mimeType: selectedFile.type,
    sizeBytes: selectedFile.size,
  }
}

function buildSummaryCards(summary: AnalysisSummary): SummaryCard[] {
  return [
    {
      key: 'overall_attention_score',
      label: 'Overall Attention',
      value: summary.overall_attention_score,
      helper: `Confidence ${formatOptionalScore(summary.confidence)}`,
    },
    {
      key: 'hook_score_first_3_seconds',
      label: 'Hook Score',
      value: summary.hook_score_first_3_seconds,
      helper: 'Opening 3-second hold strength',
    },
    {
      key: 'sustained_engagement_score',
      label: 'Sustained Engagement',
      value: summary.sustained_engagement_score,
      helper: 'Average engagement after the opening beat',
    },
    {
      key: 'memory_proxy_score',
      label: 'Memory Proxy',
      value: summary.memory_proxy_score,
      helper: `Coverage ${formatOptionalScore(summary.completeness)}`,
    },
    {
      key: 'cognitive_load_proxy',
      label: 'Cognitive Load',
      value: summary.cognitive_load_proxy,
      helper: 'Higher scores indicate more friction',
    },
  ]
}

function resolveCurrentStage(uploadStage: UploadStage, jobStatus?: AnalysisJob['status']) {
  if (jobStatus) {
    return jobStatus
  }
  if (uploadStage === 'validating') {
    return 'validating'
  }
  if (uploadStage === 'uploaded') {
    return 'uploaded'
  }
  if (uploadStage === 'uploading') {
    return 'uploading'
  }
  if (uploadStage === 'failed') {
    return 'failed'
  }
  return 'idle'
}

function resolveResultState({
  analysisJob,
  analysisResult,
  uploadState,
}: {
  analysisJob: AnalysisJob | null
  analysisResult: AnalysisResult | null
  uploadState: UploadState
}) {
  if (analysisJob?.status === 'failed') {
    return 'failed'
  }
  if (analysisResult) {
    return 'ready'
  }
  if (analysisJob?.status === 'completed') {
    return 'partial'
  }
  if (analysisJob?.status === 'queued' || analysisJob?.status === 'processing') {
    return 'loading'
  }
  if (uploadState.stage === 'validating') {
    return 'loading'
  }
  if (uploadState.stage === 'uploaded') {
    return 'empty'
  }
  return 'empty'
}

function stageRows(currentStage: string) {
  return [
    {
      label: 'Idle',
      detail: 'No asset is being prepared yet.',
      isActive: currentStage === 'idle',
    },
    {
      label: 'Validating',
      detail: 'Client-side validation is checking required fields, mime type, and size before upload.',
      isActive: currentStage === 'validating',
    },
    {
      label: 'Uploading',
      detail: 'The browser is streaming media directly into object storage.',
      isActive: currentStage === 'uploading',
    },
    {
      label: 'Uploaded',
      detail: 'The backend has confirmed the object and created the version reference.',
      isActive: currentStage === 'uploaded',
    },
    {
      label: 'Queued',
      detail: 'The worker job has been created and handed off to Celery.',
      isActive: currentStage === 'queued',
    },
    {
      label: 'Processing',
      detail: 'The worker is resolving the asset, generating events, running TRIBE, and postprocessing results.',
      isActive: currentStage === 'processing',
    },
    {
      label: 'Completed / Failed',
      detail: 'Results are available for rendering or the error payload is attached to the job.',
      isActive: currentStage === 'completed' || currentStage === 'failed',
    },
  ]
}

function buildSeriesPath(
  points: AnalysisTimelinePoint[],
  width: number,
  height: number,
  key: keyof Pick<AnalysisTimelinePoint, 'engagement_score' | 'attention_score' | 'memory_proxy'>,
) {
  if (points.length === 0) {
    return `M 0 ${height} L ${width} ${height}`
  }

  const step = points.length === 1 ? width : width / (points.length - 1)
  const commands = points.map((point, index) => {
    const rawValue = point[key] ?? 0
    const normalizedValue = Math.max(0, Math.min(100, rawValue))
    const x = index * step
    const y = height - (normalizedValue / 100) * (height - 12) - 6
    return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
  })
  return commands.join(' ')
}

function ensureTxtFilename(value: string) {
  const sanitized = value.trim() || 'analysis-notes.txt'
  return sanitized.endsWith('.txt') ? sanitized : `${sanitized}.txt`
}

function shortenId(value: string) {
  return `${value.slice(0, 8)}…`
}

function formatDuration(milliseconds: number) {
  const totalSeconds = Math.floor(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function formatFileSize(sizeInBytes: number) {
  if (sizeInBytes === 0) {
    return '0 B'
  }

  const units = ['B', 'KB', 'MB', 'GB']
  let unitIndex = 0
  let value = sizeInBytes

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }

  return `${value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`
}

function formatOptionalScore(value: number | null | undefined) {
  if (value == null) {
    return '--'
  }
  return `${Math.round(value)}%`
}

function formatSignedValue(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`
}

function formatZoneLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function formatTimestamp(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export default AnalysisPage
