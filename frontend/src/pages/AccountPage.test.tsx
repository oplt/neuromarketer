import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountPage, { __resetAccountPageRequestCacheForTests } from './AccountPage'

vi.mock('../lib/api', () => ({
  apiRequest: vi.fn(),
}))

import { apiRequest } from '../lib/api'

const mockedApiRequest = vi.mocked(apiRequest)

const session = {
  userId: 'user-1',
  email: 'owner@example.com',
  fullName: 'Owner Example',
  organizationName: 'Acme Workspace',
  organizationSlug: 'acme-workspace',
  defaultProjectId: 'project-1',
  defaultProjectName: 'Primary project',
  sessionToken: 'session-token',
}

function buildControlCenter(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    workspace_name: 'Acme Workspace',
    workspace_slug: 'acme-workspace',
    billing_email: 'finance@example.com',
    current_user_role: 'owner',
    permissions: {
      can_manage_api_keys: true,
      can_manage_webhooks: true,
      can_manage_members: true,
      can_view_audit_logs: true,
      can_manage_invites: true,
      can_manage_sso: true,
    },
    stats: {
      member_count: 2,
      project_count: 1,
      active_api_key_count: 0,
      active_webhook_count: 1,
      completed_analysis_count: 12,
    },
    available_api_key_scopes: ['analysis.read', 'analysis.write', 'admin'],
    available_webhook_events: ['analysis.job.completed', 'analysis.job.failed'],
    api_keys: [],
    webhooks: [
      {
        id: 'webhook-1',
        url: 'https://example.com/webhooks/analysis',
        subscribed_events: ['analysis.job.completed'],
        is_active: true,
        created_at: '2026-03-31T10:00:00.000Z',
        updated_at: '2026-03-31T10:00:00.000Z',
      },
    ],
    members: [
      {
        membership_id: 'membership-1',
        user_id: 'user-1',
        email: 'owner@example.com',
        full_name: 'Owner Example',
        role: 'owner',
        joined_at: '2026-03-30T10:00:00.000Z',
        is_current_user: true,
      },
      {
        membership_id: 'membership-2',
        user_id: 'user-2',
        email: 'member@example.com',
        full_name: 'Member Example',
        role: 'member',
        joined_at: '2026-03-30T11:00:00.000Z',
        is_current_user: false,
      },
    ],
    audit_logs: [
      {
        id: 'audit-1',
        created_at: '2026-03-31T12:00:00.000Z',
        action: 'account.webhook.created',
        entity_type: 'webhook_endpoint',
        entity_id: 'webhook-1',
        actor_email: 'owner@example.com',
        actor_full_name: 'Owner Example',
        payload_json: {
          url: 'https://example.com/webhooks/analysis',
        },
      },
    ],
    ...overrides,
  }
}

function buildSecurityOverview(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    session_policy: {
      absolute_ttl_minutes: 10080,
      idle_ttl_minutes: 1440,
      touch_interval_seconds: 60,
    },
    current_session_id: 'session-current',
    sessions: [
      {
        id: 'session-current',
        token_prefix: 'nmk_session_1234',
        user_agent: 'Vitest Browser',
        ip_address: '127.0.0.1',
        last_seen_at: '2026-03-31T12:00:00.000Z',
        expires_at: '2026-04-07T12:00:00.000Z',
        idle_expires_at: '2026-04-01T12:00:00.000Z',
        revoked_at: null,
        revoked_reason: null,
        is_current: true,
        created_at: '2026-03-31T10:00:00.000Z',
        updated_at: '2026-03-31T12:00:00.000Z',
      },
    ],
    mfa: {
      is_enabled: false,
      method_type: 'totp',
      recovery_codes_remaining: 0,
      pending_setup: false,
      last_used_at: null,
    },
    invites: [],
    sso: {
      provider_type: 'oidc',
      is_enabled: false,
      issuer_url: null,
      entrypoint_url: null,
      metadata_url: null,
      audience: null,
      client_id: null,
      has_client_secret: false,
      scopes: ['openid', 'profile', 'email'],
      attribute_mapping: { email: 'email', full_name: 'name' },
      certificate_pem: null,
      login_hint_domain: null,
      readiness_checks: ['Workspace SSO is not configured yet.'],
      updated_at: null,
    },
    available_sso_providers: ['oidc', 'saml'],
    ...overrides,
  }
}

describe('AccountPage', () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
    __resetAccountPageRequestCacheForTests()
  })

  it('loads the control center and creates an API key with a one-time token reveal', async () => {
    const initialControlCenter = buildControlCenter()
    const refreshedControlCenter = buildControlCenter({
      stats: {
        member_count: 2,
        project_count: 1,
        active_api_key_count: 1,
        active_webhook_count: 1,
        completed_analysis_count: 12,
      },
      api_keys: [
        {
          id: 'key-1',
          name: 'CI key',
          key_prefix: 'nmk_abcd1234',
          status: 'active',
          last_used_at: null,
          expires_at: '2026-06-29T10:00:00.000Z',
          scopes: ['analysis.read'],
          created_at: '2026-03-31T12:05:00.000Z',
          updated_at: '2026-03-31T12:05:00.000Z',
        },
      ],
    })

    let controlCenterCallCount = 0
    mockedApiRequest.mockImplementation(async (path, options) => {
      if (path === '/api/v1/account/control-center') {
        controlCenterCallCount += 1
        return controlCenterCallCount === 1 ? initialControlCenter : refreshedControlCenter
      }
      if (path === '/api/v1/account/security/overview') {
        return buildSecurityOverview()
      }
      if (path === '/api/v1/account/api-keys' && options?.method === 'POST') {
        return {
          api_key: refreshedControlCenter.api_keys[0],
          token: 'nmk_secret_value',
        }
      }
      throw new Error(`Unexpected path ${path}`)
    })

    render(<AccountPage session={session} />)

    await waitFor(() => {
      expect(screen.getByText('Workspace control center')).toBeTruthy()
      expect(screen.getByText('Audit trail')).toBeTruthy()
    })

    fireEvent.change(screen.getByLabelText('Key name'), {
      target: { value: 'CI key' },
    })
    fireEvent.change(screen.getByLabelText('API key scopes'), {
      target: { value: 'analysis.read' },
    })
    fireEvent.click(screen.getByText('Create API key'))

    await waitFor(() => {
      expect(screen.getByDisplayValue('nmk_secret_value')).toBeTruthy()
      expect(screen.getByText('CI key')).toBeTruthy()
      expect(screen.getByText('nmk_abcd1234')).toBeTruthy()
    })
  })

  it('dedupes mount-time control-center requests across immediate remounts', async () => {
    mockedApiRequest.mockImplementation(async (path) => {
      if (path === '/api/v1/account/control-center') {
        return buildControlCenter()
      }
      if (path === '/api/v1/account/security/overview') {
        return buildSecurityOverview()
      }
      throw new Error(`Unexpected path ${path}`)
    })

    const firstRender = render(<AccountPage session={session} />)

    await waitFor(() => {
      expect(screen.getByText('Workspace control center')).toBeTruthy()
    })

    firstRender.unmount()

    render(<AccountPage session={session} />)

    await waitFor(() => {
      expect(screen.getByText('Workspace control center')).toBeTruthy()
    })

    expect(mockedApiRequest.mock.calls.filter(([path]) => path === '/api/v1/account/control-center')).toHaveLength(1)
    expect(mockedApiRequest.mock.calls.filter(([path]) => path === '/api/v1/account/security/overview')).toHaveLength(1)
  })
})
