import { useCallback, useEffect, useMemo, useState } from 'react'

import { apiRequest } from '../../../lib/api'
import { clearStoredSession, type AuthSession } from '../../../lib/session'
import { fetchAccountControlCenter, fetchAccountSecurityOverview } from '../api'
import {
  type AccountControlCenter,
  type AccountSecurityOverview,
  type AccountSsoProviderValue,
  type ApiKeyCreateResponse,
  type ApiKeyRotateResponse,
  type FeedbackMessage,
  type InviteCreateResponse,
  type MfaRecoveryCodesResponse,
  type MfaSetupResponse,
  type OrgRoleValue,
  type WebhookDraft,
  type WebhookSecretResponse,
} from '../types'
import {
  buildPermissionSummary,
  parseCommaSeparatedList,
  parseJsonObject,
  readableRole,
} from '../utils'

export type RevealedApiKeyToken = { label: string; token: string } | null
export type RevealedWebhookSecret = { label: string; secret: string } | null
export type RevealedInvite = { email: string; token: string; url: string } | null

export function useAccountWorkspace(session: AuthSession) {
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
  const [revealedApiKeyToken, setRevealedApiKeyToken] = useState<RevealedApiKeyToken>(null)

  const [webhookUrl, setWebhookUrl] = useState('')
  const [webhookEventsText, setWebhookEventsText] = useState('analysis.job.completed')
  const [webhookDrafts, setWebhookDrafts] = useState<Record<string, WebhookDraft>>({})
  const [revealedWebhookSecret, setRevealedWebhookSecret] = useState<RevealedWebhookSecret>(null)

  const [memberRoleDrafts, setMemberRoleDrafts] = useState<Record<string, OrgRoleValue>>({})

  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<OrgRoleValue>('viewer')
  const [inviteExpiresInHours, setInviteExpiresInHours] = useState('168')
  const [revealedInvite, setRevealedInvite] = useState<RevealedInvite>(null)

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
  const [ssoAttributeMappingText, setSsoAttributeMappingText] = useState(
    '{"email":"email","full_name":"name"}',
  )

  const loadAccountData = useCallback(
    async (force = false) => {
      if (!sessionToken) {
        setFeedbackMessage({ type: 'error', message: 'Sign in again to manage workspace controls.' })
        return
      }

      setIsLoading((current) => (force || (!controlCenter && !securityOverview) ? true : current))
      if (controlCenter && securityOverview && !force) {
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
    },
    [sessionToken, controlCenter, securityOverview],
  )

  useEffect(() => {
    void loadAccountData()
    // We only want to load on initial mount and when sessionToken changes; loadAccountData
    // depends on cached state and would otherwise loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionToken])

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
  const permissionSummary = useMemo(
    () => (permissions ? buildPermissionSummary(permissions) : 'Loading permissions…'),
    [permissions],
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
      setRevealedApiKeyToken({ label: response.api_key.name, token: response.token })
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
      await apiRequest(`/api/v1/account/api-keys/${apiKeyId}/revoke`, { method: 'POST', sessionToken })
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
      const response = await apiRequest<ApiKeyRotateResponse>(
        `/api/v1/account/api-keys/${apiKeyId}/rotate`,
        { method: 'POST', sessionToken },
      )
      setRevealedApiKeyToken({ label: response.api_key.name, token: response.token })
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
      setRevealedWebhookSecret({ label: response.webhook.url, secret: response.signing_secret })
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
      const response = await apiRequest<WebhookSecretResponse>(
        `/api/v1/account/webhooks/${webhookId}/rotate-secret`,
        { method: 'POST', sessionToken },
      )
      setRevealedWebhookSecret({ label: response.webhook.url, secret: response.signing_secret })
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
      setFeedbackMessage({
        type: 'info',
        message: 'Scan the secret in your authenticator and confirm with a code.',
      })
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
      const response = await apiRequest<MfaRecoveryCodesResponse>(
        '/api/v1/account/mfa/recovery-codes/regenerate',
        {
          method: 'POST',
          sessionToken,
          body: {
            code: mfaDisableCode.trim() || null,
            recovery_code: mfaDisableRecoveryCode.trim() || null,
          },
        },
      )
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

  return {
    sessionToken,
    sessionInfo: session,
    controlCenter,
    securityOverview,
    feedbackMessage,
    isLoading,
    isRefreshing,
    activeMutationKey,
    permissions,
    stats,
    currentUserRoleLabel,
    permissionSummary,
    refresh: () => void loadAccountData(true),

    revealedApiKeyToken,
    revealedWebhookSecret,
    revealedInvite,
    revealedRecoveryCodes,

    apiKey: {
      name: apiKeyName,
      setName: setApiKeyName,
      expiresInDays: apiKeyExpiresInDays,
      setExpiresInDays: setApiKeyExpiresInDays,
      scopesText: apiKeyScopesText,
      setScopesText: setApiKeyScopesText,
      create: handleCreateApiKey,
      revoke: handleRevokeApiKey,
      rotate: handleRotateApiKey,
    },
    webhook: {
      url: webhookUrl,
      setUrl: setWebhookUrl,
      eventsText: webhookEventsText,
      setEventsText: setWebhookEventsText,
      drafts: webhookDrafts,
      setDrafts: setWebhookDrafts,
      create: handleCreateWebhook,
      save: handleSaveWebhook,
      rotate: handleRotateWebhookSecret,
    },
    member: {
      drafts: memberRoleDrafts,
      setDrafts: setMemberRoleDrafts,
      saveRole: handleSaveMemberRole,
    },
    invite: {
      email: inviteEmail,
      setEmail: setInviteEmail,
      role: inviteRole,
      setRole: setInviteRole,
      expiresInHours: inviteExpiresInHours,
      setExpiresInHours: setInviteExpiresInHours,
      create: handleCreateInvite,
      revoke: handleRevokeInvite,
    },
    mfa: {
      setup: mfaSetup,
      verificationCode: mfaVerificationCode,
      setVerificationCode: setMfaVerificationCode,
      disableCode: mfaDisableCode,
      setDisableCode: setMfaDisableCode,
      disableRecoveryCode: mfaDisableRecoveryCode,
      setDisableRecoveryCode: setMfaDisableRecoveryCode,
      start: handleStartMfaSetup,
      confirm: handleConfirmMfaSetup,
      disable: handleDisableMfa,
      regenerateRecoveryCodes: handleRegenerateRecoveryCodes,
    },
    sso: {
      provider: ssoProvider,
      setProvider: setSsoProvider,
      enabled: ssoEnabled,
      setEnabled: setSsoEnabled,
      issuerUrl: ssoIssuerUrl,
      setIssuerUrl: setSsoIssuerUrl,
      entrypointUrl: ssoEntrypointUrl,
      setEntrypointUrl: setSsoEntrypointUrl,
      metadataUrl: ssoMetadataUrl,
      setMetadataUrl: setSsoMetadataUrl,
      audience: ssoAudience,
      setAudience: setSsoAudience,
      clientId: ssoClientId,
      setClientId: setSsoClientId,
      clientSecret: ssoClientSecret,
      setClientSecret: setSsoClientSecret,
      scopesText: ssoScopesText,
      setScopesText: setSsoScopesText,
      loginHintDomain: ssoLoginHintDomain,
      setLoginHintDomain: setSsoLoginHintDomain,
      certificatePem: ssoCertificatePem,
      setCertificatePem: setSsoCertificatePem,
      attributeMappingText: ssoAttributeMappingText,
      setAttributeMappingText: setSsoAttributeMappingText,
      save: handleSaveSso,
    },
    session: {
      revoke: handleRevokeSession,
    },
  }
}

export type AccountWorkspaceController = ReturnType<typeof useAccountWorkspace>
