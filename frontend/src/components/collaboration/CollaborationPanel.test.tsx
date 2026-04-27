import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CollaborationPanel from './CollaborationPanel'
import { parseTimestampInput } from './timestamp'

vi.mock('../../lib/api', () => ({
  apiRequest: vi.fn(),
}))

import { apiRequest } from '../../lib/api'
import type { AuthSession } from '../../lib/session'

const mockedApiRequest = vi.mocked(apiRequest)

const session: AuthSession = {
  email: 'user@example.com',
  fullName: 'User',
  sessionToken: 'token-1',
  organizationName: 'Org',
  organizationSlug: 'org',
  defaultProjectId: 'proj-1',
  defaultProjectName: 'Project',
}

const baseReview = {
  entity_type: 'analysis_job' as const,
  entity_id: 'job-1',
  status: 'draft' as const,
  review_summary: null,
  comments: [],
}

function setupApiMock() {
  mockedApiRequest.mockImplementation(async (path: string) => {
    if (path === '/api/v1/analysis/collaboration/members') {
      return { items: [{ id: 'm-1', email: 'm@e', full_name: 'Member', role: 'reviewer' }] }
    }
    if (path.startsWith('/api/v1/analysis/collaboration/analysis_job/job-1')) {
      if (path.endsWith('/comments')) {
        return baseReview
      }
      return baseReview
    }
    throw new Error(`Unexpected path: ${path}`)
  })
}

describe('parseTimestampInput', () => {
  it('returns empty for blank input', () => {
    expect(parseTimestampInput('').kind).toBe('empty')
    expect(parseTimestampInput('   ').kind).toBe('empty')
  })

  it('returns invalid for non-finite numbers', () => {
    expect(parseTimestampInput('abc').kind).toBe('invalid')
    expect(parseTimestampInput('NaN').kind).toBe('invalid')
    expect(parseTimestampInput('-5').kind).toBe('invalid')
  })

  it('returns valid integer for finite numbers', () => {
    const parsed = parseTimestampInput('1500')
    expect(parsed.kind).toBe('valid')
    if (parsed.kind === 'valid') {
      expect(parsed.value).toBe(1500)
    }
  })

  it('rounds fractional inputs', () => {
    const parsed = parseTimestampInput('1500.6')
    expect(parsed.kind).toBe('valid')
    if (parsed.kind === 'valid') {
      expect(parsed.value).toBe(1501)
    }
  })
})

describe('CollaborationPanel', () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
  })

  it('does not refetch members when entityId changes but session/token does not', async () => {
    setupApiMock()
    const { rerender } = render(
      <CollaborationPanel
        allowTimestampComments
        entityId="job-1"
        entityType="analysis_job"
        session={session}
        subtitle="Subtitle"
        title="Collaboration"
      />,
    )

    await waitFor(() => {
      expect(
        mockedApiRequest.mock.calls.filter(([path]) => path === '/api/v1/analysis/collaboration/members'),
      ).toHaveLength(1)
    })

    rerender(
      <CollaborationPanel
        allowTimestampComments
        entityId="job-2"
        entityType="analysis_job"
        session={session}
        subtitle="Subtitle"
        title="Collaboration"
      />,
    )

    await waitFor(() => {
      expect(
        mockedApiRequest.mock.calls.filter(([path]) => path === '/api/v1/analysis/collaboration/analysis_job/job-2'),
      ).toHaveLength(1)
    })

    expect(
      mockedApiRequest.mock.calls.filter(([path]) => path === '/api/v1/analysis/collaboration/members'),
    ).toHaveLength(1)
  })

  it('blocks submission when timestamp is invalid', async () => {
    setupApiMock()
    render(
      <CollaborationPanel
        allowTimestampComments
        entityId="job-1"
        entityType="analysis_job"
        session={session}
        subtitle="Subtitle"
        title="Collaboration"
      />,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('Comment')).toBeTruthy()
    })

    fireEvent.change(screen.getByLabelText('Comment'), { target: { value: 'great clip' } })
    fireEvent.change(screen.getByLabelText('Timestamp (ms)'), { target: { value: '-5' } })

    const postButton = screen.getByRole('button', { name: /post comment/i }) as HTMLButtonElement
    expect(postButton.disabled).toBe(true)
  })

  it('submits without timestamp when field is empty', async () => {
    setupApiMock()
    render(
      <CollaborationPanel
        allowTimestampComments
        entityId="job-1"
        entityType="analysis_job"
        session={session}
        subtitle="Subtitle"
        title="Collaboration"
      />,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('Comment')).toBeTruthy()
    })

    fireEvent.change(screen.getByLabelText('Comment'), { target: { value: 'looks good' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /post comment/i }))
    })

    await waitFor(() => {
      expect(mockedApiRequest).toHaveBeenCalledWith(
        '/api/v1/analysis/collaboration/analysis_job/job-1/comments',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({ body: 'looks good', timestamp_ms: null }),
        }),
      )
    })
  })

  it('submits with valid timestamp', async () => {
    setupApiMock()
    render(
      <CollaborationPanel
        allowTimestampComments
        entityId="job-1"
        entityType="analysis_job"
        session={session}
        subtitle="Subtitle"
        title="Collaboration"
      />,
    )

    await waitFor(() => {
      expect(screen.getByLabelText('Comment')).toBeTruthy()
    })

    fireEvent.change(screen.getByLabelText('Comment'), { target: { value: 'note at marker' } })
    fireEvent.change(screen.getByLabelText('Timestamp (ms)'), { target: { value: '2400' } })

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /post comment/i }))
    })

    await waitFor(() => {
      expect(mockedApiRequest).toHaveBeenCalledWith(
        '/api/v1/analysis/collaboration/analysis_job/job-1/comments',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({ body: 'note at marker', timestamp_ms: 2400 }),
        }),
      )
    })
  })
})
