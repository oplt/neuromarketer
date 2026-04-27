import InsightsRounded from '@mui/icons-material/InsightsRounded'
import {
  Box,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { memo, useMemo } from 'react'
import AdvancedDetails from '../../../components/layout/AdvancedDetails'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import ResponsiveTableCard from '../../../components/common/ResponsiveTableCard'
import MetricsRadarCard from '../../../components/analysis/MetricsRadarCard'
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

function ComparisonResultsBase({ comparison }: ComparisonResultsProps) {
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
        ? (comparison.summary_json.metric_leaders as Array<{
            metric: string
            analysis_job_id: string
            value: number
          }>)
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

  if (!winner || !baseline) {
    return null
  }

  return (
    <Stack spacing={3}>
      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Stack
            alignItems={{ xs: 'stretch', md: 'center' }}
            direction={{ xs: 'column', md: 'row' }}
            justifyContent="space-between"
            spacing={1.5}
          >
            <Stack alignItems="center" direction="row" spacing={0.5}>
              <Typography variant="h6">Winner call</Typography>
              <HelpTooltip title="Ranking uses the persisted weighted comparison summary, not an ad hoc frontend sort." />
            </Stack>
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
              <Stack alignItems="center" direction="row" spacing={0.5}>
                <Typography variant="subtitle2">Baseline</Typography>
                <HelpTooltip title="Deltas elsewhere are measured against this baseline." />
              </Stack>
              <Typography color="text.secondary" variant="body2">
                {resolveComparisonItemLabel(baseline)}
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
          <ResponsiveTableCard ariaLabel="Comparison ranking table" maxHeight={420} minWidth={760}>
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
                    <TableCell align="right">
                      {item.is_baseline ? 'Baseline' : formatSignedNumber(item.delta_json.composite)}
                    </TableCell>
                    <TableCell align="right">{formatNumber(item.scores_json.overall_attention)}</TableCell>
                    <TableCell align="right">{formatNumber(item.scores_json.hook)}</TableCell>
                    <TableCell align="right">{formatNumber(item.scores_json.memory_proxy)}</TableCell>
                    <TableCell align="right">{formatNumber(item.scores_json.low_cognitive_load)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ResponsiveTableCard>
        </Stack>
      </Paper>

      <ScoreGaugesComparison items={comparison.items} />

      <MetricsRadarCard
        description="Compare each result's persisted metric rows in one radial view."
        emptyMessage="Radar comparison appears when at least three comparable metrics are available across the selected results."
        series={radarSeries}
        testId="compare-metrics-radar"
        title="Metrics radar comparison"
      />

      {challengers.map((item) => (
        <ChallengerSection baseline={baseline} item={item} key={item.analysis_job_id} />
      ))}
    </Stack>
  )
}

type ChallengerSectionProps = {
  baseline: AnalysisComparisonItem | null
  item: AnalysisComparisonItem
}

function ChallengerSectionBase({ baseline, item }: ChallengerSectionProps) {
  const showHeatstrip =
    (baseline?.result.segments_json.length ?? 0) > 0 || item.result.segments_json.length > 0

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
            <Typography variant="h6">{resolveComparisonItemLabel(item)} vs baseline</Typography>
            <HelpTooltip title="See where this challenger diverges from the baseline across scenes and recommendations." />
          </Stack>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip label={`Composite ${formatSignedNumber(item.delta_json.composite)}`} size="small" variant="outlined" />
            <Chip label={`Attention ${formatSignedNumber(item.delta_json.overall_attention)}`} size="small" variant="outlined" />
            <Chip label={`Hook ${formatSignedNumber(item.delta_json.hook)}`} size="small" variant="outlined" />
          </Stack>
        </Stack>

        {showHeatstrip ? <CompareHeatstripCard baseline={baseline} challenger={item} /> : null}

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
                <ResponsiveTableCard ariaLabel="Scene-by-scene differences" maxHeight={360} minWidth={560}>
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
                </ResponsiveTableCard>
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

        <AdvancedDetails
          description="Raw scoring deltas, persisted scene metadata, and rationale strings."
          title="Raw delta payload"
        >
          <Box
            component="pre"
            sx={{
              fontSize: 12,
              maxHeight: 280,
              overflow: 'auto',
              p: 1.5,
              borderRadius: 2,
              background: 'rgba(15, 23, 42, 0.05)',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {JSON.stringify(item.delta_json, null, 2)}
          </Box>
        </AdvancedDetails>
      </Stack>
    </Paper>
  )
}

const ChallengerSection = memo(ChallengerSectionBase)

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

const ComparisonResults = memo(ComparisonResultsBase)
export default ComparisonResults
