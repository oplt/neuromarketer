import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded'
import CachedRounded from '@mui/icons-material/CachedRounded'
import LocalLibraryRounded from '@mui/icons-material/LocalLibraryRounded'
import MilitaryTechRounded from '@mui/icons-material/MilitaryTechRounded'
import SchoolRounded from '@mui/icons-material/SchoolRounded'
import ShareRounded from '@mui/icons-material/ShareRounded'
import TrendingUpRounded from '@mui/icons-material/TrendingUpRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import { startTransition, useEffect, useEffectEvent, useMemo, useState } from 'react'

import { apiRequest } from '../../lib/api'

export type AnalysisEvaluationMode = 'educational' | 'defence' | 'marketing' | 'social_media'
type AnalysisEvaluationStatus = 'queued' | 'processing' | 'completed' | 'failed'

type Severity = 'low' | 'medium' | 'high'
type Priority = 'low' | 'medium' | 'high'

type AnalysisEvaluationScoreReason = {
  score: number
  reason: string
}

type AnalysisEvaluationResult = {
  mode: AnalysisEvaluationMode
  overall_verdict: string
  summary: string
  scores: {
    clarity: number
    engagement: number
    retention: number
    fit_for_purpose: number
    risk: number
  }
  strengths: string[]
  weaknesses: string[]
  risks: Array<{
    severity: Severity
    label: string
    description: string
    timestamp_start?: number | null
    timestamp_end?: number | null
  }>
  recommendations: Array<{
    priority: Priority
    action: string
    reason: string
    timestamp_start?: number | null
    timestamp_end?: number | null
  }>
  scorecard: {
    hook_or_opening: AnalysisEvaluationScoreReason
    message_clarity: AnalysisEvaluationScoreReason
    pacing: AnalysisEvaluationScoreReason
    attention_alignment: AnalysisEvaluationScoreReason
    domain_effectiveness: AnalysisEvaluationScoreReason
  }
  model_metadata: {
    provider: string
    model: string
    tokens_in: number
    tokens_out: number
  }
  educational_summary?: string | null
  comprehension_risks?: string[]
  pacing_feedback?: string | null
  retention_feedback?: string | null
  accessibility_feedback?: string | null
  defence_summary?: string | null
  operational_clarity_assessment?: string | null
  ambiguity_risks?: string[]
  overload_risks?: string[]
  safety_or_misuse_flags?: string[]
  marketing_summary?: string | null
  hook_assessment?: string | null
  value_prop_assessment?: string | null
  conversion_friction_points?: string[]
  brand_alignment_feedback?: string | null
  social_summary?: string | null
  scroll_stop_assessment?: string | null
  retention_assessment?: string | null
  platform_fit_feedback?: string | null
  shareability_feedback?: string | null
}

type AnalysisEvaluationRecord = {
  id: string
  job_id: string
  user_id: string
  mode: AnalysisEvaluationMode
  status: AnalysisEvaluationStatus
  model_provider?: string | null
  model_name?: string | null
  prompt_version?: string | null
  evaluation_json?: AnalysisEvaluationResult | null
  error_message?: string | null
  created_at: string
  updated_at: string
}

type AnalysisEvaluationListResponse = {
  items: AnalysisEvaluationRecord[]
}

type AnalysisEvaluationSectionProps = {
  sessionToken: string | null
  jobId: string | null
  analysisCompleted: boolean
}

const modeDefinitions: Array<{
  mode: AnalysisEvaluationMode
  label: string
  description: string
  icon: typeof SchoolRounded
  tone: string
}> = [
  {
    mode: 'educational',
    label: 'Educational',
    description: 'Clarity, pacing, cognitive load, retention, and accessibility.',
    icon: SchoolRounded,
    tone: '#2563eb',
  },
  {
    mode: 'defence',
    label: 'Defence',
    description: 'Operational clarity, ambiguity reduction, overload risk, and safer communication posture.',
    icon: MilitaryTechRounded,
    tone: '#b45309',
  },
  {
    mode: 'marketing',
    label: 'Marketing',
    description: 'Hook quality, value proposition, persuasion flow, CTA, and conversion friction.',
    icon: TrendingUpRounded,
    tone: '#0f766e',
  },
  {
    mode: 'social_media',
    label: 'Social media',
    description: 'Scroll-stop power, pacing density, platform fit, and shareability.',
    icon: ShareRounded,
    tone: '#be185d',
  },
]

function AnalysisEvaluationSection({
  sessionToken,
  jobId,
  analysisCompleted,
}: AnalysisEvaluationSectionProps) {
  const [selectedModes, setSelectedModes] = useState<AnalysisEvaluationMode[]>([])
  const [recordsByMode, setRecordsByMode] = useState<Record<string, AnalysisEvaluationRecord>>({})
  const [isLoading, setIsLoading] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [requestError, setRequestError] = useState<string | null>(null)

  const applyResponse = (response: AnalysisEvaluationListResponse) => {
    startTransition(() => {
      setRecordsByMode((current) => {
        const next = { ...current }
        response.items.forEach((item) => {
          next[item.mode] = item
        })
        return next
      })
      setSelectedModes((current) => {
        if (current.length > 0) {
          return current
        }
        return response.items.map((item) => item.mode)
      })
    })
  }

  const loadEvaluations = useEffectEvent(async () => {
    if (!sessionToken || !jobId || !analysisCompleted) {
      startTransition(() => {
        setRecordsByMode({})
        setRequestError(null)
      })
      return
    }

    setIsLoading(true)
    try {
      const response = await apiRequest<AnalysisEvaluationListResponse>(
        `/api/v1/analysis/jobs/${jobId}/evaluations`,
        { sessionToken },
      )
      applyResponse(response)
      setRequestError(null)
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'Unable to load LLM evaluations.')
    } finally {
      setIsLoading(false)
    }
  })

  const requestEvaluations = async (forceRefresh: boolean) => {
    if (!sessionToken || !jobId || selectedModes.length === 0) {
      return
    }

    setIsSubmitting(true)
    try {
      const response = await apiRequest<AnalysisEvaluationListResponse>(
        `/api/v1/analysis/jobs/${jobId}/evaluate`,
        {
          method: 'POST',
          sessionToken,
          body: {
            modes: selectedModes,
            force_refresh: forceRefresh,
          },
        },
      )
      applyResponse(response)
      setRequestError(null)
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'Unable to request LLM evaluations.')
    } finally {
      setIsSubmitting(false)
    }
  }

  useEffect(() => {
    void loadEvaluations()
  }, [analysisCompleted, jobId, sessionToken])

  useEffect(() => {
    if (!sessionToken || !jobId) {
      return
    }
    const activeRecords = Object.values(recordsByMode)
    if (!activeRecords.some((record) => record.status === 'queued' || record.status === 'processing')) {
      return
    }
    const intervalId = window.setInterval(() => {
      void loadEvaluations()
    }, 3_500)
    return () => {
      window.clearInterval(intervalId)
    }
  }, [jobId, recordsByMode, sessionToken])

  const selectedRecords = useMemo(
    () => selectedModes.map((mode) => recordsByMode[mode]).filter(Boolean),
    [recordsByMode, selectedModes],
  )
  const hasExistingSelection = selectedModes.some((mode) => Boolean(recordsByMode[mode]))

  return (
    <Stack spacing={3}>
      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2.5}>
          <Stack alignItems={{ md: 'center' }} direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
            <Box>
              <Stack alignItems="center" direction="row" spacing={1}>
                <Chip color="primary" icon={<AutoAwesomeRounded />} label="LLM evaluation" size="small" />
                <Typography variant="h6">Interpret the completed analysis through domain lenses.</Typography>
              </Stack>
              <Typography color="text.secondary" sx={{ mt: 1 }} variant="body2">
                The model reads the structured analysis output, not the raw media, and produces domain-specific critique,
                risk flags, and recommendations for educational, defence, marketing, or social media review.
              </Typography>
            </Box>
            <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} spacing={1.25}>
              <Button
                disabled={!analysisCompleted || selectedModes.length === 0 || isSubmitting}
                onClick={() => void requestEvaluations(false)}
                startIcon={<LocalLibraryRounded />}
                variant="contained"
              >
                {isSubmitting ? 'Submitting…' : 'Generate evaluation'}
              </Button>
              <Button
                disabled={!analysisCompleted || selectedModes.length === 0 || !hasExistingSelection || isSubmitting}
                onClick={() => void requestEvaluations(true)}
                startIcon={<CachedRounded />}
                variant="outlined"
              >
                Refresh selected
              </Button>
            </Stack>
          </Stack>

          <Box className="analysis-evaluation-mode-grid" data-testid="evaluation-mode-selector">
            {modeDefinitions.map((definition) => {
              const Icon = definition.icon
              const isSelected = selectedModes.includes(definition.mode)
              return (
                <Button
                  color="inherit"
                  key={definition.mode}
                  onClick={() => setSelectedModes((current) => toggleMode(current, definition.mode))}
                  sx={{
                    justifyContent: 'flex-start',
                    borderRadius: '20px',
                    border: `1px solid ${isSelected ? definition.tone : 'rgba(24, 34, 48, 0.08)'}`,
                    bgcolor: isSelected ? `${definition.tone}12` : 'rgba(248, 250, 252, 0.72)',
                    color: isSelected ? definition.tone : 'text.primary',
                    px: 2,
                    py: 1.5,
                  }}
                  variant="text"
                >
                  <Stack direction="row" spacing={1.25} sx={{ textAlign: 'left' }}>
                    <Icon fontSize="small" />
                    <Box>
                      <Typography variant="subtitle2">{definition.label}</Typography>
                      <Typography color="inherit" sx={{ opacity: 0.78 }} variant="body2">
                        {definition.description}
                      </Typography>
                    </Box>
                  </Stack>
                </Button>
              )
            })}
          </Box>

          {!analysisCompleted ? (
            <Alert severity="info">LLM evaluation becomes available after the core analysis job is completed.</Alert>
          ) : null}
          {requestError ? <Alert severity="error">{requestError}</Alert> : null}
          {isLoading ? <LinearProgress /> : null}
        </Stack>
      </Paper>

      {selectedModes.length === 0 ? (
        <Paper className="dashboard-card" elevation={0}>
          <Box className="analysis-empty-state">
            <Typography color="text.secondary" variant="body2">
              Select one or more evaluation modes to compare how the same analysis result reads across different domains.
            </Typography>
          </Box>
        </Paper>
      ) : null}

      {selectedModes.length > 0 ? (
        <Box className="analysis-evaluation-grid" data-testid="evaluation-comparison-grid">
          {selectedModes.map((mode) => (
            <EvaluationModeCard
              key={mode}
              mode={mode}
              record={recordsByMode[mode] ?? null}
            />
          ))}
        </Box>
      ) : null}

      {selectedRecords.length > 1 ? (
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={1.5}>
            <Typography variant="h6">Comparison snapshot</Typography>
            <Typography color="text.secondary" variant="body2">
              Side-by-side scores make it easier to spot where the same content is strong for one objective but weak for another.
            </Typography>
            <Box className="analysis-evaluation-summary-row">
              {selectedRecords.map((record) => (
                <Box className="analysis-evaluation-summary-card" key={`summary-${record.mode}`}>
                  <Typography variant="subtitle2">{toModeLabel(record.mode)}</Typography>
                  <Typography variant="h4">
                    {record.evaluation_json ? Math.round(record.evaluation_json.scores.fit_for_purpose) : '--'}
                  </Typography>
                  <Typography color="text.secondary" variant="body2">
                    Fit for purpose
                  </Typography>
                </Box>
              ))}
            </Box>
          </Stack>
        </Paper>
      ) : null}
    </Stack>
  )
}

function EvaluationModeCard({
  mode,
  record,
}: {
  mode: AnalysisEvaluationMode
  record: AnalysisEvaluationRecord | null
}) {
  const definition = modeDefinitions.find((item) => item.mode === mode) ?? modeDefinitions[0]
  const evaluation = record?.evaluation_json ?? null
  const domainSections = evaluation ? buildDomainSections(evaluation) : []

  return (
    <Paper className="dashboard-card analysis-evaluation-card" data-testid={`evaluation-card-${mode}`} elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ md: 'center' }} direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">{definition.label}</Typography>
            <Typography color="text.secondary" variant="body2">
              {definition.description}
            </Typography>
          </Box>
          <Chip
            className={`analysis-status-chip is-${record?.status ?? 'idle'}`}
            label={(record?.status ?? 'idle').toUpperCase()}
            sx={{ alignSelf: 'flex-start' }}
          />
        </Stack>

        {record?.status === 'queued' || record?.status === 'processing' ? <LinearProgress /> : null}
        {record?.error_message ? (
          <Alert severity={evaluation ? 'warning' : 'error'}>
            {evaluation
              ? `Refresh failed: ${record.error_message}. Showing the previous cached evaluation.`
              : record.error_message}
          </Alert>
        ) : null}

        {!record ? (
          <Box className="analysis-empty-state">
            <Typography color="text.secondary" variant="body2">
              No evaluation has been requested for this mode yet.
            </Typography>
          </Box>
        ) : null}

        {evaluation ? (
          <Stack spacing={2}>
            <Box>
              <Typography variant="subtitle1">{evaluation.overall_verdict}</Typography>
              <Typography color="text.secondary" sx={{ mt: 0.75 }} variant="body2">
                {evaluation.summary}
              </Typography>
            </Box>

            <Box className="analysis-evaluation-score-grid">
              <ScorePill label="Clarity" value={evaluation.scores.clarity} />
              <ScorePill label="Engagement" value={evaluation.scores.engagement} />
              <ScorePill label="Retention" value={evaluation.scores.retention} />
              <ScorePill label="Fit" value={evaluation.scores.fit_for_purpose} />
              <ScorePill label="Risk" tone="risk" value={evaluation.scores.risk} />
            </Box>

            <Divider />

            <Stack spacing={1.25}>
              <Typography variant="subtitle2">Strengths</Typography>
              <ListBlock items={evaluation.strengths} emptyLabel="No strengths were returned." />
            </Stack>

            <Stack spacing={1.25}>
              <Typography variant="subtitle2">Weaknesses</Typography>
              <ListBlock items={evaluation.weaknesses} emptyLabel="No weaknesses were returned." />
            </Stack>

            {domainSections.map((section) => (
              <Stack key={section.label} spacing={1}>
                <Typography variant="subtitle2">{section.label}</Typography>
                {section.kind === 'list' ? (
                  <ListBlock items={section.items} emptyLabel={`No ${section.label.toLowerCase()} noted.`} />
                ) : (
                  <Typography color="text.secondary" variant="body2">
                    {section.text}
                  </Typography>
                )}
              </Stack>
            ))}

            <Stack spacing={1.25}>
              <Typography variant="subtitle2">Risks</Typography>
              {evaluation.risks.length === 0 ? (
                <Box className="analysis-empty-state">
                  <Typography color="text.secondary" variant="body2">
                    No explicit risk entries were returned.
                  </Typography>
                </Box>
              ) : (
                evaluation.risks.map((risk) => (
                  <Box className="analysis-evaluation-item" key={`${risk.label}-${risk.timestamp_start ?? 'na'}`}>
                    <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1}>
                      <Typography variant="subtitle2">{risk.label}</Typography>
                      <Chip
                        className={`analysis-priority-chip analysis-priority-chip--${risk.severity}`}
                        label={risk.severity}
                        size="small"
                        variant="outlined"
                      />
                    </Stack>
                    <Typography color="text.secondary" variant="body2">
                      {risk.description}
                    </Typography>
                    <Typography color="text.secondary" variant="caption">
                      {formatTimestampRange(risk.timestamp_start, risk.timestamp_end)}
                    </Typography>
                  </Box>
                ))
              )}
            </Stack>

            <Stack spacing={1.25}>
              <Typography variant="subtitle2">Recommendations</Typography>
              {evaluation.recommendations.length === 0 ? (
                <Box className="analysis-empty-state">
                  <Typography color="text.secondary" variant="body2">
                    No recommendations were returned.
                  </Typography>
                </Box>
              ) : (
                evaluation.recommendations.map((recommendation) => (
                  <Box className="analysis-evaluation-item" key={`${recommendation.action}-${recommendation.timestamp_start ?? 'na'}`}>
                    <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1}>
                      <Typography variant="subtitle2">{recommendation.action}</Typography>
                      <Chip
                        className={`analysis-priority-chip analysis-priority-chip--${recommendation.priority}`}
                        label={recommendation.priority}
                        size="small"
                        variant="outlined"
                      />
                    </Stack>
                    <Typography color="text.secondary" variant="body2">
                      {recommendation.reason}
                    </Typography>
                    <Typography color="text.secondary" variant="caption">
                      {formatTimestampRange(recommendation.timestamp_start, recommendation.timestamp_end)}
                    </Typography>
                  </Box>
                ))
              )}
            </Stack>

            <Stack spacing={1.25}>
              <Typography variant="subtitle2">Scorecard</Typography>
              <Box className="analysis-evaluation-scorecard-grid">
                <ScorecardTile label="Hook / opening" value={evaluation.scorecard.hook_or_opening} />
                <ScorecardTile label="Message clarity" value={evaluation.scorecard.message_clarity} />
                <ScorecardTile label="Pacing" value={evaluation.scorecard.pacing} />
                <ScorecardTile label="Attention alignment" value={evaluation.scorecard.attention_alignment} />
                <ScorecardTile label="Domain effectiveness" value={evaluation.scorecard.domain_effectiveness} />
              </Box>
            </Stack>

            <Typography color="text.secondary" variant="caption">
              Model: {evaluation.model_metadata.provider} / {evaluation.model_metadata.model} · tokens in{' '}
              {evaluation.model_metadata.tokens_in} · tokens out {evaluation.model_metadata.tokens_out}
            </Typography>
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  )
}

function ScorePill({
  label,
  tone = 'default',
  value,
}: {
  label: string
  tone?: 'default' | 'risk'
  value: number
}) {
  return (
    <Box className={`analysis-evaluation-pill ${tone === 'risk' ? 'is-risk' : ''}`}>
      <Typography color="text.secondary" variant="caption">
        {label}
      </Typography>
      <Typography variant="h6">{Math.round(value)}</Typography>
    </Box>
  )
}

function ScorecardTile({
  label,
  value,
}: {
  label: string
  value: AnalysisEvaluationScoreReason
}) {
  return (
    <Box className="analysis-evaluation-scorecard-tile">
      <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={1}>
        <Typography variant="subtitle2">{label}</Typography>
        <Chip label={`${Math.round(value.score)}/100`} size="small" variant="outlined" />
      </Stack>
      <Typography color="text.secondary" variant="body2">
        {value.reason}
      </Typography>
    </Box>
  )
}

function ListBlock({
  items,
  emptyLabel,
}: {
  items: string[]
  emptyLabel: string
}) {
  if (items.length === 0) {
    return (
      <Box className="analysis-empty-state">
        <Typography color="text.secondary" variant="body2">
          {emptyLabel}
        </Typography>
      </Box>
    )
  }

  return (
    <Box className="analysis-evaluation-list">
      {items.map((item) => (
        <Box className="analysis-evaluation-list__item" key={item}>
          <Typography color="text.secondary" variant="body2">
            {item}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}

function buildDomainSections(result: AnalysisEvaluationResult): Array<
  | { kind: 'text'; label: string; text: string }
  | { kind: 'list'; label: string; items: string[] }
> {
  if (result.mode === 'educational') {
    return [
      maybeTextSection('Educational summary', result.educational_summary),
      maybeListSection('Comprehension risks', result.comprehension_risks || []),
      maybeTextSection('Pacing feedback', result.pacing_feedback),
      maybeTextSection('Retention feedback', result.retention_feedback),
      maybeTextSection('Accessibility feedback', result.accessibility_feedback),
    ].filter(Boolean) as Array<{ kind: 'text'; label: string; text: string } | { kind: 'list'; label: string; items: string[] }>
  }

  if (result.mode === 'defence') {
    return [
      maybeTextSection('Defence summary', result.defence_summary),
      maybeTextSection('Operational clarity', result.operational_clarity_assessment),
      maybeListSection('Ambiguity risks', result.ambiguity_risks || []),
      maybeListSection('Overload risks', result.overload_risks || []),
      maybeListSection('Safety or misuse flags', result.safety_or_misuse_flags || []),
    ].filter(Boolean) as Array<{ kind: 'text'; label: string; text: string } | { kind: 'list'; label: string; items: string[] }>
  }

  if (result.mode === 'marketing') {
    return [
      maybeTextSection('Marketing summary', result.marketing_summary),
      maybeTextSection('Hook assessment', result.hook_assessment),
      maybeTextSection('Value proposition', result.value_prop_assessment),
      maybeListSection('Conversion friction points', result.conversion_friction_points || []),
      maybeTextSection('Brand alignment', result.brand_alignment_feedback),
    ].filter(Boolean) as Array<{ kind: 'text'; label: string; text: string } | { kind: 'list'; label: string; items: string[] }>
  }

  return [
    maybeTextSection('Social summary', result.social_summary),
    maybeTextSection('Scroll-stop assessment', result.scroll_stop_assessment),
    maybeTextSection('Retention assessment', result.retention_assessment),
    maybeTextSection('Platform fit', result.platform_fit_feedback),
    maybeTextSection('Shareability', result.shareability_feedback),
  ].filter(Boolean) as Array<{ kind: 'text'; label: string; text: string } | { kind: 'list'; label: string; items: string[] }>
}

function maybeTextSection(label: string, text?: string | null) {
  if (!text) {
    return null
  }
  return { kind: 'text' as const, label, text }
}

function maybeListSection(label: string, items: string[]) {
  if (items.length === 0) {
    return null
  }
  return { kind: 'list' as const, label, items }
}

function toggleMode(current: AnalysisEvaluationMode[], nextMode: AnalysisEvaluationMode) {
  if (current.includes(nextMode)) {
    return current.filter((mode) => mode !== nextMode)
  }
  return [...current, nextMode]
}

function toModeLabel(mode: AnalysisEvaluationMode) {
  return modeDefinitions.find((item) => item.mode === mode)?.label ?? mode
}

function formatTimestampRange(start?: number | null, end?: number | null) {
  if (start == null && end == null) {
    return 'General recommendation'
  }
  if (start != null && end != null) {
    return `${formatDuration(start)} - ${formatDuration(end)}`
  }
  return formatDuration(start ?? end ?? 0)
}

function formatDuration(milliseconds: number) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export default AnalysisEvaluationSection
