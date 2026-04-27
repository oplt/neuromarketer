import { Alert, Button, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { memo } from 'react'

import AdvancedDetails from '../../../components/layout/AdvancedDetails'
import DataCard from '../../../components/layout/DataCard'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import type { AccountPermissions, AccountSecurityOverview, AccountSsoProviderValue } from '../types'

type SsoPanelProps = {
  securityOverview: AccountSecurityOverview | null
  permissions?: AccountPermissions
  provider: AccountSsoProviderValue
  onProviderChange: (value: AccountSsoProviderValue) => void
  enabled: boolean
  onEnabledChange: (value: boolean) => void
  issuerUrl: string
  onIssuerUrlChange: (value: string) => void
  entrypointUrl: string
  onEntrypointUrlChange: (value: string) => void
  metadataUrl: string
  onMetadataUrlChange: (value: string) => void
  audience: string
  onAudienceChange: (value: string) => void
  clientId: string
  onClientIdChange: (value: string) => void
  clientSecret: string
  onClientSecretChange: (value: string) => void
  scopesText: string
  onScopesTextChange: (value: string) => void
  loginHintDomain: string
  onLoginHintDomainChange: (value: string) => void
  certificatePem: string
  onCertificatePemChange: (value: string) => void
  attributeMappingText: string
  onAttributeMappingTextChange: (value: string) => void
  activeMutationKey: string | null
  onSave: () => void
}

function SsoPanelBase({
  securityOverview,
  permissions,
  provider,
  onProviderChange,
  enabled,
  onEnabledChange,
  issuerUrl,
  onIssuerUrlChange,
  entrypointUrl,
  onEntrypointUrlChange,
  metadataUrl,
  onMetadataUrlChange,
  audience,
  onAudienceChange,
  clientId,
  onClientIdChange,
  clientSecret,
  onClientSecretChange,
  scopesText,
  onScopesTextChange,
  loginHintDomain,
  onLoginHintDomainChange,
  certificatePem,
  onCertificatePemChange,
  attributeMappingText,
  onAttributeMappingTextChange,
  activeMutationKey,
  onSave,
}: SsoPanelProps) {
  const canManage = Boolean(permissions?.can_manage_sso)
  const availableProviders = securityOverview?.available_sso_providers || ['oidc', 'saml']

  return (
    <DataCard
      title="SSO readiness"
      subtitle="Store OIDC or SAML configuration so enterprise rollout is unblocked."
      helpTooltip="Configuration is validated server-side. Client secrets are never returned after they are stored."
    >
      <Stack spacing={2}>
        {!canManage ? (
          <Alert severity="info">Only workspace owners and admins can edit the SSO configuration.</Alert>
        ) : null}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <TextField
            disabled={!canManage}
            fullWidth
            label="Provider"
            onChange={(event) => onProviderChange(event.target.value as AccountSsoProviderValue)}
            select
            value={provider}
          >
            {availableProviders.map((entry) => (
              <MenuItem key={entry} value={entry}>
                {entry.toUpperCase()}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            disabled={!canManage}
            fullWidth
            label="Status"
            onChange={(event) => onEnabledChange(event.target.value === 'enabled')}
            select
            value={enabled ? 'enabled' : 'disabled'}
          >
            <MenuItem value="enabled">Enabled</MenuItem>
            <MenuItem value="disabled">Disabled</MenuItem>
          </TextField>
        </Stack>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <TextField
            disabled={!canManage}
            fullWidth
            label="Client ID"
            onChange={(event) => onClientIdChange(event.target.value)}
            value={clientId}
          />
          <TextField
            disabled={!canManage}
            fullWidth
            label="Client secret"
            onChange={(event) => onClientSecretChange(event.target.value)}
            type="password"
            value={clientSecret}
            helperText="Leave empty to keep the existing secret."
          />
        </Stack>
        <TextField
          disabled={!canManage}
          fullWidth
          label="Issuer URL"
          onChange={(event) => onIssuerUrlChange(event.target.value)}
          value={issuerUrl}
        />
        <TextField
          disabled={!canManage}
          fullWidth
          label="Login hint domain"
          onChange={(event) => onLoginHintDomainChange(event.target.value)}
          value={loginHintDomain}
        />

        <AdvancedDetails
          title="Endpoint and certificate details"
          description="Optional fields used by SAML / OIDC enterprise rollouts."
          variant="caution"
        >
          <Stack spacing={1.5}>
            <TextField
              disabled={!canManage}
              fullWidth
              label="Entrypoint URL"
              onChange={(event) => onEntrypointUrlChange(event.target.value)}
              value={entrypointUrl}
            />
            <TextField
              disabled={!canManage}
              fullWidth
              label="Metadata URL"
              onChange={(event) => onMetadataUrlChange(event.target.value)}
              value={metadataUrl}
            />
            <TextField
              disabled={!canManage}
              fullWidth
              label="Audience"
              onChange={(event) => onAudienceChange(event.target.value)}
              value={audience}
            />
            <TextField
              disabled={!canManage}
              fullWidth
              label="Scopes"
              onChange={(event) => onScopesTextChange(event.target.value)}
              value={scopesText}
              helperText="Comma-separated scopes."
            />
            <TextField
              disabled={!canManage}
              fullWidth
              label="Certificate PEM"
              minRows={3}
              multiline
              onChange={(event) => onCertificatePemChange(event.target.value)}
              value={certificatePem}
            />
            <TextField
              disabled={!canManage}
              fullWidth
              label="Attribute mapping JSON"
              minRows={4}
              multiline
              onChange={(event) => onAttributeMappingTextChange(event.target.value)}
              value={attributeMappingText}
            />
          </Stack>
        </AdvancedDetails>

        <Stack direction="row" alignItems="center" spacing={1}>
          <Button
            disabled={!canManage || activeMutationKey === 'sso-save'}
            onClick={onSave}
            variant="contained"
          >
            {activeMutationKey === 'sso-save' ? 'Saving…' : 'Save SSO config'}
          </Button>
          <HelpTooltip title="Saves provider type, status, scopes, and any optional endpoint metadata. Client secret is only updated when a new value is provided." />
        </Stack>

        {(securityOverview?.sso.readiness_checks || []).length > 0 ? (
          <Stack spacing={0.5}>
            <Typography color="text.secondary" variant="overline">
              Readiness checks
            </Typography>
            {(securityOverview?.sso.readiness_checks || []).map((item) => (
              <Typography color="text.secondary" key={item} variant="body2">
                {item}
              </Typography>
            ))}
          </Stack>
        ) : null}
      </Stack>
    </DataCard>
  )
}

export const SsoPanel = memo(SsoPanelBase)
export default SsoPanel
