import KeyRounded from '@mui/icons-material/KeyRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
} from '@mui/material'
import { memo, useCallback } from 'react'

import DataCard from '../../../components/layout/DataCard'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import ResponsiveTableCard from '../../../components/common/ResponsiveTableCard'
import type { AccountControlCenter, AccountPermissions } from '../types'
import { appendDraftToken, formatDateTime, readableApiKeyStatus } from '../utils'

type ApiKeysPanelProps = {
  controlCenter: AccountControlCenter | null
  permissions?: AccountPermissions
  name: string
  onNameChange: (value: string) => void
  expiresInDays: string
  onExpiresInDaysChange: (value: string) => void
  scopesText: string
  onScopesTextChange: (value: string) => void
  activeMutationKey: string | null
  onCreate: () => void
  onRevoke: (apiKeyId: string) => void
  onRotate: (apiKeyId: string) => void
}

function ApiKeysPanelBase({
  controlCenter,
  permissions,
  name,
  onNameChange,
  expiresInDays,
  onExpiresInDaysChange,
  scopesText,
  onScopesTextChange,
  activeMutationKey,
  onCreate,
  onRevoke,
  onRotate,
}: ApiKeysPanelProps) {
  const canManage = Boolean(permissions?.can_manage_api_keys)
  const apiKeys = controlCenter?.api_keys ?? []
  const availableScopes = controlCenter?.available_api_key_scopes ?? []

  const handleAppendScope = useCallback(
    (scope: string) => onScopesTextChange(appendDraftToken(scopesText, scope)),
    [onScopesTextChange, scopesText],
  )

  return (
    <DataCard
      title="API keys"
      subtitle="Org-scoped tokens for automation, CI, and SDK access."
      helpTooltip="Tokens are only displayed once at creation or rotation. Restrict scopes to the minimum required."
      action={<Chip icon={<KeyRounded />} label={`${apiKeys.length} keys`} variant="outlined" />}
    >
      <Stack spacing={2}>
        {!canManage ? (
          <Alert severity="info">Only workspace owners and admins can create, revoke, or rotate API keys.</Alert>
        ) : null}

        <Box className="dashboard-grid dashboard-grid--content">
          <Stack spacing={1.5}>
            <TextField
              disabled={!canManage}
              label="Key name"
              onChange={(event) => onNameChange(event.target.value)}
              placeholder="Example: CI deployment key"
              value={name}
            />
            <TextField
              disabled={!canManage}
              label="Expires in days"
              onChange={(event) => onExpiresInDaysChange(event.target.value)}
              type="number"
              value={expiresInDays}
            />
            <TextField
              disabled={!canManage}
              helperText="Comma-separated scopes."
              label="API key scopes"
              minRows={3}
              multiline
              onChange={(event) => onScopesTextChange(event.target.value)}
              value={scopesText}
            />
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {availableScopes.map((scope) => (
                <Chip
                  key={scope}
                  label={scope}
                  onClick={() => handleAppendScope(scope)}
                  size="small"
                  variant="outlined"
                />
              ))}
            </Stack>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Button
                disabled={!canManage || !name.trim() || activeMutationKey === 'api-key-create'}
                onClick={onCreate}
                variant="contained"
              >
                {activeMutationKey === 'api-key-create' ? 'Creating…' : 'Create API key'}
              </Button>
              <HelpTooltip title="Tokens are shown once at creation. Store them in a secret manager." />
            </Stack>
          </Stack>

          <ResponsiveTableCard
            ariaLabel="API keys"
            isEmpty={apiKeys.length === 0}
            emptyState="No API keys created yet for this workspace."
          >
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
                {apiKeys.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.name}</TableCell>
                    <TableCell>{item.key_prefix}</TableCell>
                    <TableCell>{item.scopes.join(', ')}</TableCell>
                    <TableCell>{readableApiKeyStatus(item.status)}</TableCell>
                    <TableCell>{item.expires_at ? formatDateTime(item.expires_at) : 'No expiry'}</TableCell>
                    <TableCell align="right">
                      <Stack direction="row" justifyContent="flex-end" spacing={1}>
                        <Button
                          disabled={!canManage || activeMutationKey === `api-key-rotate:${item.id}`}
                          onClick={() => onRotate(item.id)}
                          size="small"
                          variant="text"
                        >
                          {activeMutationKey === `api-key-rotate:${item.id}` ? 'Rotating…' : 'Rotate'}
                        </Button>
                        <Button
                          disabled={!canManage || item.status === 'revoked' || activeMutationKey === `api-key-revoke:${item.id}`}
                          onClick={() => onRevoke(item.id)}
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
          </ResponsiveTableCard>
        </Box>
      </Stack>
    </DataCard>
  )
}

export const ApiKeysPanel = memo(ApiKeysPanelBase)
export default ApiKeysPanel
