import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AnalysisPage from './AnalysisPage'

vi.mock('../components/analysis/AnalysisEvaluationSection', () => ({
  default: () => null,
}))

vi.mock('../lib/api', () => ({
  apiRequest: vi.fn(),
  uploadToApi: vi.fn(),
  uploadToSignedUrl: vi.fn(),
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

function buildHistoryItem({
  jobId,
  assetId,
  filename,
  objective,
}: {
  jobId: string
  assetId: string
  filename: string
  objective: string
}) {
  return {
    job: {
      id: jobId,
      asset_id: assetId,
      status: 'completed',
      objective,
      started_at: '2026-03-31T09:58:00.000Z',
      finished_at: '2026-03-31T10:00:00.000Z',
      error_message: null,
      created_at: '2026-03-31T09:55:00.000Z',
    },
    asset: {
      id: assetId,
      media_type: 'video',
      original_filename: filename,
      mime_type: 'video/mp4',
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

function buildResult(jobId: string, attentionScore: number, recommendationTitle: string) {
  return {
    job_id: jobId,
    summary_json: {
      modality: 'video',
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

describe('AnalysisPage', () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
    window.sessionStorage.clear()
  })

  it('loads recent completed analyses and shows clicked results on the page', async () => {
    const alphaItem = buildHistoryItem({
      jobId: 'job-alpha',
      assetId: 'asset-alpha',
      filename: 'alpha.mp4',
      objective: 'Assess the launch hook',
    })
    const betaItem = buildHistoryItem({
      jobId: 'job-beta',
      assetId: 'asset-beta',
      filename: 'beta.mp4',
      objective: 'Assess the retention curve',
    })
    const alphaResult = buildResult('job-alpha', 41, 'Alpha recommendation')
    const betaResult = buildResult('job-beta', 88, 'Beta recommendation')

    mockedApiRequest.mockImplementation(async (path) => {
      if (path === '/api/v1/analysis/config') {
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
      if (path === '/api/v1/analysis/assets?media_type=video&limit=12') {
        return { items: [] }
      }
      if (path === '/api/v1/analysis/jobs?media_type=video&limit=12') {
        return { items: [alphaItem, betaItem] }
      }
      if (path === '/api/v1/analysis/jobs/job-alpha') {
        return { job: alphaItem.job, result: alphaResult }
      }
      if (path === '/api/v1/analysis/jobs/job-beta') {
        return { job: betaItem.job, result: betaResult }
      }
      throw new Error(`Unexpected path ${path}`)
    })

    render(<AnalysisPage session={session} />)

    await waitFor(() => {
      expect(screen.getByText('Alpha recommendation')).toBeTruthy()
      expect(screen.getByTestId('analysis-history-list')).toBeTruthy()
    })

    fireEvent.click(screen.getByTestId('analysis-history-item-job-beta'))

    await waitFor(() => {
      expect(screen.getByText('Beta recommendation')).toBeTruthy()
    })
  })
})
