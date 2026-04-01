import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ComparePage, { __resetComparePageRequestCacheForTests } from './ComparePage'

vi.mock('../lib/api', () => ({
  apiRequest: vi.fn(),
}))

import { apiRequest } from '../lib/api'

const mockedApiRequest = vi.mocked(apiRequest)

const session = {
  email: 'analyst@example.com',
  fullName: 'Analysis Tester',
  defaultProjectId: 'project-1',
  defaultProjectName: 'Primary project',
  organizationName: 'Acme',
  sessionToken: 'session-token',
}

function mockWorkspaceMembers() {
  return {
    items: [
      {
        id: 'user-1',
        email: session.email,
        full_name: session.fullName,
        role: 'owner',
      },
    ],
  }
}

function maybeHandleCollaborationRequest(path: string) {
  if (path === '/api/v1/analysis/collaboration/members') {
    return mockWorkspaceMembers()
  }
  const reviewMatch = path.match(/^\/api\/v1\/analysis\/collaboration\/(analysis_job|analysis_comparison)\/([^/]+)$/)
  if (!reviewMatch) {
    return undefined
  }
  return {
    id: null,
    entity_type: reviewMatch[1],
    entity_id: reviewMatch[2],
    status: 'draft',
    review_summary: null,
    created_by: null,
    assignee: null,
    approved_by: null,
    approved_at: null,
    created_at: null,
    updated_at: null,
    comments: [],
  }
}

function buildAnalysisHistoryItem({
  jobId,
  assetId,
  filename,
  objective,
  goalTemplate = 'paid_social_hook',
  channel = 'meta_feed',
  audienceSegment = 'Returning customers',
}: {
  jobId: string
  assetId: string
  filename: string
  objective: string
  goalTemplate?: string
  channel?: string
  audienceSegment?: string
}) {
  return {
    job: {
      id: jobId,
      asset_id: assetId,
      status: 'completed',
      objective,
      goal_template: goalTemplate,
      channel,
      audience_segment: audienceSegment,
      created_at: '2026-03-31T10:00:00.000Z',
    },
    asset: {
      id: assetId,
      media_type: 'video',
      original_filename: filename,
      object_key: `analysis/${filename}`,
      upload_status: 'uploaded',
      created_at: '2026-03-31T09:55:00.000Z',
    },
    has_result: true,
  }
}

function buildResult(jobId: string, attention: number, recommendationTitle: string) {
  return {
    job_id: jobId,
    summary_json: {
      overall_attention_score: attention,
      hook_score_first_3_seconds: attention - 5,
      sustained_engagement_score: attention - 8,
      memory_proxy_score: attention - 12,
      cognitive_load_proxy: 30,
      confidence: 83,
    },
    metrics_json: [
      { key: 'conversion_proxy_score', label: 'Conversion proxy', value: attention - 6, unit: '/100' },
    ],
    segments_json: [
      {
        segment_index: 0,
        label: 'Scene 01',
        start_time_ms: 0,
        end_time_ms: 1500,
        attention_score: attention,
        engagement_delta: 4,
        note: `${recommendationTitle} segment note`,
      },
    ],
    recommendations_json: [
      {
        title: recommendationTitle,
        detail: `${recommendationTitle} detail`,
        priority: 'high',
      },
    ],
  }
}

function buildComparisonResponse({
  comparisonId,
  name,
  baselineItem,
  challengerItem,
  winningJobId,
}: {
  comparisonId: string
  name: string
  baselineItem: ReturnType<typeof buildAnalysisHistoryItem>
  challengerItem: ReturnType<typeof buildAnalysisHistoryItem>
  winningJobId: string
}) {
  const baselineResult = buildResult(baselineItem.job.id, 71, 'Baseline recommendation')
  const challengerResult = buildResult(challengerItem.job.id, 86, 'Winner recommendation')

  return {
    id: comparisonId,
    name,
    created_at: '2026-03-31T10:30:00.000Z',
    winning_analysis_job_id: winningJobId,
    baseline_job_id: baselineItem.job.id,
    summary_json: {
      winning_rationale: `${challengerItem.asset.original_filename} leads on conversion proxy and overall attention.`,
      metric_leaders: [
        { metric: 'composite', analysis_job_id: challengerItem.job.id, value: 84.2 },
        { metric: 'overall_attention', analysis_job_id: challengerItem.job.id, value: 86 },
      ],
    },
    comparison_context: {},
    items: [
      {
        analysis_job_id: challengerItem.job.id,
        job: challengerItem.job,
        asset: challengerItem.asset,
        result: challengerResult,
        overall_rank: 1,
        is_winner: true,
        is_baseline: false,
        scores_json: {
          composite: 84.2,
          overall_attention: 86,
          hook: 81,
          sustained_engagement: 78,
          memory_proxy: 74,
          low_cognitive_load: 70,
        },
        delta_json: {
          composite: 8.1,
          overall_attention: 15,
          hook: 15,
        },
        rationale: `${challengerItem.asset.original_filename} leads on conversion proxy and hook strength.`,
        scene_deltas_json: [
          {
            segment_index: 0,
            label: 'Scene 01',
            candidate_window: '0-1500',
            baseline_attention: 71,
            candidate_attention: 86,
            attention_delta: 15,
            engagement_delta_delta: 2,
            candidate_note: 'Winner recommendation segment note',
          },
        ],
        recommendation_overlap_json: {
          shared_titles: [],
          candidate_only_titles: ['Winner recommendation'],
          baseline_only_titles: ['Baseline recommendation'],
        },
      },
      {
        analysis_job_id: baselineItem.job.id,
        job: baselineItem.job,
        asset: baselineItem.asset,
        result: baselineResult,
        overall_rank: 2,
        is_winner: false,
        is_baseline: true,
        scores_json: {
          composite: 76.1,
          overall_attention: 71,
          hook: 66,
          sustained_engagement: 63,
          memory_proxy: 59,
          low_cognitive_load: 70,
        },
        delta_json: {
          composite: 0,
          overall_attention: 0,
          hook: 0,
        },
        rationale: `${baselineItem.asset.original_filename} is the baseline item.`,
        scene_deltas_json: [],
        recommendation_overlap_json: {
          shared_titles: [],
          candidate_only_titles: ['Baseline recommendation'],
          baseline_only_titles: [],
        },
      },
    ],
  }
}

describe('ComparePage', () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
    __resetComparePageRequestCacheForTests()
    window.sessionStorage.clear()
  })

  it('creates and reopens persisted analysis comparisons', async () => {
    const alphaItem = buildAnalysisHistoryItem({
      jobId: 'job-alpha',
      assetId: 'asset-alpha',
      filename: 'alpha.mp4',
      objective: 'Assess the current hook',
    })
    const betaItem = buildAnalysisHistoryItem({
      jobId: 'job-beta',
      assetId: 'asset-beta',
      filename: 'beta.mp4',
      objective: 'Assess the alternate hook',
    })
    const gammaItem = buildAnalysisHistoryItem({
      jobId: 'job-gamma',
      assetId: 'asset-gamma',
      filename: 'gamma.mp4',
      objective: 'Assess the retention cut',
    })

    const createdComparison = buildComparisonResponse({
      comparisonId: 'comparison-new',
      name: 'Spring hook compare',
      baselineItem: alphaItem,
      challengerItem: betaItem,
      winningJobId: betaItem.job.id,
    })
    const savedComparison = buildComparisonResponse({
      comparisonId: 'comparison-saved',
      name: 'Retention compare',
      baselineItem: alphaItem,
      challengerItem: gammaItem,
      winningJobId: gammaItem.job.id,
    })

    mockedApiRequest.mockImplementation(async (path, options) => {
      const collaborationResponse = maybeHandleCollaborationRequest(path)
      if (collaborationResponse !== undefined) {
        return collaborationResponse
      }
      if (path === '/api/v1/analysis/jobs?limit=24') {
        return { items: [alphaItem, betaItem, gammaItem] }
      }
      if (path === '/api/v1/analysis/comparisons?limit=12') {
        return {
          items: [
            {
              id: 'comparison-saved',
              name: 'Retention compare',
              created_at: '2026-03-31T10:20:00.000Z',
              winning_analysis_job_id: gammaItem.job.id,
              baseline_job_id: alphaItem.job.id,
              candidate_count: 2,
              summary_json: {},
              item_labels: ['alpha.mp4', 'gamma.mp4'],
            },
          ],
        }
      }
      if (path === '/api/v1/analysis/comparisons' && options?.method === 'POST') {
        return createdComparison
      }
      if (path === '/api/v1/analysis/comparisons/comparison-saved') {
        return savedComparison
      }
      throw new Error(`Unexpected path ${path}`)
    })

    render(<ComparePage session={session} />)

    await waitFor(() => {
      expect(screen.getByText('Build a comparison')).toBeTruthy()
      expect(screen.getByText('alpha.mp4')).toBeTruthy()
      expect(screen.getByText('Saved comparisons')).toBeTruthy()
    })

    fireEvent.click(screen.getAllByText('Add to compare')[0])
    fireEvent.click(screen.getAllByText('Add to compare')[1])

    fireEvent.change(screen.getByLabelText('Comparison name'), {
      target: { value: 'Spring hook compare' },
    })

    fireEvent.click(screen.getByTestId('create-analysis-comparison'))

    await waitFor(() => {
      expect(screen.getByText('Winner call')).toBeTruthy()
      expect(screen.getAllByText('beta.mp4').length).toBeGreaterThan(0)
      expect(screen.getByText(/leads on conversion proxy and overall attention/i)).toBeTruthy()
      expect(screen.getByText('Recommendation overlap')).toBeTruthy()
      expect(screen.getByText('Comparison review ops')).toBeTruthy()
    })

    const savedComparisonCard = screen.getByText('Retention compare').closest('.analysis-job-history__item')
    expect(savedComparisonCard).toBeTruthy()
    fireEvent.click(within(savedComparisonCard as HTMLElement).getByText('Open comparison'))

    await waitFor(() => {
      expect(screen.getByText('Retention compare')).toBeTruthy()
      expect(screen.getAllByText('gamma.mp4').length).toBeGreaterThan(0)
    })
  })

  it('dedupes mount-time compare requests across immediate remounts', async () => {
    const alphaItem = buildAnalysisHistoryItem({
      jobId: 'job-alpha',
      assetId: 'asset-alpha',
      filename: 'alpha.mp4',
      objective: 'Assess the current hook',
    })
    const betaItem = buildAnalysisHistoryItem({
      jobId: 'job-beta',
      assetId: 'asset-beta',
      filename: 'beta.mp4',
      objective: 'Assess the alternate hook',
    })

    mockedApiRequest.mockImplementation(async (path) => {
      const collaborationResponse = maybeHandleCollaborationRequest(path)
      if (collaborationResponse !== undefined) {
        return collaborationResponse
      }
      if (path === '/api/v1/analysis/jobs?limit=24') {
        return { items: [alphaItem, betaItem] }
      }
      if (path === '/api/v1/analysis/comparisons?limit=12') {
        return { items: [] }
      }
      throw new Error(`Unexpected path ${path}`)
    })

    const firstRender = render(<ComparePage session={session} />)

    await waitFor(() => {
      expect(screen.getByText('Build a comparison')).toBeTruthy()
      expect(screen.getByText('Saved comparisons')).toBeTruthy()
    })

    firstRender.unmount()

    render(<ComparePage session={session} />)

    await waitFor(() => {
      expect(screen.getByText('Build a comparison')).toBeTruthy()
      expect(screen.getByText('Saved comparisons')).toBeTruthy()
    })

    expect(mockedApiRequest.mock.calls.filter(([path]) => path === '/api/v1/analysis/jobs?limit=24')).toHaveLength(1)
    expect(mockedApiRequest.mock.calls.filter(([path]) => path === '/api/v1/analysis/comparisons?limit=12')).toHaveLength(1)
  })
})
