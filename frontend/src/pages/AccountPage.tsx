import KeyRounded from '@mui/icons-material/KeyRounded'
import LinkRounded from '@mui/icons-material/LinkRounded'
import ManageAccountsRounded from '@mui/icons-material/ManageAccountsRounded'
import RefreshRounded from '@mui/icons-material/RefreshRounded'
import ShieldRounded from '@mui/icons-material/ShieldRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useEffectEvent, useMemo, useState } from 'react'

import { apiRequest } from '../lib/api'
import { clearStoredSession, type AuthSession } from '../lib/session'

type AccountPageProps = {
  session: AuthSession
}

type OrgRoleValue = 'owner' | 'admin' | 'member' | 'viewer'
type ApiKeyStatusValue = 'active' | 'revoked'

type AccountPermissions = {
  can_manage_api_keys: boolean
  can_manage_webhooks: boolean
  can_manage_members: boolean
  can_view_audit_logs: boolean
  can_manage_invites: boolean
  can_manage_sso: boolean
}

type AccountWorkspaceStats = {
  member_count: number
  project_count: number
  active_api_key_count: number
  active_webhook_count: number
  completed_analysis_count: number
}

type AccountApiKey = {
  id: string
  name: string
  key_prefix: string
  status: ApiKeyStatusValue
  last_used_at?: string | null
  expires_at?: string | null
  scopes: string[]
  created_at: string
  updated_at: string
}

type AccountWebhook = {
  id: string
  url: string
  subscribed_events: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

type AccountMember = {
  membership_id: string
  user_id: string
  email: string
  full_name?: string | null
  role: OrgRoleValue
  joined_at: string
  is_current_user: boolean
}

type AccountAuditLog = {
  id: string
  created_at: string
  action: string
  entity_type: string
  entity_id?: string | null
  actor_email?: string | null
  actor_full_name?: string | null
  payload_json: Record<string, unknown>
}

type AccountControlCenter = {
  workspace_name: string
  workspace_slug: string
  billing_email?: string | null
  current_user_role: OrgRoleValue
  permissions: AccountPermissions
  stats: AccountWorkspaceStats
  available_api_key_scopes: string[]
  available_webhook_events: string[]
  api_keys: AccountApiKey[]
  webhooks: AccountWebhook[]
  members: AccountMember[]
  audit_logs: AccountAuditLog[]
}

type AccountInviteStatusValue = 'pending' | 'accepted' | 'revoked' | 'expired'
type AccountSsoProviderValue = 'oidc' | 'saml'

type AccountInvite = {
  id: string
  email: string
  role: OrgRoleValue
  status: AccountInviteStatusValue
  token_prefix: string
  expires_at: string
  accepted_at?: string | null
  revoked_at?: string | null
  invited_by_email?: string | null
  invited_by_full_name?: string | null
  accepted_by_email?: string | null
  accepted_by_full_name?: string | null
  created_at: string
  updated_at: string
}

type AccountSessionPolicy = {
  absolute_ttl_minutes: number
  idle_ttl_minutes: number
  touch_interval_seconds: number
}

type AccountUserSession = {
  id: string
  token_prefix: string
  user_agent?: string | null
  ip_address?: string | null
  last_seen_at: string
  expires_at: string
  idle_expires_at: string
  revoked_at?: string | null
  revoked_reason?: string | null
  is_current: boolean
  created_at: string
  updated_at: string
}

type AccountMfaStatus = {
  is_enabled: boolean
  method_type?: string | null
  recovery_codes_remaining: number
  pending_setup: boolean
  last_used_at?: string | null
}

type AccountSsoConfig = {
  provider_type: AccountSsoProviderValue
  is_enabled: boolean
  issuer_url?: string | null
  entrypoint_url?: string | null
  metadata_url?: string | null
  audience?: string | null
  client_id?: string | null
  has_client_secret: boolean
  scopes: string[]
  attribute_mapping: Record<string, unknown>
  certificate_pem?: string | null
  login_hint_domain?: string | null
  readiness_checks: string[]
  updated_at?: string | null
}

type AccountSecurityOverview = {
  session_policy: AccountSessionPolicy
  current_session_id?: string | null
  sessions: AccountUserSession[]
  mfa: AccountMfaStatus
  invites: AccountInvite[]
  sso: AccountSsoConfig
  available_sso_providers: AccountSsoProviderValue[]
}

type InviteCreateResponse = {
  invite: AccountInvite
  invite_token: string
  invite_url: string
}

type MfaSetupResponse = {
  method_type: 'totp'
  secret: string
  otpauth_uri: string
  issuer: string
}

type MfaRecoveryCodesResponse = {
  recovery_codes: string[]
  status: AccountMfaStatus
}

type ApiKeyCreateResponse = {
  api_key: AccountApiKey
  token: string
}

type ApiKeyRotateResponse = {
  rotated_from: AccountApiKey
  api_key: AccountApiKey
  token: string
}

type WebhookSecretResponse = {
  webhook: AccountWebhook
  signing_secret: string
}

type WebhookDraft = {
  url: string
  eventsText: string
  isActive: boolean
}

type FeedbackMessage = {
  type: 'success' | 'error' | 'info'
  message: string
}

type AccountCacheEntry<T> = {
  sessionToken: string
  value: T
  loadedAt: number
}

const ACCOUNT_CACHE_TTL_MS = 30_000

let controlCenterCache: AccountCacheEntry<AccountControlCenter> | null = null
let inFlightControlCenterRequest: Promise<AccountControlCenter> | null = null
let securityOverviewCache: AccountCacheEntry<AccountSecurityOverview> | null = null
let inFlightSecurityOverviewRequest: Promise<AccountSecurityOverview> | null = null

function isAccountCacheFresh(cacheEntry: AccountCacheEntry<unknown> | null, sessionToken: string) {
  return cacheEntry !== null && cacheEntry.sessionToken === sessionToken && Date.now() - cacheEntry.loadedAt <= ACCOUNT_CACHE_TTL_MS
}

async function fetchAccountControlCenter(sessionToken: string, force = false) {
  const cachedValue = controlCenterCache
  if (!force && cachedValue && isAccountCacheFresh(cachedValue, sessionToken)) {
    return cachedValue.value
  }
  if (!force && inFlightControlCenterRequest) {
    return inFlightControlCenterRequest
  }

  const request = apiRequest<AccountControlCenter>('/api/v1/account/control-center', { sessionToken })
    .then((response) => {
      controlCenterCache = {
        sessionToken,
        value: response,
        loadedAt: Date.now(),
      }
      return response
    })
    .finally(() => {
      inFlightControlCenterRequest = null
    })

  inFlightControlCenterRequest = request
  return request
}

async function fetchAccountSecurityOverview(sessionToken: string, force = false) {
  const cachedValue = securityOverviewCache
  if (!force && cachedValue && isAccountCacheFresh(cachedValue, sessionToken)) {
    return cachedValue.value
  }
  if (!force && inFlightSecurityOverviewRequest) {
    return inFlightSecurityOverviewRequest
  }

  const request = apiRequest<AccountSecurityOverview>('/api/v1/account/security/overview', { sessionToken })
    .then((response) => {
      securityOverviewCache = {
        sessionToken,
        value: response,
        loadedAt: Date.now(),
      }
      return response
    })
    .finally(() => {
      inFlightSecurityOverviewRequest = null
    })

  inFlightSecurityOverviewRequest = request
  return request
}

export function __resetAccountPageRequestCacheForTests() {
  controlCenterCache = null
  inFlightControlCenterRequest = null
  securityOverviewCache = null
  inFlightSecurityOverviewRequest = null
}

function AccountPage({ session }: AccountPageProps) {
  const sessionToken = session.sessionToken || ''
  const [controlCenter, setControlCenter] = useState<AccountControlCenter | null>(null)
  const [securityOverview, setSecurityOverview] = useState<AccountSecurityOverview | null>(null)
  const [feedbackMessage, setFeedbackMessage] = useState<FeedbackMessage | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [activeMutationKey, setActiveMutationKey] = useState<string | null>(null)
  const [apiKeyName, setApiKeyName] = useState('')
  const [apiKeyExpiresInDays, setApiKeyExpiresInDays] = useState('90')
  const [apiKeyScopesText, setApiKeyScopesText] = useState('analysis.read')
  const [revealedApiKeyToken, setRevealedApiKeyToken] = useState<{ label: string; token: string } | null>(null)
  const [webhookUrl, setWebhookUrl] = useState('')
  const [webhookEventsText, setWebhookEventsText] = useState('analysis.job.completed')
  const [webhookDrafts, setWebhookDrafts] = useState<Record<string, WebhookDraft>>({})
  const [revealedWebhookSecret, setRevealedWebhookSecret] = useState<{ label: string; secret: string } | null>(null)
  const [memberRoleDrafts, setMemberRoleDrafts] = useState<Record<string, OrgRoleValue>>({})
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<OrgRoleValue>('viewer')
  const [inviteExpiresInHours, setInviteExpiresInHours] = useState('168')
  const [revealedInvite, setRevealedInvite] = useState<{ email: string; token: string; url: string } | null>(null)
  const [mfaSetup, setMfaSetup] = useState<MfaSetupResponse | null>(null)
  const [mfaVerificationCode, setMfaVerificationCode] = useState('')
  const [mfaDisableCode, setMfaDisableCode] = useState('')
  const [mfaDisableRecoveryCode, setMfaDisableRecoveryCode] = useState('')
  const [revealedRecoveryCodes, setRevealedRecoveryCodes] = useState<string[]>([])
  const [ssoProvider, setSsoProvider] = useState<AccountSsoProviderValue>('oidc')
  const [ssoEnabled, setSsoEnabled] = useState(false)
  const [ssoIssuerUrl, setSsoIssuerUrl] = useState('')
  const [ssoEntrypointUrl, setSsoEntrypointUrl] = useState('')
  const [ssoMetadataUrl, setSsoMetadataUrl] = useState('')
  const [ssoAudience, setSsoAudience] = useState('')
  const [ssoClientId, setSsoClientId] = useState('')
  const [ssoClientSecret, setSsoClientSecret] = useState('')
  const [ssoScopesText, setSsoScopesText] = useState('openid, profile, email')
  const [ssoLoginHintDomain, setSsoLoginHintDomain] = useState('')
  const [ssoCertificatePem, setSsoCertificatePem] = useState('')
  const [ssoAttributeMappingText, setSsoAttributeMappingText] = useState('{"email":"email","full_name":"name"}')

  const loadAccountData = useEffectEvent(async (force = false) => {
    if (!sessionToken) {
      setFeedbackMessage({ type: 'error', message: 'Sign in again to manage workspace controls.' })
      return
    }

    if (!controlCenter || !securityOverview || force) {
      setIsLoading(true)
    } else {
      setIsRefreshing(true)
    }

    try {
      const [controlCenterResponse, securityOverviewResponse] = await Promise.all([
        fetchAccountControlCenter(sessionToken, force),
        fetchAccountSecurityOverview(sessionToken, force),
      ])
      setControlCenter(controlCenterResponse)
      setSecurityOverview(securityOverviewResponse)
      setFeedbackMessage((current) => (current?.type === 'error' ? null : current))
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load workspace controls.',
      })
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  })

  useEffect(() => {
    void loadAccountData()
  }, [loadAccountData])

  useEffect(() => {
    if (!controlCenter) {
      return
    }
    setWebhookDrafts(
      Object.fromEntries(
        controlCenter.webhooks.map((webhook) => [
          webhook.id,
          {
            url: webhook.url,
            eventsText: webhook.subscribed_events.join(', '),
            isActive: webhook.is_active,
          },
        ]),
      ),
    )
    setMemberRoleDrafts(
      Object.fromEntries(controlCenter.members.map((member) => [member.membership_id, member.role])),
    )
  }, [controlCenter])

  useEffect(() => {
    if (!securityOverview) {
      return
    }
    setSsoProvider(securityOverview.sso.provider_type || 'oidc')
    setSsoEnabled(Boolean(securityOverview.sso.is_enabled))
    setSsoIssuerUrl(securityOverview.sso.issuer_url || '')
    setSsoEntrypointUrl(securityOverview.sso.entrypoint_url || '')
    setSsoMetadataUrl(securityOverview.sso.metadata_url || '')
    setSsoAudience(securityOverview.sso.audience || '')
    setSsoClientId(securityOverview.sso.client_id || '')
    setSsoScopesText((securityOverview.sso.scopes || []).join(', '))
    setSsoLoginHintDomain(securityOverview.sso.login_hint_domain || '')
    setSsoCertificatePem(securityOverview.sso.certificate_pem || '')
    setSsoAttributeMappingText(
      JSON.stringify(securityOverview.sso.attribute_mapping || { email: 'email', full_name: 'name' }, null, 2),
    )
  }, [securityOverview])

  const permissions = controlCenter?.permissions
  const stats = controlCenter?.stats
  const currentUserRoleLabel = useMemo(
    () => readableRole(controlCenter?.current_user_role || 'viewer'),
    [controlCenter?.current_user_role],
  )

  const handleCreateApiKey = async () => {
    if (!sessionToken || !apiKeyName.trim()) {
      return
    }
    setActiveMutationKey('api-key-create')
    try {
      const response = await apiRequest<ApiKeyCreateResponse>('/api/v1/account/api-keys', {
        method: 'POST',
        sessionToken,
        body: {
          name: apiKeyName.trim(),
          scopes: parseCommaSeparatedList(apiKeyScopesText),
          expires_in_days: apiKeyExpiresInDays.trim() ? Number(apiKeyExpiresInDays) : null,
        },
      })
      setRevealedApiKeyToken({
        label: response.api_key.name,
        token: response.token,
      })
      setApiKeyName('')
      setApiKeyExpiresInDays('90')
      setFeedbackMessage({ type: 'success', message: 'API key created. Copy it now; the token is only shown once.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to create API key.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleRevokeApiKey = async (apiKeyId: string) => {
    if (!sessionToken) {
      return
    }
    setActiveMutationKey(`api-key-revoke:${apiKeyId}`)
    try {
      await apiRequest(`/api/v1/account/api-keys/${apiKeyId}/revoke`, {
        method: 'POST',
        sessionToken,
      })
      setFeedbackMessage({ type: 'success', message: 'API key revoked.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to revoke API key.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleRotateApiKey = async (apiKeyId: string) => {
    if (!sessionToken) {
      return
    }
    setActiveMutationKey(`api-key-rotate:${apiKeyId}`)
    try {
      const response = await apiRequest<ApiKeyRotateResponse>(`/api/v1/account/api-keys/${apiKeyId}/rotate`, {
        method: 'POST',
        sessionToken,
      })
      setRevealedApiKeyToken({
        label: response.api_key.name,
        token: response.token,
      })
      setFeedbackMessage({
        type: 'success',
        message: `API key rotated. ${response.rotated_from.key_prefix} is now revoked.`,
      })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to rotate API key.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleCreateWebhook = async () => {
    if (!sessionToken || !webhookUrl.trim()) {
      return
    }
    setActiveMutationKey('webhook-create')
    try {
      const response = await apiRequest<WebhookSecretResponse>('/api/v1/account/webhooks', {
        method: 'POST',
        sessionToken,
        body: {
          url: webhookUrl.trim(),
          subscribed_events: parseCommaSeparatedList(webhookEventsText),
          is_active: true,
        },
      })
      setRevealedWebhookSecret({
        label: response.webhook.url,
        secret: response.signing_secret,
      })
      setWebhookUrl('')
      setWebhookEventsText('analysis.job.completed')
      setFeedbackMessage({ type: 'success', message: 'Webhook endpoint created. Store the signing secret now.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to create webhook endpoint.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleSaveWebhook = async (webhookId: string) => {
    if (!sessionToken) {
      return
    }
    const draft = webhookDrafts[webhookId]
    if (!draft) {
      return
    }
    setActiveMutationKey(`webhook-save:${webhookId}`)
    try {
      await apiRequest(`/api/v1/account/webhooks/${webhookId}`, {
        method: 'PUT',
        sessionToken,
        body: {
          url: draft.url.trim(),
          subscribed_events: parseCommaSeparatedList(draft.eventsText),
          is_active: draft.isActive,
        },
      })
      setFeedbackMessage({ type: 'success', message: 'Webhook endpoint updated.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to update webhook endpoint.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleRotateWebhookSecret = async (webhookId: string) => {
    if (!sessionToken) {
      return
    }
    setActiveMutationKey(`webhook-rotate:${webhookId}`)
    try {
      const response = await apiRequest<WebhookSecretResponse>(`/api/v1/account/webhooks/${webhookId}/rotate-secret`, {
        method: 'POST',
        sessionToken,
      })
      setRevealedWebhookSecret({
        label: response.webhook.url,
        secret: response.signing_secret,
      })
      setFeedbackMessage({ type: 'success', message: 'Webhook signing secret rotated.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to rotate webhook secret.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleSaveMemberRole = async (membershipId: string) => {
    if (!sessionToken) {
      return
    }
    const nextRole = memberRoleDrafts[membershipId]
    if (!nextRole) {
      return
    }
    setActiveMutationKey(`member-role:${membershipId}`)
    try {
      await apiRequest(`/api/v1/account/members/${membershipId}`, {
        method: 'PUT',
        sessionToken,
        body: { role: nextRole },
      })
      setFeedbackMessage({ type: 'success', message: 'Workspace role updated.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to update workspace role.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleCreateInvite = async () => {
    if (!sessionToken || !inviteEmail.trim()) {
      return
    }
    setActiveMutationKey('invite-create')
    try {
      const response = await apiRequest<InviteCreateResponse>('/api/v1/account/invites', {
        method: 'POST',
        sessionToken,
        body: {
          email: inviteEmail.trim(),
          role: inviteRole,
          expires_in_hours: inviteExpiresInHours.trim() ? Number(inviteExpiresInHours) : null,
        },
      })
      setInviteEmail('')
      setInviteRole('viewer')
      setInviteExpiresInHours('168')
      setRevealedInvite({
        email: response.invite.email,
        token: response.invite_token,
        url: response.invite_url,
      })
      setFeedbackMessage({ type: 'success', message: 'Invite created. Copy the invite link or token now.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to create invite.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleRevokeInvite = async (inviteId: string) => {
    if (!sessionToken) {
      return
    }
    setActiveMutationKey(`invite-revoke:${inviteId}`)
    try {
      await apiRequest(`/api/v1/account/invites/${inviteId}/revoke`, {
        method: 'POST',
        sessionToken,
      })
      setFeedbackMessage({ type: 'success', message: 'Invite revoked.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to revoke invite.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleStartMfaSetup = async () => {
    if (!sessionToken) {
      return
    }
    setActiveMutationKey('mfa-setup')
    try {
      const response = await apiRequest<MfaSetupResponse>('/api/v1/account/mfa/setup', {
        method: 'POST',
        sessionToken,
      })
      setMfaSetup(response)
      setRevealedRecoveryCodes([])
      setMfaVerificationCode('')
      setFeedbackMessage({ type: 'info', message: 'Scan the secret in your authenticator and confirm with a code.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to start MFA setup.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleConfirmMfaSetup = async () => {
    if (!sessionToken || !mfaVerificationCode.trim()) {
      return
    }
    setActiveMutationKey('mfa-confirm')
    try {
      const response = await apiRequest<MfaRecoveryCodesResponse>('/api/v1/account/mfa/confirm', {
        method: 'POST',
        sessionToken,
        body: { code: mfaVerificationCode.trim() },
      })
      setMfaSetup(null)
      setMfaVerificationCode('')
      setRevealedRecoveryCodes(response.recovery_codes)
      setFeedbackMessage({ type: 'success', message: 'MFA enabled. Store the recovery codes now.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to confirm MFA setup.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleDisableMfa = async () => {
    if (!sessionToken || (!mfaDisableCode.trim() && !mfaDisableRecoveryCode.trim())) {
      return
    }
    setActiveMutationKey('mfa-disable')
    try {
      await apiRequest('/api/v1/account/mfa/disable', {
        method: 'POST',
        sessionToken,
        body: {
          code: mfaDisableCode.trim() || null,
          recovery_code: mfaDisableRecoveryCode.trim() || null,
        },
      })
      setMfaDisableCode('')
      setMfaDisableRecoveryCode('')
      setMfaSetup(null)
      setRevealedRecoveryCodes([])
      setFeedbackMessage({ type: 'success', message: 'MFA disabled for this account.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to disable MFA.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleRegenerateRecoveryCodes = async () => {
    if (!sessionToken || (!mfaDisableCode.trim() && !mfaDisableRecoveryCode.trim())) {
      return
    }
    setActiveMutationKey('mfa-recovery')
    try {
      const response = await apiRequest<MfaRecoveryCodesResponse>('/api/v1/account/mfa/recovery-codes/regenerate', {
        method: 'POST',
        sessionToken,
        body: {
          code: mfaDisableCode.trim() || null,
          recovery_code: mfaDisableRecoveryCode.trim() || null,
        },
      })
      setRevealedRecoveryCodes(response.recovery_codes)
      setMfaDisableCode('')
      setMfaDisableRecoveryCode('')
      setFeedbackMessage({ type: 'success', message: 'Recovery codes regenerated. Store them now.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to regenerate recovery codes.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleRevokeSession = async (sessionId: string, isCurrent: boolean) => {
    if (!sessionToken) {
      return
    }
    setActiveMutationKey(`session-revoke:${sessionId}`)
    try {
      await apiRequest(`/api/v1/account/sessions/${sessionId}/revoke`, {
        method: 'POST',
        sessionToken,
      })
      if (isCurrent) {
        clearStoredSession()
        window.location.reload()
        return
      }
      setFeedbackMessage({ type: 'success', message: 'Session revoked.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to revoke session.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  const handleSaveSso = async () => {
    if (!sessionToken) {
      return
    }
    setActiveMutationKey('sso-save')
    try {
      await apiRequest('/api/v1/account/sso', {
        method: 'PUT',
        sessionToken,
        body: {
          provider_type: ssoProvider,
          is_enabled: ssoEnabled,
          issuer_url: ssoIssuerUrl.trim() || null,
          entrypoint_url: ssoEntrypointUrl.trim() || null,
          metadata_url: ssoMetadataUrl.trim() || null,
          audience: ssoAudience.trim() || null,
          client_id: ssoClientId.trim() || null,
          client_secret: ssoClientSecret.trim() || null,
          scopes: parseCommaSeparatedList(ssoScopesText),
          attribute_mapping: parseJsonObject(ssoAttributeMappingText),
          certificate_pem: ssoCertificatePem.trim() || null,
          login_hint_domain: ssoLoginHintDomain.trim() || null,
        },
      })
      setSsoClientSecret('')
      setFeedbackMessage({ type: 'success', message: 'SSO configuration updated.' })
      await loadAccountData(true)
    } catch (error) {
      setFeedbackMessage({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to update SSO configuration.',
      })
    } finally {
      setActiveMutationKey(null)
    }
  }

  return (
    <Stack spacing={3}>
      {feedbackMessage ? <Alert severity={feedbackMessage.type}>{feedbackMessage.message}</Alert> : null}
      {revealedInvite ? (
        <Alert severity="success">
          <Stack spacing={1.25}>
            <Typography variant="subtitle2">Invite created for {revealedInvite.email}</Typography>
            <TextField InputProps={{ readOnly: true }} label="Invite link" value={revealedInvite.url} />
            <TextField InputProps={{ readOnly: true }} label="Invite token" value={revealedInvite.token} />
          </Stack>
        </Alert>
      ) : null}
      {revealedRecoveryCodes.length > 0 ? (
        <Alert severity="warning">
          <Stack spacing={1.25}>
            <Typography variant="subtitle2">Recovery codes</Typography>
            <Typography variant="body2">Store these now. They are only shown once.</Typography>
            <TextField
              InputProps={{ readOnly: true }}
              label="Recovery codes"
              minRows={4}
              multiline
              value={revealedRecoveryCodes.join('\n')}
            />
          </Stack>
        </Alert>
      ) : null}
      {isLoading && !controlCenter ? <LinearProgress sx={{ borderRadius: 999, height: 8 }} /> : null}

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
          <Stack spacing={2.5}>
            <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
              <Box>
                <Typography variant="h6">Workspace control center</Typography>
                <Typography color="text.secondary" variant="body2">
                  API keys, webhook endpoints, member roles, and audit history for the active workspace.
                </Typography>
              </Box>
              <Button
                disabled={isLoading || isRefreshing || !sessionToken}
                onClick={() => void loadAccountData(true)}
                size="small"
                startIcon={<RefreshRounded />}
                variant="outlined"
              >
                Refresh
              </Button>
            </Stack>

            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip icon={<ShieldRounded />} label={controlCenter?.workspace_name || session.organizationName || 'Workspace'} />
              <Chip label={currentUserRoleLabel} variant="outlined" />
              <Chip label={controlCenter?.workspace_slug || session.organizationSlug || 'workspace'} variant="outlined" />
            </Stack>

            <Stack spacing={1.1}>
              <DetailRow label="Billing email" value={controlCenter?.billing_email || session.email} />
              <DetailRow label="Current project" value={session.defaultProjectName || 'Default Analysis Project'} />
              <DetailRow label="Session posture" value={permissions ? buildPermissionSummary(permissions) : 'Loading permissions…'} />
            </Stack>
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Usage snapshot</Typography>
            <Typography color="text.secondary" variant="body2">
              Practical usage signals for operations and internal billing conversations.
            </Typography>
            <Stack spacing={1.1}>
              <DetailRow label="Members" value={stats ? String(stats.member_count) : '—'} />
              <DetailRow label="Projects" value={stats ? String(stats.project_count) : '—'} />
              <DetailRow label="Completed analyses" value={stats ? String(stats.completed_analysis_count) : '—'} />
              <DetailRow label="Active API keys" value={stats ? String(stats.active_api_key_count) : '—'} />
              <DetailRow label="Active webhooks" value={stats ? String(stats.active_webhook_count) : '—'} />
            </Stack>
            {isRefreshing ? <LinearProgress sx={{ borderRadius: 999, height: 8 }} /> : null}
          </Stack>
        </Paper>
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Session security</Typography>
            <Typography color="text.secondary" variant="body2">
              Review active browser sessions, revoke stale access, and confirm the current session policy.
            </Typography>
            <Stack spacing={1.1}>
              <DetailRow
                label="Absolute TTL"
                value={securityOverview ? `${securityOverview.session_policy.absolute_ttl_minutes} minutes` : '—'}
              />
              <DetailRow
                label="Idle timeout"
                value={securityOverview ? `${securityOverview.session_policy.idle_ttl_minutes} minutes` : '—'}
              />
              <DetailRow
                label="Touch cadence"
                value={securityOverview ? `${securityOverview.session_policy.touch_interval_seconds} seconds` : '—'}
              />
            </Stack>
            {securityOverview && securityOverview.sessions.length === 0 ? (
              <EmptyState message="No active sessions are recorded for this account." />
            ) : null}
            {securityOverview && securityOverview.sessions.length > 0 ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Token</TableCell>
                    <TableCell>Client</TableCell>
                    <TableCell>Last seen</TableCell>
                    <TableCell>Expires</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {securityOverview.sessions.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                          <Typography variant="body2">{item.token_prefix}</Typography>
                          {item.is_current ? <Chip label="Current" size="small" variant="outlined" /> : null}
                        </Stack>
                      </TableCell>
                      <TableCell>{summarizeSessionClient(item)}</TableCell>
                      <TableCell>{formatDateTime(item.last_seen_at)}</TableCell>
                      <TableCell>{formatDateTime(item.expires_at)}</TableCell>
                      <TableCell align="right">
                        <Button
                          disabled={Boolean(item.revoked_at) || activeMutationKey === `session-revoke:${item.id}`}
                          onClick={() => void handleRevokeSession(item.id, item.is_current)}
                          size="small"
                          variant="outlined"
                        >
                          {activeMutationKey === `session-revoke:${item.id}` ? 'Revoking…' : item.is_current ? 'Sign out' : 'Revoke'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Multi-factor authentication</Typography>
            <Typography color="text.secondary" variant="body2">
              Enable TOTP-based MFA with one-time recovery codes for account recovery.
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip
                color={securityOverview?.mfa.is_enabled ? 'primary' : 'default'}
                label={securityOverview?.mfa.is_enabled ? 'MFA enabled' : 'MFA not enabled'}
                variant={securityOverview?.mfa.is_enabled ? 'filled' : 'outlined'}
              />
              <Chip
                label={
                  securityOverview
                    ? `${securityOverview.mfa.recovery_codes_remaining} recovery codes left`
                    : 'Recovery codes unavailable'
                }
                variant="outlined"
              />
            </Stack>
            <Stack spacing={1.1}>
              <DetailRow label="Method" value={securityOverview?.mfa.method_type || 'totp'} />
              <DetailRow
                label="Last used"
                value={securityOverview?.mfa.last_used_at ? formatDateTime(securityOverview.mfa.last_used_at) : 'Not recorded'}
              />
              <DetailRow
                label="Pending setup"
                value={securityOverview?.mfa.pending_setup ? 'Awaiting confirmation' : 'No'}
              />
            </Stack>
            {mfaSetup ? (
              <Alert severity="info">
                <Stack spacing={1.25}>
                  <TextField InputProps={{ readOnly: true }} label="Manual secret" value={mfaSetup.secret} />
                  <TextField InputProps={{ readOnly: true }} label="OTPAuth URI" value={mfaSetup.otpauth_uri} />
                </Stack>
              </Alert>
            ) : null}
            <TextField
              helperText="Use the 6-digit code from your authenticator app. Recovery code also works for disable/regenerate."
              label="Verification code"
              onChange={(event) => setMfaVerificationCode(event.target.value)}
              value={mfaVerificationCode}
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <Button
                disabled={activeMutationKey === 'mfa-setup'}
                onClick={() => void handleStartMfaSetup()}
                variant="contained"
              >
                {activeMutationKey === 'mfa-setup' ? 'Preparing…' : 'Start MFA setup'}
              </Button>
              <Button
                disabled={!mfaSetup || !mfaVerificationCode.trim() || activeMutationKey === 'mfa-confirm'}
                onClick={() => void handleConfirmMfaSetup()}
                variant="outlined"
              >
                {activeMutationKey === 'mfa-confirm' ? 'Confirming…' : 'Confirm setup'}
              </Button>
            </Stack>
            <TextField
              label="Disable / recovery verification code"
              onChange={(event) => setMfaDisableCode(event.target.value)}
              value={mfaDisableCode}
            />
            <TextField
              label="Recovery code"
              onChange={(event) => setMfaDisableRecoveryCode(event.target.value)}
              value={mfaDisableRecoveryCode}
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <Button
                disabled={(!mfaDisableCode.trim() && !mfaDisableRecoveryCode.trim()) || activeMutationKey === 'mfa-recovery'}
                onClick={() => void handleRegenerateRecoveryCodes()}
                variant="outlined"
              >
                {activeMutationKey === 'mfa-recovery' ? 'Rotating…' : 'Regenerate recovery codes'}
              </Button>
              <Button
                color="warning"
                disabled={(!mfaDisableCode.trim() && !mfaDisableRecoveryCode.trim()) || activeMutationKey === 'mfa-disable'}
                onClick={() => void handleDisableMfa()}
                variant="outlined"
              >
                {activeMutationKey === 'mfa-disable' ? 'Disabling…' : 'Disable MFA'}
              </Button>
            </Stack>
          </Stack>
        </Paper>
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Invites</Typography>
            <Typography color="text.secondary" variant="body2">
              Create join links for new workspace members and revoke pending access when plans change.
            </Typography>
            {permissions && !permissions.can_manage_invites ? (
              <Alert severity="info">Only workspace owners and admins can issue or revoke invites.</Alert>
            ) : null}
            <Stack spacing={1.5}>
              <TextField
                disabled={!permissions?.can_manage_invites}
                label="Invite email"
                onChange={(event) => setInviteEmail(event.target.value)}
                value={inviteEmail}
              />
              <TextField
                disabled={!permissions?.can_manage_invites}
                label="Role"
                onChange={(event) => setInviteRole(event.target.value as OrgRoleValue)}
                select
                value={inviteRole}
              >
                <MenuItem value="owner">Owner</MenuItem>
                <MenuItem value="admin">Admin</MenuItem>
                <MenuItem value="member">Member</MenuItem>
                <MenuItem value="viewer">Viewer</MenuItem>
              </TextField>
              <TextField
                disabled={!permissions?.can_manage_invites}
                label="Expires in hours"
                onChange={(event) => setInviteExpiresInHours(event.target.value)}
                type="number"
                value={inviteExpiresInHours}
              />
              <Button
                disabled={!permissions?.can_manage_invites || !inviteEmail.trim() || activeMutationKey === 'invite-create'}
                onClick={() => void handleCreateInvite()}
                variant="contained"
              >
                {activeMutationKey === 'invite-create' ? 'Creating…' : 'Create invite'}
              </Button>
            </Stack>
            {securityOverview && securityOverview.invites.length === 0 ? (
              <EmptyState message="No recent invites exist for this workspace." />
            ) : null}
            {securityOverview && securityOverview.invites.length > 0 ? (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Email</TableCell>
                    <TableCell>Role</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Expires</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {securityOverview.invites.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.email}</TableCell>
                      <TableCell>{readableRole(item.role)}</TableCell>
                      <TableCell>{readableInviteStatus(item.status)}</TableCell>
                      <TableCell>{formatDateTime(item.expires_at)}</TableCell>
                      <TableCell align="right">
                        <Button
                          disabled={
                            !permissions?.can_manage_invites ||
                            item.status !== 'pending' ||
                            activeMutationKey === `invite-revoke:${item.id}`
                          }
                          onClick={() => void handleRevokeInvite(item.id)}
                          size="small"
                          variant="outlined"
                        >
                          {activeMutationKey === `invite-revoke:${item.id}` ? 'Revoking…' : 'Revoke'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : null}
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">SSO readiness</Typography>
            <Typography color="text.secondary" variant="body2">
              Store OIDC or SAML configuration now so enterprise SSO wiring has a clean contract later.
            </Typography>
            {permissions && !permissions.can_manage_sso ? (
              <Alert severity="info">Only workspace owners and admins can edit the SSO configuration.</Alert>
            ) : null}
            <Stack spacing={1.5}>
              <TextField
                disabled={!permissions?.can_manage_sso}
                label="Provider"
                onChange={(event) => setSsoProvider(event.target.value as AccountSsoProviderValue)}
                select
                value={ssoProvider}
              >
                {(securityOverview?.available_sso_providers || ['oidc', 'saml']).map((provider) => (
                  <MenuItem key={provider} value={provider}>
                    {provider.toUpperCase()}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                disabled={!permissions?.can_manage_sso}
                label="Status"
                onChange={(event) => setSsoEnabled(event.target.value === 'enabled')}
                select
                value={ssoEnabled ? 'enabled' : 'disabled'}
              >
                <MenuItem value="enabled">Enabled</MenuItem>
                <MenuItem value="disabled">Disabled</MenuItem>
              </TextField>
              <TextField disabled={!permissions?.can_manage_sso} label="Issuer URL" onChange={(event) => setSsoIssuerUrl(event.target.value)} value={ssoIssuerUrl} />
              <TextField disabled={!permissions?.can_manage_sso} label="Entrypoint URL" onChange={(event) => setSsoEntrypointUrl(event.target.value)} value={ssoEntrypointUrl} />
              <TextField disabled={!permissions?.can_manage_sso} label="Metadata URL" onChange={(event) => setSsoMetadataUrl(event.target.value)} value={ssoMetadataUrl} />
              <TextField disabled={!permissions?.can_manage_sso} label="Audience" onChange={(event) => setSsoAudience(event.target.value)} value={ssoAudience} />
              <TextField disabled={!permissions?.can_manage_sso} label="Client ID" onChange={(event) => setSsoClientId(event.target.value)} value={ssoClientId} />
              <TextField disabled={!permissions?.can_manage_sso} label="Client secret" onChange={(event) => setSsoClientSecret(event.target.value)} type="password" value={ssoClientSecret} />
              <TextField disabled={!permissions?.can_manage_sso} label="Scopes" onChange={(event) => setSsoScopesText(event.target.value)} value={ssoScopesText} />
              <TextField disabled={!permissions?.can_manage_sso} label="Login hint domain" onChange={(event) => setSsoLoginHintDomain(event.target.value)} value={ssoLoginHintDomain} />
              <TextField disabled={!permissions?.can_manage_sso} label="Certificate PEM" minRows={3} multiline onChange={(event) => setSsoCertificatePem(event.target.value)} value={ssoCertificatePem} />
              <TextField disabled={!permissions?.can_manage_sso} label="Attribute mapping JSON" minRows={4} multiline onChange={(event) => setSsoAttributeMappingText(event.target.value)} value={ssoAttributeMappingText} />
              <Button
                disabled={!permissions?.can_manage_sso || activeMutationKey === 'sso-save'}
                onClick={() => void handleSaveSso()}
                variant="contained"
              >
                {activeMutationKey === 'sso-save' ? 'Saving…' : 'Save SSO config'}
              </Button>
            </Stack>
            <Stack spacing={0.75}>
              {(securityOverview?.sso.readiness_checks || []).map((item) => (
                <Typography color="text.secondary" key={item} variant="body2">
                  {item}
                </Typography>
              ))}
            </Stack>
          </Stack>
        </Paper>
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
              <Box>
                <Typography variant="h6">API keys</Typography>
                <Typography color="text.secondary" variant="body2">
                  Create org-scoped keys for automation, revoke stale credentials, and rotate exposed keys.
                </Typography>
              </Box>
              <Chip icon={<KeyRounded />} label={`${controlCenter?.api_keys.length || 0} keys`} variant="outlined" />
            </Stack>

            {permissions && !permissions.can_manage_api_keys ? (
              <Alert severity="info">Only workspace owners and admins can create, revoke, or rotate API keys.</Alert>
            ) : null}

            {revealedApiKeyToken ? (
              <Alert severity="success">
                <Stack spacing={1.25}>
                  <Typography variant="subtitle2">New token for {revealedApiKeyToken.label}</Typography>
                  <TextField InputProps={{ readOnly: true }} value={revealedApiKeyToken.token} />
                </Stack>
              </Alert>
            ) : null}

            <Box className="dashboard-grid dashboard-grid--content">
              <Stack spacing={1.5}>
                <TextField
                  disabled={!permissions?.can_manage_api_keys}
                  label="Key name"
                  onChange={(event) => setApiKeyName(event.target.value)}
                  placeholder="Example: CI deployment key"
                  value={apiKeyName}
                />
                <TextField
                  disabled={!permissions?.can_manage_api_keys}
                  label="Expires in days"
                  onChange={(event) => setApiKeyExpiresInDays(event.target.value)}
                  type="number"
                  value={apiKeyExpiresInDays}
                />
                <TextField
                  disabled={!permissions?.can_manage_api_keys}
                  helperText="Comma-separated scopes."
                  label="API key scopes"
                  minRows={3}
                  multiline
                  onChange={(event) => setApiKeyScopesText(event.target.value)}
                  value={apiKeyScopesText}
                />
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  {(controlCenter?.available_api_key_scopes || []).map((scope) => (
                    <Chip
                      key={scope}
                      label={scope}
                      onClick={() => setApiKeyScopesText(appendDraftToken(apiKeyScopesText, scope))}
                      size="small"
                      variant="outlined"
                    />
                  ))}
                </Stack>
                <Button
                  disabled={!permissions?.can_manage_api_keys || !apiKeyName.trim() || activeMutationKey === 'api-key-create'}
                  onClick={() => void handleCreateApiKey()}
                  variant="contained"
                >
                  {activeMutationKey === 'api-key-create' ? 'Creating…' : 'Create API key'}
                </Button>
              </Stack>

              <Stack spacing={1.5}>
                {controlCenter && controlCenter.api_keys.length === 0 ? (
                  <EmptyState message="No API keys created yet for this workspace." />
                ) : null}

                {controlCenter && controlCenter.api_keys.length > 0 ? (
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Name</TableCell>
                        <TableCell>Prefix</TableCell>
                        <TableCell>Scopes</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Expires</TableCell>
                        <TableCell align="right">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {controlCenter.api_keys.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell>{item.name}</TableCell>
                          <TableCell>{item.key_prefix}</TableCell>
                          <TableCell>{item.scopes.join(', ')}</TableCell>
                          <TableCell>{readableApiKeyStatus(item.status)}</TableCell>
                          <TableCell>{item.expires_at ? formatDateTime(item.expires_at) : 'No expiry'}</TableCell>
                          <TableCell align="right">
                            <Stack direction="row" justifyContent="flex-end" spacing={1}>
                              <Button
                                disabled={!permissions?.can_manage_api_keys || activeMutationKey === `api-key-rotate:${item.id}`}
                                onClick={() => void handleRotateApiKey(item.id)}
                                size="small"
                                variant="text"
                              >
                                {activeMutationKey === `api-key-rotate:${item.id}` ? 'Rotating…' : 'Rotate'}
                              </Button>
                              <Button
                                disabled={!permissions?.can_manage_api_keys || item.status === 'revoked' || activeMutationKey === `api-key-revoke:${item.id}`}
                                onClick={() => void handleRevokeApiKey(item.id)}
                                size="small"
                                variant="outlined"
                              >
                                {activeMutationKey === `api-key-revoke:${item.id}` ? 'Revoking…' : 'Revoke'}
                              </Button>
                            </Stack>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : null}
              </Stack>
            </Box>
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
              <Box>
                <Typography variant="h6">Webhook endpoints</Typography>
                <Typography color="text.secondary" variant="body2">
                  Manage outbound notifications and rotate signing secrets without touching the database.
                </Typography>
              </Box>
              <Chip icon={<LinkRounded />} label={`${controlCenter?.webhooks.length || 0} endpoints`} variant="outlined" />
            </Stack>

            {permissions && !permissions.can_manage_webhooks ? (
              <Alert severity="info">Only workspace owners and admins can create or edit webhook endpoints.</Alert>
            ) : null}

            {revealedWebhookSecret ? (
              <Alert severity="success">
                <Stack spacing={1.25}>
                  <Typography variant="subtitle2">Signing secret for {revealedWebhookSecret.label}</Typography>
                  <TextField InputProps={{ readOnly: true }} value={revealedWebhookSecret.secret} />
                </Stack>
              </Alert>
            ) : null}

            <Stack spacing={1.5}>
              <TextField
                disabled={!permissions?.can_manage_webhooks}
                label="Webhook URL"
                onChange={(event) => setWebhookUrl(event.target.value)}
                placeholder="https://example.com/webhooks/neuromarketer"
                value={webhookUrl}
              />
              <TextField
                disabled={!permissions?.can_manage_webhooks}
                helperText="Comma-separated event names."
                label="Subscribed events"
                minRows={3}
                multiline
                onChange={(event) => setWebhookEventsText(event.target.value)}
                value={webhookEventsText}
              />
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                {(controlCenter?.available_webhook_events || []).map((eventName) => (
                  <Chip
                    key={eventName}
                    label={eventName}
                    onClick={() => setWebhookEventsText(appendDraftToken(webhookEventsText, eventName))}
                    size="small"
                    variant="outlined"
                  />
                ))}
              </Stack>
              <Button
                disabled={!permissions?.can_manage_webhooks || !webhookUrl.trim() || activeMutationKey === 'webhook-create'}
                onClick={() => void handleCreateWebhook()}
                variant="contained"
              >
                {activeMutationKey === 'webhook-create' ? 'Creating…' : 'Create webhook'}
              </Button>
            </Stack>

            {controlCenter && controlCenter.webhooks.length === 0 ? (
              <EmptyState message="No webhook endpoints configured yet." />
            ) : null}

            {controlCenter?.webhooks.map((webhook) => {
              const draft = webhookDrafts[webhook.id] || {
                url: webhook.url,
                eventsText: webhook.subscribed_events.join(', '),
                isActive: webhook.is_active,
              }
              return (
                <Box className="analysis-inline-summary" key={webhook.id}>
                  <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
                    <Typography variant="subtitle2">{webhook.url}</Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip label={webhook.is_active ? 'Active' : 'Paused'} size="small" variant="outlined" />
                      <Chip label={`${webhook.subscribed_events.length} events`} size="small" variant="outlined" />
                    </Stack>
                  </Stack>
                  <TextField
                    disabled={!permissions?.can_manage_webhooks}
                    label="Endpoint URL"
                    onChange={(event) =>
                      setWebhookDrafts((current) => ({
                        ...current,
                        [webhook.id]: { ...draft, url: event.target.value },
                      }))
                    }
                    value={draft.url}
                  />
                  <TextField
                    disabled={!permissions?.can_manage_webhooks}
                    helperText="Comma-separated event names."
                    label="Subscribed events"
                    minRows={3}
                    multiline
                    onChange={(event) =>
                      setWebhookDrafts((current) => ({
                        ...current,
                        [webhook.id]: { ...draft, eventsText: event.target.value },
                      }))
                    }
                    value={draft.eventsText}
                  />
                  <TextField
                    disabled={!permissions?.can_manage_webhooks}
                    label="Status"
                    onChange={(event) =>
                      setWebhookDrafts((current) => ({
                        ...current,
                        [webhook.id]: { ...draft, isActive: event.target.value === 'active' },
                      }))
                    }
                    select
                    value={draft.isActive ? 'active' : 'paused'}
                  >
                    <MenuItem value="active">Active</MenuItem>
                    <MenuItem value="paused">Paused</MenuItem>
                  </TextField>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                    <Button
                      disabled={!permissions?.can_manage_webhooks || activeMutationKey === `webhook-save:${webhook.id}`}
                      onClick={() => void handleSaveWebhook(webhook.id)}
                      variant="contained"
                    >
                      {activeMutationKey === `webhook-save:${webhook.id}` ? 'Saving…' : 'Save changes'}
                    </Button>
                    <Button
                      disabled={!permissions?.can_manage_webhooks || activeMutationKey === `webhook-rotate:${webhook.id}`}
                      onClick={() => void handleRotateWebhookSecret(webhook.id)}
                      variant="outlined"
                    >
                      {activeMutationKey === `webhook-rotate:${webhook.id}` ? 'Rotating…' : 'Rotate secret'}
                    </Button>
                  </Stack>
                </Box>
              )
            })}
          </Stack>
        </Paper>
      </Box>

      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
            <Box>
              <Typography variant="h6">Workspace members</Typography>
              <Typography color="text.secondary" variant="body2">
                Review current roles and update access without manual database changes.
              </Typography>
            </Box>
            <Chip icon={<ManageAccountsRounded />} label={`${controlCenter?.members.length || 0} members`} variant="outlined" />
          </Stack>
          {permissions && !permissions.can_manage_members ? (
            <Alert severity="info">Only workspace owners can change member roles. Members can still view current access.</Alert>
          ) : null}

          {controlCenter && controlCenter.members.length === 0 ? (
            <EmptyState message="No workspace members were found." />
          ) : null}

          {controlCenter && controlCenter.members.length > 0 ? (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Member</TableCell>
                  <TableCell>Email</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell>Joined</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {controlCenter.members.map((member) => (
                  <TableRow key={member.membership_id}>
                    <TableCell>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                        <Typography variant="body2">{member.full_name || 'Workspace member'}</Typography>
                        {member.is_current_user ? <Chip label="You" size="small" variant="outlined" /> : null}
                      </Stack>
                    </TableCell>
                    <TableCell>{member.email}</TableCell>
                    <TableCell sx={{ minWidth: 180 }}>
                      {permissions?.can_manage_members ? (
                        <TextField
                          onChange={(event) =>
                            setMemberRoleDrafts((current) => ({
                              ...current,
                              [member.membership_id]: event.target.value as OrgRoleValue,
                            }))
                          }
                          select
                          size="small"
                          value={memberRoleDrafts[member.membership_id] || member.role}
                        >
                          <MenuItem value="owner">Owner</MenuItem>
                          <MenuItem value="admin">Admin</MenuItem>
                          <MenuItem value="member">Member</MenuItem>
                          <MenuItem value="viewer">Viewer</MenuItem>
                        </TextField>
                      ) : (
                        readableRole(member.role)
                      )}
                    </TableCell>
                    <TableCell>{formatDateTime(member.joined_at)}</TableCell>
                    <TableCell align="right">
                      {permissions?.can_manage_members ? (
                        <Button
                          disabled={
                            activeMutationKey === `member-role:${member.membership_id}` ||
                            (memberRoleDrafts[member.membership_id] || member.role) === member.role
                          }
                          onClick={() => void handleSaveMemberRole(member.membership_id)}
                          size="small"
                          variant="outlined"
                        >
                          {activeMutationKey === `member-role:${member.membership_id}` ? 'Saving…' : 'Save role'}
                        </Button>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}
        </Stack>
      </Paper>

      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Typography variant="h6">Audit trail</Typography>
          <Typography color="text.secondary" variant="body2">
            Recent account-control actions, including key rotation, webhook changes, and member role updates.
          </Typography>
          {permissions && !permissions.can_view_audit_logs ? (
            <Alert severity="info">Audit history is visible to workspace owners and admins.</Alert>
          ) : null}
          {permissions?.can_view_audit_logs && controlCenter && controlCenter.audit_logs.length === 0 ? (
            <EmptyState message="No audit events have been recorded for this workspace yet." />
          ) : null}
          {permissions?.can_view_audit_logs && controlCenter && controlCenter.audit_logs.length > 0 ? (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>When</TableCell>
                  <TableCell>Actor</TableCell>
                  <TableCell>Action</TableCell>
                  <TableCell>Entity</TableCell>
                  <TableCell>Summary</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {controlCenter.audit_logs.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>{formatDateTime(entry.created_at)}</TableCell>
                    <TableCell>{entry.actor_full_name || entry.actor_email || 'System'}</TableCell>
                    <TableCell>{entry.action}</TableCell>
                    <TableCell>{entry.entity_type}</TableCell>
                    <TableCell>{summarizeAuditPayload(entry.payload_json)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : null}
        </Stack>
      </Paper>
    </Stack>
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

function EmptyState({ message }: { message: string }) {
  return (
    <Box className="analysis-empty-state">
      <Typography color="text.secondary" variant="body2">
        {message}
      </Typography>
    </Box>
  )
}

function parseCommaSeparatedList(value: string) {
  return Array.from(
    new Set(
      value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  )
}

function appendDraftToken(currentValue: string, token: string) {
  const nextValues = new Set(parseCommaSeparatedList(currentValue))
  nextValues.add(token)
  return Array.from(nextValues).join(', ')
}

function parseJsonObject(value: string) {
  const trimmed = value.trim()
  if (!trimmed) {
    return {}
  }
  const parsed = JSON.parse(trimmed) as Record<string, unknown>
  if (parsed === null || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('Attribute mapping must be a JSON object.')
  }
  return parsed
}

function formatDateTime(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

function readableRole(value: OrgRoleValue) {
  return value.replace('_', ' ')
}

function readableApiKeyStatus(value: ApiKeyStatusValue) {
  return value === 'revoked' ? 'Revoked' : 'Active'
}

function readableInviteStatus(value: AccountInviteStatusValue) {
  return value.replace('_', ' ')
}

function summarizeSessionClient(session: AccountUserSession) {
  const fragments = [session.user_agent, session.ip_address].filter(Boolean)
  return fragments.length > 0 ? fragments.join(' · ') : 'Unspecified client'
}

function buildPermissionSummary(permissions: AccountPermissions) {
  const enabled = []
  if (permissions.can_manage_api_keys) {
    enabled.push('API keys')
  }
  if (permissions.can_manage_webhooks) {
    enabled.push('Webhooks')
  }
  if (permissions.can_manage_members) {
    enabled.push('Members')
  }
  if (permissions.can_view_audit_logs) {
    enabled.push('Audit logs')
  }
  if (permissions.can_manage_invites) {
    enabled.push('Invites')
  }
  if (permissions.can_manage_sso) {
    enabled.push('SSO')
  }
  return enabled.length > 0 ? enabled.join(', ') : 'View-only'
}

function summarizeAuditPayload(payload: Record<string, unknown>) {
  const entries = Object.entries(payload)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .slice(0, 3)
  if (entries.length === 0) {
    return 'No metadata'
  }
  return entries
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join('|') : String(value)}`)
    .join(' · ')
}

export default AccountPage
