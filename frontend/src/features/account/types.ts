export type OrgRoleValue = 'owner' | 'admin' | 'member' | 'viewer'
export type ApiKeyStatusValue = 'active' | 'revoked'
export type AccountInviteStatusValue = 'pending' | 'accepted' | 'revoked' | 'expired'
export type AccountSsoProviderValue = 'oidc' | 'saml'

export type AccountPermissions = {
  can_manage_api_keys: boolean
  can_manage_webhooks: boolean
  can_manage_members: boolean
  can_view_audit_logs: boolean
  can_manage_invites: boolean
  can_manage_sso: boolean
}

export type AccountWorkspaceStats = {
  member_count: number
  project_count: number
  active_api_key_count: number
  active_webhook_count: number
  completed_analysis_count: number
}

export type AccountApiKey = {
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

export type AccountWebhook = {
  id: string
  url: string
  subscribed_events: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

export type AccountMember = {
  membership_id: string
  user_id: string
  email: string
  full_name?: string | null
  role: OrgRoleValue
  joined_at: string
  is_current_user: boolean
}

export type AccountAuditLog = {
  id: string
  created_at: string
  action: string
  entity_type: string
  entity_id?: string | null
  actor_email?: string | null
  actor_full_name?: string | null
  payload_json: Record<string, unknown>
}

export type AccountControlCenter = {
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

export type AccountInvite = {
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

export type AccountSessionPolicy = {
  absolute_ttl_minutes: number
  idle_ttl_minutes: number
  touch_interval_seconds: number
}

export type AccountUserSession = {
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

export type AccountMfaStatus = {
  is_enabled: boolean
  method_type?: string | null
  recovery_codes_remaining: number
  pending_setup: boolean
  last_used_at?: string | null
}

export type AccountSsoConfig = {
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

export type AccountSecurityOverview = {
  session_policy: AccountSessionPolicy
  current_session_id?: string | null
  sessions: AccountUserSession[]
  mfa: AccountMfaStatus
  invites: AccountInvite[]
  sso: AccountSsoConfig
  available_sso_providers: AccountSsoProviderValue[]
}

export type InviteCreateResponse = {
  invite: AccountInvite
  invite_token: string
  invite_url: string
}

export type MfaSetupResponse = {
  method_type: 'totp'
  secret: string
  otpauth_uri: string
  issuer: string
}

export type MfaRecoveryCodesResponse = {
  recovery_codes: string[]
  status: AccountMfaStatus
}

export type ApiKeyCreateResponse = {
  api_key: AccountApiKey
  token: string
}

export type ApiKeyRotateResponse = {
  rotated_from: AccountApiKey
  api_key: AccountApiKey
  token: string
}

export type WebhookSecretResponse = {
  webhook: AccountWebhook
  signing_secret: string
}

export type WebhookDraft = {
  url: string
  eventsText: string
  isActive: boolean
}

export type FeedbackMessage = {
  type: 'success' | 'error' | 'info'
  message: string
}

export type AccountTabId = 'overview' | 'members' | 'security' | 'api' | 'webhooks' | 'audit'
