import { render, screen, waitFor } from '@testing-library/react'
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

describe('AnalysisEvaluationSection', () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
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
})
