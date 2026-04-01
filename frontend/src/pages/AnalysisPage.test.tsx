import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AnalysisPage from './AnalysisPage'

vi.mock('../components/analysis/AnalysisEvaluationSection', () => ({
  default: () => null,
}))

vi.mock('../lib/api', () => ({
  apiRequest: vi.fn(),
  subscribeToEventStream: vi.fn(() => vi.fn()),
  uploadToApi: vi.fn(),
  uploadToSignedUrl: vi.fn(),
}))

import { apiRequest, subscribeToEventStream } from '../lib/api'

const mockedApiRequest = vi.mocked(apiRequest)
const mockedSubscribeToEventStream = vi.mocked(subscribeToEventStream)

const session = {
  email: 'analyst@example.com',
  fullName: 'Analysis Tester',
  defaultProjectId: 'project-1',
  defaultProjectName: 'Primary project',
  organizationName: 'Acme',
  sessionToken: 'session-token',
}

function buildHistoryItem({
  jobId,
  assetId,
  filename,
  mediaType = 'video',
  objective,
  goalTemplate = null,
  channel = null,
  audienceSegment = null,
}: {
  jobId: string
  assetId: string
  filename: string
  mediaType?: 'video' | 'audio' | 'text'
  objective: string
  goalTemplate?: string | null
  channel?: string | null
  audienceSegment?: string | null
}) {
  const mimeType =
    mediaType === 'audio' ? 'audio/mpeg' : mediaType === 'text' ? 'text/plain' : 'video/mp4'

  return {
    job: {
      id: jobId,
      asset_id: assetId,
      status: 'completed',
      objective,
      goal_template: goalTemplate,
      channel,
      audience_segment: audienceSegment,
      started_at: '2026-03-31T09:58:00.000Z',
      finished_at: '2026-03-31T10:00:00.000Z',
      error_message: null,
      created_at: '2026-03-31T09:55:00.000Z',
    },
    asset: {
      id: assetId,
      media_type: mediaType,
      original_filename: filename,
      mime_type: mimeType,
      size_bytes: 4096,
      bucket: 'analysis',
      object_key: `analysis/${filename}`,
      object_uri: `s3://analysis/${filename}`,
      upload_status: 'uploaded',
      created_at: '2026-03-31T09:54:00.000Z',
    },
    has_result: true,
    result_created_at: '2026-03-31T10:00:00.000Z',
  }
}

function buildResult(jobId: string, attentionScore: number, recommendationTitle: string, mediaType = 'video') {
  return {
    job_id: jobId,
    summary_json: {
      modality: mediaType,
      overall_attention_score: attentionScore,
      hook_score_first_3_seconds: 70,
      sustained_engagement_score: 68,
      memory_proxy_score: 64,
      cognitive_load_proxy: 32,
      confidence: 82,
      completeness: 79,
      notes: [],
      metadata: {
        objective: 'Evaluate opening strength',
        goal_template: 'paid_social_hook',
        channel: 'meta_feed',
        audience_segment: 'Returning customers',
        source_label: 'Upload',
        segment_count: 3,
        duration_ms: 15000,
      },
    },
    metrics_json: [
      {
        key: 'overall_attention_score',
        label: 'Overall Attention',
        value: attentionScore,
        unit: '/100',
        source: 'postprocessor',
        detail: 'Derived from timeline behavior.',
        confidence: 82,
      },
    ],
    timeline_json: [
      { timestamp_ms: 0, engagement_score: 62, attention_score: attentionScore, memory_proxy: 58 },
      { timestamp_ms: 1500, engagement_score: 66, attention_score: attentionScore - 4, memory_proxy: 60 },
    ],
    segments_json: [
      {
        segment_index: 0,
        label: 'Scene 01',
        start_time_ms: 0,
        end_time_ms: 1500,
        attention_score: attentionScore,
        engagement_delta: 4,
        note: `${recommendationTitle} segment note`,
      },
    ],
    visualizations_json: {
      visualization_mode: 'frame_grid_fallback',
      heatmap_frames: [
        {
          timestamp_ms: 0,
          label: 'Frame 1',
          scene_label: 'Scene 01',
          grid_rows: 2,
          grid_columns: 2,
          intensity_map: [
            [10, 20],
            [30, 40],
          ],
          strongest_zone: 'middle_center',
          caption: 'Frame summary',
        },
      ],
      high_attention_intervals: [],
      low_attention_intervals: [],
    },
    recommendations_json: [
      {
        title: recommendationTitle,
        detail: `${recommendationTitle} detail`,
        priority: 'high',
        timestamp_ms: 1000,
        confidence: 88,
      },
    ],
    created_at: '2026-03-31T10:00:00.000Z',
  }
}

function buildJobStatus(item: ReturnType<typeof buildHistoryItem>, result: ReturnType<typeof buildResult>) {
  return {
    job: item.job,
    asset: item.asset,
    result,
  }
}

function mockBenchmarkResponse(jobId: string) {
  return {
    job_id: jobId,
    cohort_label: 'Video cohort for paid social hook / meta feed',
    cohort_size: 8,
    fallback_level: 'exact_match',
    metrics: [
      {
        key: 'overall_attention_score',
        label: 'Overall Attention',
        value: 82,
        percentile: 74,
        cohort_median: 63,
        cohort_p75: 77,
        orientation: 'higher',
        detail: 'Overall Attention benchmarked against the current cohort.',
      },
    ],
    generated_at: '2026-03-31T10:00:00.000Z',
  }
}

function mockVerdictResponse(jobId: string) {
  return {
    job_id: jobId,
    status: 'ship',
    headline: 'Ship with confidence',
    summary: 'Average benchmark percentile is 72.0 across comparable completed analyses.',
    benchmark_average_percentile: 72,
    top_strengths: ['Overall Attention ranks in the 74th percentile for this cohort.'],
    top_risks: ['Cognitive Load is lagging at the 38th percentile.'],
    recommended_actions: ['Clarify the CTA in the final scene.'],
    generated_at: '2026-03-31T10:00:00.000Z',
  }
}

function mockCalibrationResponse(jobId: string) {
  return {
    job_id: jobId,
    summary: {
      observation_count: 0,
      metric_types: [],
      latest_observed_at: null,
      average_predicted_value: null,
      average_actual_value: null,
    },
    observations: [],
  }
}

function mockGeneratedVariantsResponse(jobId: string) {
  return {
    job_id: jobId,
    items: [
      {
        id: `variant-${jobId}-hook`,
        job_id: jobId,
        parent_creative_version_id: `creative-version-${jobId}`,
        variant_type: 'hook_rewrite',
        title: 'Hook rewrite',
        summary: 'A faster opening variant designed to improve first-impression hold strength.',
        focus_recommendations: ['Front-load the strongest cue', 'Clarify the decision moment'],
        source_suggestion_title: 'Front-load the strongest cue',
        source_suggestion_type: 'pacing',
        sections: [
          {
            key: 'primary_hook',
            label: 'Primary hook',
            value: 'Lead with the clearest payoff before context builds.',
          },
        ],
        expected_score_lift_json: {
          overall_attention_score: 6,
          hook_score_first_3_seconds: 10,
          sustained_engagement_score: 4,
          memory_proxy_score: 2,
          cognitive_load_proxy: -2,
        },
        projected_summary_json: {
          modality: 'video',
          overall_attention_score: 88,
          hook_score_first_3_seconds: 82,
          sustained_engagement_score: 72,
          memory_proxy_score: 66,
          cognitive_load_proxy: 30,
          confidence: 82,
          completeness: 79,
          notes: [],
          metadata: {
            projection_kind: 'generated_variant',
            variant_type: 'hook_rewrite',
          },
        },
        compare_metrics: [
          {
            key: 'overall_attention_score',
            label: 'Overall attention',
            original_value: 82,
            variant_value: 88,
            delta: 6,
            unit: '/100',
          },
        ],
        compare_summary: 'Compared with the original, this variant is projected to lift overall attention by 6.0.',
        created_at: '2026-03-31T10:01:00.000Z',
        updated_at: '2026-03-31T10:01:00.000Z',
      },
    ],
  }
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

function mockConfig() {
  return {
    max_file_size_bytes: 50_000_000,
    max_text_characters: 10_000,
    allowed_media_types: ['video', 'audio', 'text'],
    allowed_mime_types: {
      video: ['video/mp4'],
      audio: ['audio/mpeg'],
      text: ['text/plain'],
    },
  }
}

function mockGoalPresets() {
  return {
    goal_templates: [
      {
        value: 'paid_social_hook',
        label: 'Paid social hook',
        description: 'Front-loaded hold strength, pacing, and CTA readiness.',
        supported_media_types: ['video', 'audio'],
        default_channel: 'meta_feed',
        group_id: 'paid_social',
      },
      {
        value: 'ugc_native_social',
        label: 'UGC / native social',
        description: 'Authenticity, creator pacing, and native platform fit.',
        supported_media_types: ['video'],
        default_channel: 'tiktok',
        group_id: 'paid_social',
      },
      {
        value: 'landing_page_clarity',
        label: 'Landing page hero',
        description: 'Message clarity, cognitive load, and conversion friction above the fold.',
        supported_media_types: ['video', 'text'],
        default_channel: 'landing_page',
        group_id: 'web_conversion',
      },
      {
        value: 'email_clickthrough',
        label: 'Email clickthrough',
        description: 'Subject-to-body continuity, scanning flow, and CTA intent.',
        supported_media_types: ['text'],
        default_channel: 'email',
        group_id: 'web_conversion',
      },
      {
        value: 'education_explainer',
        label: 'Education / explainer',
        description: 'Comprehension, retention, and overload risk.',
        supported_media_types: ['video', 'audio', 'text'],
        default_channel: 'youtube_pre_roll',
        group_id: 'education',
      },
      {
        value: 'brand_story_film',
        label: 'Brand film',
        description: 'Memory lift, emotional continuity, and brand anchoring.',
        supported_media_types: ['video', 'audio'],
        default_channel: 'youtube_pre_roll',
        group_id: 'storytelling',
      },
    ],
    channels: [
      { value: 'meta_feed', label: 'Meta feed', supported_media_types: ['video', 'audio'] },
      { value: 'instagram_reels', label: 'Instagram Reels', supported_media_types: ['video'] },
      { value: 'tiktok', label: 'TikTok', supported_media_types: ['video'] },
      { value: 'youtube_pre_roll', label: 'YouTube pre-roll', supported_media_types: ['video', 'audio'] },
      { value: 'landing_page', label: 'Landing page', supported_media_types: ['video', 'text'] },
      { value: 'email', label: 'Email', supported_media_types: ['text'] },
    ],
    preset_groups: [
      {
        id: 'paid_social',
        label: 'Paid social',
        description: 'Fast hook and native-feed review modes for short-form launches.',
        template_values: ['paid_social_hook', 'ugc_native_social'],
      },
      {
        id: 'web_conversion',
        label: 'Web conversion',
        description: 'Message clarity and clickthrough workflows for owned surfaces.',
        template_values: ['landing_page_clarity', 'email_clickthrough'],
      },
      {
        id: 'education',
        label: 'Education',
        description: 'Teaching-oriented review modes for demos, onboarding, and explainers.',
        template_values: ['education_explainer'],
      },
      {
        id: 'storytelling',
        label: 'Storytelling',
        description: 'Brand-memory and emotional continuity review for longer campaign cuts.',
        template_values: ['brand_story_film'],
      },
    ],
    suggestions: [
      {
        media_type: 'video',
        goal_template: 'paid_social_hook',
        channel: 'meta_feed',
        audience_placeholder: 'Cold prospecting, retargeting, creator-led lookalikes',
        rationale: 'Video uploads usually benefit from a short-form hook review first.',
      },
      {
        media_type: 'audio',
        goal_template: 'education_explainer',
        channel: 'youtube_pre_roll',
        audience_placeholder: 'Podcast listeners, webinar registrants, warm audio audiences',
        rationale: 'Audio assets usually need pacing and comprehension checks before channel-specific polish.',
      },
      {
        media_type: 'text',
        goal_template: 'landing_page_clarity',
        channel: 'landing_page',
        audience_placeholder: 'New visitors, ICP accounts, lifecycle email segments',
        rationale: 'Text uploads usually start with clarity and conversion-friction review.',
      },
    ],
  }
}

describe('AnalysisPage', () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
    mockedSubscribeToEventStream.mockReset()
    mockedSubscribeToEventStream.mockImplementation(() => vi.fn())
    window.sessionStorage.clear()
  })

  it('loads saved runs from the drawer and exposes primary compare and generate actions', async () => {
    const alphaItem = buildHistoryItem({
      jobId: 'job-alpha',
      assetId: 'asset-alpha',
      filename: 'alpha.mp4',
      objective: 'Assess the launch hook',
      goalTemplate: 'paid_social_hook',
      channel: 'meta_feed',
      audienceSegment: 'Returning customers',
    })
    const betaItem = buildHistoryItem({
      jobId: 'job-beta',
      assetId: 'asset-beta',
      filename: 'beta.mp4',
      objective: 'Assess the retention curve',
    })
    const alphaResult = buildResult('job-alpha', 41, 'Alpha recommendation')
    const betaResult = buildResult('job-beta', 88, 'Beta recommendation')
    let hasGeneratedVariants = false

    mockedApiRequest.mockImplementation(async (path, options) => {
      const collaborationResponse = maybeHandleCollaborationRequest(path)
      if (collaborationResponse !== undefined) {
        return collaborationResponse
      }
      if (path === '/api/v1/analysis/config') {
        return mockConfig()
      }
      if (path === '/api/v1/analysis/goal-presets') {
        return mockGoalPresets()
      }
      if (path === '/api/v1/analysis/events') {
        return { status: 'accepted' }
      }
      if (path === '/api/v1/analysis/assets?media_type=video&limit=12') {
        return { items: [] }
      }
      if (path === '/api/v1/analysis/jobs?media_type=video&limit=12') {
        return { items: [alphaItem, betaItem] }
      }
      if (path === '/api/v1/analysis/jobs/job-alpha') {
        return buildJobStatus(alphaItem, alphaResult)
      }
      if (path === '/api/v1/analysis/jobs/job-beta') {
        return buildJobStatus(betaItem, betaResult)
      }
      if (path === '/api/v1/analysis/jobs/job-alpha/benchmarks' || path === '/api/v1/analysis/jobs/job-beta/benchmarks') {
        return mockBenchmarkResponse(path.includes('job-alpha') ? 'job-alpha' : 'job-beta')
      }
      if (path === '/api/v1/analysis/jobs/job-alpha/verdict' || path === '/api/v1/analysis/jobs/job-beta/verdict') {
        return mockVerdictResponse(path.includes('job-alpha') ? 'job-alpha' : 'job-beta')
      }
      if (path === '/api/v1/analysis/jobs/job-alpha/calibration' || path === '/api/v1/analysis/jobs/job-beta/calibration') {
        return mockCalibrationResponse(path.includes('job-alpha') ? 'job-alpha' : 'job-beta')
      }
      if (path === '/api/v1/analysis/jobs/job-alpha/variants' && options?.method === 'POST') {
        hasGeneratedVariants = true
        return mockGeneratedVariantsResponse('job-alpha')
      }
      if (path === '/api/v1/analysis/jobs/job-alpha/variants' || path === '/api/v1/analysis/jobs/job-beta/variants') {
        if (path.includes('job-alpha') && hasGeneratedVariants) {
          return mockGeneratedVariantsResponse('job-alpha')
        }
        return { job_id: path.includes('job-alpha') ? 'job-alpha' : 'job-beta', items: [] }
      }
      throw new Error(`Unexpected path ${path}`)
    })

    render(<AnalysisPage session={session} />)

    await waitFor(() => {
      expect(screen.getByTestId('open-analysis-history')).toBeTruthy()
    })
    expect(screen.queryByText('Alpha recommendation')).toBeNull()

    fireEvent.click(screen.getByTestId('open-analysis-history'))

    await waitFor(() => {
      expect(screen.getByTestId('analysis-history-list')).toBeTruthy()
    })

    fireEvent.click(screen.getByTestId('analysis-history-item-job-alpha'))

    await waitFor(() => {
      expect(screen.getByText('Alpha recommendation')).toBeTruthy()
    })
    expect(screen.getByText('Review ops')).toBeTruthy()

    expect((screen.getByTestId('analysis-action-compare') as HTMLButtonElement).disabled).toBe(false)
    expect((screen.getByTestId('analysis-action-export') as HTMLButtonElement).disabled).toBe(false)
    expect((screen.getByTestId('analysis-action-generate') as HTMLButtonElement).disabled).toBe(false)

    fireEvent.click(screen.getByTestId('analysis-action-generate'))

    await waitFor(() => {
      expect(screen.getByText('Generated variants')).toBeTruthy()
      expect(screen.getAllByText('Hook rewrite').length).toBeGreaterThan(0)
      expect(screen.getByText(/Compare generated variant vs original/i)).toBeTruthy()
    })

    fireEvent.click(screen.getByTestId('analysis-action-compare'))

    await waitFor(() => {
      expect(screen.getByText('Choose a comparison target')).toBeTruthy()
    })

    fireEvent.click(screen.getByTestId('analysis-history-item-job-beta'))

    await waitFor(() => {
      expect(screen.getByText('Quick comparison')).toBeTruthy()
      expect(screen.getByText(/beta.mp4 currently leads the quick compare snapshot/i)).toBeTruthy()
    })
  })

  it('restores the goal step from the stored asset snapshot without auto-loading history', async () => {
    const storedAsset = buildHistoryItem({
      jobId: 'job-previous',
      assetId: 'asset-goal',
      filename: 'goal.mp4',
      objective: 'Assess the launch hook',
    }).asset
    const previousRun = buildHistoryItem({
      jobId: 'job-previous',
      assetId: 'asset-previous',
      filename: 'previous.mp4',
      objective: 'Previous result',
    })

    window.sessionStorage.setItem(
      'neuromarketer.analysis.wizard.project-1',
      JSON.stringify({
        mediaType: 'video',
        objective: 'Assess whether the opener is strong enough for paid retargeting.',
        goalTemplate: 'paid_social_hook',
        channel: 'meta_feed',
        audienceSegment: 'Returning customers',
        selectionMode: 'asset',
      }),
    )
    window.sessionStorage.setItem('neuromarketer.analysis.selected-asset.project-1', 'asset-goal')

    mockedApiRequest.mockImplementation(async (path) => {
      const collaborationResponse = maybeHandleCollaborationRequest(path)
      if (collaborationResponse !== undefined) {
        return collaborationResponse
      }
      if (path === '/api/v1/analysis/config') {
        return mockConfig()
      }
      if (path === '/api/v1/analysis/goal-presets') {
        return mockGoalPresets()
      }
      if (path === '/api/v1/analysis/events') {
        return { status: 'accepted' }
      }
      if (path === '/api/v1/analysis/assets?media_type=video&limit=12') {
        return { items: [storedAsset] }
      }
      if (path === '/api/v1/analysis/jobs?media_type=video&limit=12') {
        return { items: [previousRun] }
      }
      if (path === '/api/v1/analysis/jobs/job-previous') {
        throw new Error('History should not auto-load when restoring the asset step.')
      }
      throw new Error(`Unexpected path ${path}`)
    })

    render(<AnalysisPage session={session} />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('Assess whether the opener is strong enough for paid retargeting.')).toBeTruthy()
      expect(screen.getByDisplayValue('Returning customers')).toBeTruthy()
      expect(screen.getAllByText('goal.mp4').length).toBeGreaterThan(0)
    })

    expect(screen.queryByText('Alpha recommendation')).toBeNull()
    expect(
      mockedApiRequest.mock.calls.some(([path]) => path === '/api/v1/analysis/jobs/job-previous'),
    ).toBe(false)
    expect((screen.getByText('Start analysis') as HTMLButtonElement).disabled).toBe(false)
  })

  it('restores the selected job and media type from the stored wizard snapshot', async () => {
    const audioItem = buildHistoryItem({
      jobId: 'job-audio',
      assetId: 'asset-audio',
      filename: 'voiceover.mp3',
      mediaType: 'audio',
      objective: 'Assess narration pacing',
      goalTemplate: 'education_explainer',
      channel: 'youtube_pre_roll',
      audienceSegment: 'First-time visitors',
    })
    const audioResult = buildResult('job-audio', 73, 'Audio recommendation', 'audio')

    window.sessionStorage.setItem(
      'neuromarketer.analysis.wizard.project-1',
      JSON.stringify({
        mediaType: 'audio',
        objective: 'Assess narration pacing',
        goalTemplate: 'education_explainer',
        channel: 'youtube_pre_roll',
        audienceSegment: 'First-time visitors',
        selectionMode: 'job',
      }),
    )
    window.sessionStorage.setItem('neuromarketer.analysis.selected-job.project-1', 'job-audio')

    mockedApiRequest.mockImplementation(async (path) => {
      const collaborationResponse = maybeHandleCollaborationRequest(path)
      if (collaborationResponse !== undefined) {
        return collaborationResponse
      }
      if (path === '/api/v1/analysis/config') {
        return mockConfig()
      }
      if (path === '/api/v1/analysis/goal-presets') {
        return mockGoalPresets()
      }
      if (path === '/api/v1/analysis/events') {
        return { status: 'accepted' }
      }
      if (path === '/api/v1/analysis/assets?media_type=audio&limit=12') {
        return { items: [] }
      }
      if (path === '/api/v1/analysis/jobs?media_type=audio&limit=12') {
        return { items: [audioItem] }
      }
      if (path === '/api/v1/analysis/jobs/job-audio') {
        return buildJobStatus(audioItem, audioResult)
      }
      if (path === '/api/v1/analysis/jobs/job-audio/benchmarks') {
        return mockBenchmarkResponse('job-audio')
      }
      if (path === '/api/v1/analysis/jobs/job-audio/verdict') {
        return mockVerdictResponse('job-audio')
      }
      if (path === '/api/v1/analysis/jobs/job-audio/calibration') {
        return mockCalibrationResponse('job-audio')
      }
      if (path === '/api/v1/analysis/jobs/job-audio/variants') {
        return { job_id: 'job-audio', items: [] }
      }
      throw new Error(`Unexpected path ${path}`)
    })

    render(<AnalysisPage session={session} />)

    await waitFor(() => {
      expect(screen.getByText('Step 1: Audio input')).toBeTruthy()
      expect(screen.getByText('Audio recommendation')).toBeTruthy()
      expect(screen.getAllByText('Assess narration pacing').length).toBeGreaterThan(0)
    })
  })

  it('renders progressive results from the live stream before the final dashboard is ready', async () => {
    const storedAsset = buildHistoryItem({
      jobId: 'job-asset-source',
      assetId: 'asset-live',
      filename: 'live.mp4',
      objective: 'Assess launch hook quality',
      goalTemplate: 'paid_social_hook',
      channel: 'meta_feed',
      audienceSegment: 'Prospecting audiences',
    }).asset

    const queuedJob = {
      id: 'job-live',
      asset_id: 'asset-live',
      status: 'queued',
      objective: 'Assess launch hook quality',
      goal_template: 'paid_social_hook',
      channel: 'meta_feed',
      audience_segment: 'Prospecting audiences',
      started_at: null,
      finished_at: null,
      error_message: null,
      created_at: '2026-03-31T10:10:00.000Z',
    }
    const processingJob = {
      ...queuedJob,
      status: 'processing',
      started_at: '2026-03-31T10:10:04.000Z',
    }
    const completedJob = {
      ...processingJob,
      status: 'completed',
      finished_at: '2026-03-31T10:10:25.000Z',
    }

    const previewResult = {
      ...buildResult('job-live', 77, 'Preview recommendation'),
      recommendations_json: [],
      segments_json: [
        {
          segment_index: 0,
          label: 'Scene 01',
          start_time_ms: 0,
          end_time_ms: 1500,
          attention_score: 77,
          engagement_delta: 6,
          note: 'Preview segment note',
        },
      ],
    }
    const finalResult = buildResult('job-live', 79, 'Final recommendation')

    let streamHandler: ((event: { event: string; data: unknown }) => void) | undefined

    window.sessionStorage.setItem(
      'neuromarketer.analysis.wizard.project-1',
      JSON.stringify({
        mediaType: 'video',
        objective: 'Assess launch hook quality',
        goalTemplate: 'paid_social_hook',
        channel: 'meta_feed',
        audienceSegment: 'Prospecting audiences',
        selectionMode: 'asset',
      }),
    )
    window.sessionStorage.setItem('neuromarketer.analysis.selected-asset.project-1', 'asset-live')

    mockedSubscribeToEventStream.mockImplementation(({ onMessage }) => {
      streamHandler = onMessage as (event: { event: string; data: unknown }) => void
      return vi.fn()
    })

    mockedApiRequest.mockImplementation(async (path, options) => {
      const collaborationResponse = maybeHandleCollaborationRequest(path)
      if (collaborationResponse !== undefined) {
        return collaborationResponse
      }
      if (path === '/api/v1/analysis/config') {
        return mockConfig()
      }
      if (path === '/api/v1/analysis/goal-presets') {
        return mockGoalPresets()
      }
      if (path === '/api/v1/analysis/events') {
        return { status: 'accepted' }
      }
      if (path === '/api/v1/analysis/assets?media_type=video&limit=12') {
        return { items: [storedAsset] }
      }
      if (path === '/api/v1/analysis/jobs?media_type=video&limit=12') {
        return { items: [] }
      }
      if (path === '/api/v1/analysis/jobs' && options?.method === 'POST') {
        return {
          job: queuedJob,
          asset: storedAsset,
          result: null,
        }
      }
      if (path === '/api/v1/analysis/jobs/job-live/benchmarks') {
        return mockBenchmarkResponse('job-live')
      }
      if (path === '/api/v1/analysis/jobs/job-live/verdict') {
        return mockVerdictResponse('job-live')
      }
      if (path === '/api/v1/analysis/jobs/job-live/calibration') {
        return mockCalibrationResponse('job-live')
      }
      if (path === '/api/v1/analysis/jobs/job-live/variants') {
        return { job_id: 'job-live', items: [] }
      }
      throw new Error(`Unexpected path ${path}`)
    })

    render(<AnalysisPage session={session} />)

    await waitFor(() => {
      expect(screen.getAllByText('live.mp4').length).toBeGreaterThan(0)
      expect((screen.getByText('Start analysis') as HTMLButtonElement).disabled).toBe(false)
    })

    fireEvent.click(screen.getByText('Start analysis'))

    await waitFor(() => {
      expect(streamHandler).toBeTruthy()
    })

    if (!streamHandler) {
      throw new Error('Expected the analysis event stream to be subscribed.')
    }
    const currentStreamHandler = streamHandler

    act(() => {
      currentStreamHandler({
        event: 'progress',
        data: {
          job: processingJob,
          asset: storedAsset,
          result: previewResult,
          stage: 'signals_ready',
          stage_label: 'Summary, charts, and scene diagnostics are ready. Recommendations are still running.',
          is_partial: true,
        },
      })
    })

    await waitFor(() => {
      expect(screen.getByText('Preview segment note')).toBeTruthy()
      expect(screen.getByText(/Recommendations are still being generated/i)).toBeTruthy()
    })
    expect((screen.getByTestId('analysis-action-export') as HTMLButtonElement).disabled).toBe(true)

    await waitFor(() => {
      const eventBodies = mockedApiRequest.mock.calls
        .filter(([path]) => path === '/api/v1/analysis/events')
        .map(([, requestOptions]) => requestOptions?.body as { event_name: string })
      expect(eventBodies.some((body) => body.event_name === 'first_result_seen')).toBe(true)
    })

    act(() => {
      currentStreamHandler({
        event: 'done',
        data: {
          job: completedJob,
          asset: storedAsset,
          result: finalResult,
        },
      })
    })

    await waitFor(() => {
      expect(screen.getByText('Final recommendation')).toBeTruthy()
      expect((screen.getByTestId('analysis-action-export') as HTMLButtonElement).disabled).toBe(false)
    })

    await waitFor(() => {
      const eventBodies = mockedApiRequest.mock.calls
        .filter(([path]) => path === '/api/v1/analysis/events')
        .map(([, requestOptions]) => requestOptions?.body as { event_name: string })
      expect(eventBodies.some((body) => body.event_name === 'analysis_started')).toBe(true)
      expect(eventBodies.some((body) => body.event_name === 'analysis_completed')).toBe(true)
    })
  })
})
