import CloseRounded from '@mui/icons-material/CloseRounded'
import InsightsRounded from '@mui/icons-material/InsightsRounded'
import TuneRounded from '@mui/icons-material/TuneRounded'
import {
  Box,
  Button,
  Chip,
  Drawer,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { memo, useMemo, useState, type ReactNode } from 'react'
import MetricsRadarCard from '../../../components/analysis/MetricsRadarCard'
import ResponsiveTableCard from '../../../components/common/ResponsiveTableCard'
import {
  findComparisonItemLabel,
  formatNumber,
  formatSignedNumber,
  readableMetric,
  resolveComparisonItemLabel,
} from '../utils'
import type { AnalysisComparison, AnalysisComparisonItem } from '../types'
import CompareHeatstripCard from './CompareHeatstripCard'
import ScoreGaugesComparison from './ScoreGaugesComparison'

type ComparisonResultsProps = {
  comparison: AnalysisComparison
}

type MetricLeader = {
  metric: string
  analysis_job_id: string
  value: number
}

function ComparisonResultsBase({ comparison }: ComparisonResultsProps) {
  const [detailsOpen, setDetailsOpen] = useState(false)
  const winner = useMemo(
    () => comparison.items.find((item) => item.is_winner) || comparison.items[0] || null,
    [comparison.items],
  )
  const baseline = useMemo(
    () => comparison.items.find((item) => item.is_baseline) || comparison.items[0] || null,
    [comparison.items],
  )
  const challengers = useMemo(
    () => comparison.items.filter((item) => !item.is_baseline),
    [comparison.items],
  )
  const metricLeaders = useMemo(
    () =>
      Array.isArray(comparison.summary_json.metric_leaders)
        ? (comparison.summary_json.metric_leaders as MetricLeader[])
        : [],
    [comparison.summary_json.metric_leaders],
  )
  const radarSeries = useMemo(
    () =>
      comparison.items.map((item) => ({
        label: resolveComparisonItemLabel(item),
        metrics: item.result.metrics_json,
      })),
    [comparison.items],
  )
  const insights = useMemo(
    () => buildInsights(comparison, winner, baseline, metricLeaders),
    [baseline, comparison, metricLeaders, winner],
  )
  const recommendations = useMemo(
    () => buildRecommendations(challengers),
    [challengers],
  )

  if (!winner || !baseline) {
    return null
  }

  return (
    <Stack className="compare-results" spacing={3}>
      <Stack
        alignItems={{ xs: 'stretch', md: 'center' }}
        direction={{ xs: 'column', md: 'row' }}
        justifyContent="space-between"
        spacing={2}
      >
        <Box>
          <Typography color="primary" variant="overline">
            Step 3
          </Typography>
          <Typography variant="h5">Comparison results</Typography>
        </Box>
        <Button onClick={() => setDetailsOpen(true)} startIcon={<TuneRounded />} variant="outlined">
          View technical details
        </Button>
      </Stack>

      <ComparisonSummary comparison={comparison} metricLeaders={metricLeaders} winner={winner} />
      <SideBySideTable baseline={baseline} items={comparison.items} />
      <InsightsPanel insights={insights} />
      <RecommendationsPanel recommendations={recommendations} />

      <TechnicalDetailsDrawer onClose={() => setDetailsOpen(false)} open={detailsOpen}>
        <ScoreGaugesComparison items={comparison.items} />
        <MetricsRadarCard
          description="Persisted metric rows across selected results."
          emptyMessage="Radar appears when enough shared metrics exist."
          series={radarSeries}
          testId="compare-metrics-radar"
          title="Metrics radar"
        />
        {challengers.map((item) => (
          <TechnicalChallengerSection baseline={baseline} item={item} key={item.analysis_job_id} />
        ))}
      </TechnicalDetailsDrawer>
    </Stack>
  )
}

type ComparisonSummaryProps = {
  comparison: AnalysisComparison
  metricLeaders: MetricLeader[]
  winner: AnalysisComparisonItem
}

function ComparisonSummaryBase({ comparison, metricLeaders, winner }: ComparisonSummaryProps) {
  return (
    <Paper className="compare-summary-panel" elevation={0}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Chip color="success" icon={<InsightsRounded />} label="Winner" />
          <Chip label={comparison.name} variant="outlined" />
        </Stack>
        <Typography variant="h4">{resolveComparisonItemLabel(winner)}</Typography>
        <Typography color="text.secondary" variant="body1">
          {String(comparison.summary_json.winning_rationale || winner.rationale || 'This asset leads the comparison.')}
        </Typography>
        <Box className="compare-score-grid">
          <ScoreTile label="Composite" value={formatNumber(winner.scores_json.composite)} />
          <ScoreTile label="Attention" value={formatNumber(winner.scores_json.overall_attention)} />
          <ScoreTile label="Hook" value={formatNumber(winner.scores_json.hook)} />
          <ScoreTile label="Memory" value={formatNumber(winner.scores_json.memory_proxy)} />
        </Box>
        {metricLeaders.length > 0 ? (
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {metricLeaders.slice(0, 4).map((leader) => (
              <Chip
                key={`${leader.metric}-${leader.analysis_job_id}`}
                label={`${readableMetric(leader.metric)} ${formatNumber(leader.value)}`}
                size="small"
                variant="outlined"
              />
            ))}
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  )
}

function ScoreTile({ label, value }: { label: string; value: string }) {
  return (
    <Box className="compare-score-tile">
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
      <Typography variant="h5">{value}</Typography>
    </Box>
  )
}

type SideBySideTableProps = {
  baseline: AnalysisComparisonItem
  items: AnalysisComparisonItem[]
}

function SideBySideTableBase({ baseline, items }: SideBySideTableProps) {
  const rows = [
    { key: 'overall_rank', label: 'Rank', read: (item: AnalysisComparisonItem) => String(item.overall_rank) },
    { key: 'composite', label: 'Composite', read: (item: AnalysisComparisonItem) => formatNumber(item.scores_json.composite) },
    {
      key: 'delta',
      label: 'Delta vs baseline',
      read: (item: AnalysisComparisonItem) =>
        item.is_baseline ? 'Baseline' : formatSignedNumber(item.delta_json.composite),
    },
    {
      key: 'attention',
      label: 'Attention',
      read: (item: AnalysisComparisonItem) => formatNumber(item.scores_json.overall_attention),
    },
    { key: 'hook', label: 'Hook', read: (item: AnalysisComparisonItem) => formatNumber(item.scores_json.hook) },
    {
      key: 'memory',
      label: 'Memory',
      read: (item: AnalysisComparisonItem) => formatNumber(item.scores_json.memory_proxy),
    },
    {
      key: 'load',
      label: 'Low load',
      read: (item: AnalysisComparisonItem) => formatNumber(item.scores_json.low_cognitive_load),
    },
  ]

  return (
    <Paper className="compare-results-section" elevation={0}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Typography variant="h6">Side-by-side</Typography>
          <Chip label={`Baseline: ${resolveComparisonItemLabel(baseline)}`} size="small" variant="outlined" />
        </Stack>
        <ResponsiveTableCard ariaLabel="Side-by-side comparison table" maxHeight={420} minWidth={760}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Metric</TableCell>
                {items.map((item) => (
                  <TableCell align="right" key={item.analysis_job_id}>
                    {resolveComparisonItemLabel(item)}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.key}>
                  <TableCell>{row.label}</TableCell>
                  {items.map((item) => (
                    <TableCell align="right" key={`${row.key}-${item.analysis_job_id}`}>
                      {row.read(item)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ResponsiveTableCard>
      </Stack>
    </Paper>
  )
}

function InsightsPanelBase({ insights }: { insights: string[] }) {
  return (
    <Paper className="compare-results-section" elevation={0}>
      <Stack spacing={1.5}>
        <Typography variant="h6">Insights</Typography>
        <Stack component="ul" className="compare-bullet-list" spacing={1}>
          {insights.map((insight) => (
            <Typography component="li" key={insight} variant="body2">
              {insight}
            </Typography>
          ))}
        </Stack>
      </Stack>
    </Paper>
  )
}

function RecommendationsPanelBase({ recommendations }: { recommendations: string[] }) {
  return (
    <Paper className="compare-results-section" elevation={0}>
      <Stack spacing={1.5}>
        <Typography variant="h6">Recommendations</Typography>
        <Stack component="ul" className="compare-bullet-list" spacing={1}>
          {recommendations.map((recommendation) => (
            <Typography component="li" key={recommendation} variant="body2">
              {recommendation}
            </Typography>
          ))}
        </Stack>
      </Stack>
    </Paper>
  )
}

type TechnicalChallengerSectionProps = {
  baseline: AnalysisComparisonItem
  item: AnalysisComparisonItem
}

function TechnicalChallengerSectionBase({ baseline, item }: TechnicalChallengerSectionProps) {
  const showHeatstrip =
    (baseline.result.segments_json.length ?? 0) > 0 || item.result.segments_json.length > 0

  return (
    <Paper className="compare-results-section" elevation={0}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <Typography variant="h6">{resolveComparisonItemLabel(item)}</Typography>
          <Chip label={`Composite ${formatSignedNumber(item.delta_json.composite)}`} size="small" variant="outlined" />
          <Chip label={`Hook ${formatSignedNumber(item.delta_json.hook)}`} size="small" variant="outlined" />
        </Stack>

        {showHeatstrip ? <CompareHeatstripCard baseline={baseline} challenger={item} /> : null}

        <ResponsiveTableCard ariaLabel="Scene differences" maxHeight={360} minWidth={560}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Scene</TableCell>
                <TableCell align="right">Attention</TableCell>
                <TableCell align="right">Engagement</TableCell>
                <TableCell>Note</TableCell>
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
        </ResponsiveTableCard>

        <Box
          component="pre"
          sx={{
            background: 'rgba(15, 23, 42, 0.05)',
            borderRadius: 2,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            fontSize: 12,
            maxHeight: 260,
            overflow: 'auto',
            p: 1.5,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {JSON.stringify(item.delta_json, null, 2)}
        </Box>
      </Stack>
    </Paper>
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
      <Box className="compare-details-drawer">
        <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={2}>
          <Typography variant="h6">Technical details</Typography>
          <IconButton aria-label="Close technical details" onClick={onClose}>
            <CloseRounded />
          </IconButton>
        </Stack>
        <Stack spacing={2}>{children}</Stack>
      </Box>
    </Drawer>
  )
}

function buildInsights(
  comparison: AnalysisComparison,
  winner: AnalysisComparisonItem | null,
  baseline: AnalysisComparisonItem | null,
  metricLeaders: MetricLeader[],
): string[] {
  const insights = [
    String(comparison.summary_json.winning_rationale || winner?.rationale || '').trim(),
  ].filter(Boolean)

  metricLeaders.slice(0, 3).forEach((leader) => {
    insights.push(
      `${findComparisonItemLabel(comparison.items, leader.analysis_job_id)} leads ${readableMetric(
        leader.metric,
      )} at ${formatNumber(leader.value)}.`,
    )
  })

  if (winner && baseline && winner.analysis_job_id !== baseline.analysis_job_id) {
    insights.push(
      `${resolveComparisonItemLabel(winner)} is ${formatSignedNumber(
        winner.delta_json.composite,
      )} composite points vs baseline.`,
    )
  }

  return insights.length > 0 ? insights.slice(0, 5) : ['Winner selected from persisted comparison scores.']
}

function buildRecommendations(items: AnalysisComparisonItem[]): string[] {
  const recommendations = items.flatMap((item) =>
    item.recommendation_overlap_json.candidate_only_titles
      .slice(0, 2)
      .map((title) => `Borrow "${title}" from ${resolveComparisonItemLabel(item)}.`),
  )

  if (recommendations.length > 0) {
    return recommendations.slice(0, 5)
  }

  return [
    'Use winner as primary direction.',
    'Retain baseline elements only where score deltas stay neutral or positive.',
    'Re-run comparison after hook or structure edits.',
  ]
}

const ComparisonSummary = memo(ComparisonSummaryBase)
const SideBySideTable = memo(SideBySideTableBase)
const InsightsPanel = memo(InsightsPanelBase)
const RecommendationsPanel = memo(RecommendationsPanelBase)
const TechnicalChallengerSection = memo(TechnicalChallengerSectionBase)
const TechnicalDetailsDrawer = memo(TechnicalDetailsDrawerBase)
const ComparisonResults = memo(ComparisonResultsBase)
export default ComparisonResults
