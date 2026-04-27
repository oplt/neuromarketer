import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AnalysisEvaluationSection from './AnalysisEvaluationSection'

vi.mock('../../lib/api', () => ({
  apiRequest: vi.fn(),
}))

import { apiRequest } from '../../lib/api'

const mockedApiRequest = vi.mocked(apiRequest)

function buildRecord(mode: 'marketing' | 'social_media') {
  return {
    id: `${mode}-id`,
    job_id: 'job-1',
    user_id: 'user-1',
    mode,
    status: 'completed',
    model_provider: 'ollama',
    model_name: 'gemma3:27b',
    prompt_version: `${mode}_v2`,
    error_message: null,
    created_at: '2026-03-31T10:00:00.000Z',
    updated_at: '2026-03-31T10:00:00.000Z',
    evaluation_json: {
      mode,
      overall_verdict: `${mode} verdict`,
      summary: `${mode} summary`,
      scores: {
        clarity: 70,
        engagement: 78,
        retention: 74,
        fit_for_purpose: mode === 'marketing' ? 81 : 76,
        risk: 28,
      },
      strengths: ['Strong opening'],
      weaknesses: ['Midpoint drag'],
      risks: [],
      recommendations: [],
      scorecard: {
        hook_or_opening: { score: 82, reason: 'Clear start.' },
        message_clarity: { score: 74, reason: 'Message is understandable.' },
        pacing: { score: 71, reason: 'Middle is slower.' },
        attention_alignment: { score: 75, reason: 'Attention supports the core goal.' },
        domain_effectiveness: { score: mode === 'marketing' ? 81 : 76, reason: 'Mode fit is solid.' },
      },
      model_metadata: {
        provider: 'ollama',
        model: 'gemma3:27b',
        tokens_in: 120,
        tokens_out: 240,
      },
      marketing_summary: mode === 'marketing' ? 'Marketing fit is solid.' : null,
      hook_assessment: mode === 'marketing' ? 'The hook is strong.' : null,
      value_prop_assessment: mode === 'marketing' ? 'Value is clear.' : null,
      conversion_friction_points: mode === 'marketing' ? ['Middle drag'] : [],
      brand_alignment_feedback: mode === 'marketing' ? 'Brand is consistent.' : null,
      social_summary: mode === 'social_media' ? 'Social fit is solid.' : null,
      scroll_stop_assessment: mode === 'social_media' ? 'The opening can stop the scroll.' : null,
      retention_assessment: mode === 'social_media' ? 'Retention holds reasonably well.' : null,
      platform_fit_feedback: mode === 'social_media' ? 'Feels feed-native.' : null,
      shareability_feedback: mode === 'social_media' ? 'Share potential is moderate.' : null,
    },
  }
}

function buildQueuedRecord(mode: 'marketing' | 'social_media', jobId: string) {
  return {
    ...buildRecord(mode),
    job_id: jobId,
    status: 'queued',
    evaluation_json: null,
    metadata_json: {
      progress: {
        stage: 'evaluation_queued',
        stage_label: `${mode === 'marketing' ? 'Marketing' : 'Social media'} evaluation queued. Waiting for worker capacity.`,
      },
    },
  }
}

function buildProcessingRecord(mode: 'marketing' | 'social_media', jobId: string) {
  return {
    ...buildQueuedRecord(mode, jobId),
    status: 'processing',
    metadata_json: {
      progress: {
        stage: 'evaluation_started',
        stage_label: `${mode === 'marketing' ? 'Marketing' : 'Social media'} evaluation is reading the completed analysis snapshot.`,
      },
    },
  }
}

async function flushEffects() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('AnalysisEvaluationSection', () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
    vi.useRealTimers()
  })

  it('renders multiple evaluation modes side by side from cached results', async () => {
    mockedApiRequest.mockResolvedValue({
      items: [buildRecord('marketing'), buildRecord('social_media')],
    })

    render(
      <AnalysisEvaluationSection
        analysisCompleted
        jobId="job-1"
        sessionToken="session-token"
      />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('evaluation-card-marketing')).toBeTruthy()
      expect(screen.getByTestId('evaluation-card-social_media')).toBeTruthy()
    })

    expect(screen.getByTestId('evaluation-comparison-grid')).toBeTruthy()
    expect(screen.getByText('marketing verdict')).toBeTruthy()
    expect(screen.getByText('social_media verdict')).toBeTruthy()
    expect(screen.getByText('Comparison snapshot')).toBeTruthy()
  })

  it('stops polling stale queued records after switching to a different job', async () => {
    vi.useFakeTimers()
    mockedApiRequest.mockImplementation(async (path) => {
      if (path === '/api/v1/analysis/jobs/job-1/evaluations') {
        return {
          items: [buildQueuedRecord('marketing', 'job-1')],
        }
      }
      if (path === '/api/v1/analysis/jobs/job-2/evaluations') {
        return {
          items: [],
        }
      }
      throw new Error(`Unexpected path: ${String(path)}`)
    })

    const { rerender } = render(
      <AnalysisEvaluationSection
        analysisCompleted
        jobId="job-1"
        sessionToken="session-token"
      />,
    )

    await flushEffects()
    expect(mockedApiRequest).toHaveBeenCalledWith(
      '/api/v1/analysis/jobs/job-1/evaluations',
      expect.objectContaining({ sessionToken: 'session-token' }),
    )

    rerender(
      <AnalysisEvaluationSection
        analysisCompleted
        jobId="job-2"
        sessionToken="session-token"
      />,
    )

    await flushEffects()
    expect(mockedApiRequest).toHaveBeenCalledWith(
      '/api/v1/analysis/jobs/job-2/evaluations',
      expect.objectContaining({ sessionToken: 'session-token' }),
    )

    await act(async () => {
      await vi.advanceTimersByTimeAsync(7_000)
    })

    expect(
      mockedApiRequest.mock.calls.filter(([path]) => path === '/api/v1/analysis/jobs/job-2/evaluations'),
    ).toHaveLength(1)
  })

  it('renders stage-aligned loading scaffolds and reports active evaluation progress', async () => {
    const onProgressSnapshot = vi.fn()

    mockedApiRequest.mockResolvedValue({
      items: [buildProcessingRecord('marketing', 'job-1')],
    })

    render(
      <AnalysisEvaluationSection
        analysisCompleted
        jobId="job-1"
        onProgressSnapshot={onProgressSnapshot}
        sessionToken="session-token"
      />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('evaluation-loading-marketing')).toBeTruthy()
    })

    expect(screen.getAllByText(/Marketing evaluation is reading the completed analysis snapshot/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Verdict, scorecard, risks, and recommendations are being drafted now/i)).toBeTruthy()

    await waitFor(() => {
      expect(onProgressSnapshot).toHaveBeenCalledWith({
        jobId: 'job-1',
        mode: 'marketing',
        stage: 'evaluation_started',
        stageLabel: 'Marketing evaluation is reading the completed analysis snapshot.',
      })
    })
  })
})
