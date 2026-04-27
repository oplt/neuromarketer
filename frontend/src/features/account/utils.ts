import type {
  AccountInviteStatusValue,
  AccountPermissions,
  AccountUserSession,
  ApiKeyStatusValue,
  OrgRoleValue,
} from './types'

export function parseCommaSeparatedList(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  )
}

export function appendDraftToken(currentValue: string, token: string): string {
  const nextValues = new Set(parseCommaSeparatedList(currentValue))
  nextValues.add(token)
  return Array.from(nextValues).join(', ')
}

export function parseJsonObject(value: string): Record<string, unknown> {
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

export function formatDateTime(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export function readableRole(value: OrgRoleValue): string {
  return value.replace('_', ' ')
}

export function readableApiKeyStatus(value: ApiKeyStatusValue): string {
  return value === 'revoked' ? 'Revoked' : 'Active'
}

export function readableInviteStatus(value: AccountInviteStatusValue): string {
  return value.replace('_', ' ')
}

export function summarizeSessionClient(session: AccountUserSession): string {
  const fragments = [session.user_agent, session.ip_address].filter(Boolean)
  return fragments.length > 0 ? fragments.join(' · ') : 'Unspecified client'
}

export function buildPermissionSummary(permissions: AccountPermissions): string {
  const enabled: string[] = []
  if (permissions.can_manage_api_keys) enabled.push('API keys')
  if (permissions.can_manage_webhooks) enabled.push('Webhooks')
  if (permissions.can_manage_members) enabled.push('Members')
  if (permissions.can_view_audit_logs) enabled.push('Audit logs')
  if (permissions.can_manage_invites) enabled.push('Invites')
  if (permissions.can_manage_sso) enabled.push('SSO')
  return enabled.length > 0 ? enabled.join(', ') : 'View-only'
}

export function summarizeAuditPayload(payload: Record<string, unknown>): string {
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
