import {
  Alert,
  Button,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
} from '@mui/material'
import { memo } from 'react'

import DataCard from '../../../components/layout/DataCard'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import ResponsiveTableCard from '../../../components/common/ResponsiveTableCard'
import type { AccountPermissions, AccountSecurityOverview, OrgRoleValue } from '../types'
import { formatDateTime, readableInviteStatus, readableRole } from '../utils'

type InvitesPanelProps = {
  securityOverview: AccountSecurityOverview | null
  permissions?: AccountPermissions
  email: string
  onEmailChange: (value: string) => void
  role: OrgRoleValue
  onRoleChange: (value: OrgRoleValue) => void
  expiresInHours: string
  onExpiresInHoursChange: (value: string) => void
  activeMutationKey: string | null
  onCreate: () => void
  onRevoke: (inviteId: string) => void
}

function InvitesPanelBase({
  securityOverview,
  permissions,
  email,
  onEmailChange,
  role,
  onRoleChange,
  expiresInHours,
  onExpiresInHoursChange,
  activeMutationKey,
  onCreate,
  onRevoke,
}: InvitesPanelProps) {
  const canManage = Boolean(permissions?.can_manage_invites)
  const invites = securityOverview?.invites ?? []

  return (
    <DataCard
      title="Invites"
      subtitle="Issue join links and revoke pending access."
      helpTooltip="Invite tokens are sent out-of-band. The link is shown once after creation."
    >
      <Stack spacing={2}>
        {!canManage ? (
          <Alert severity="info">Only workspace owners and admins can issue or revoke invites.</Alert>
        ) : null}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <TextField
            disabled={!canManage}
            fullWidth
            label="Invite email"
            onChange={(event) => onEmailChange(event.target.value)}
            value={email}
          />
          <TextField
            disabled={!canManage}
            fullWidth
            label="Role"
            onChange={(event) => onRoleChange(event.target.value as OrgRoleValue)}
            select
            value={role}
          >
            <MenuItem value="owner">Owner</MenuItem>
            <MenuItem value="admin">Admin</MenuItem>
            <MenuItem value="member">Member</MenuItem>
            <MenuItem value="viewer">Viewer</MenuItem>
          </TextField>
          <TextField
            disabled={!canManage}
            fullWidth
            label="Expires in hours"
            onChange={(event) => onExpiresInHoursChange(event.target.value)}
            type="number"
            value={expiresInHours}
          />
        </Stack>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Button
            disabled={!canManage || !email.trim() || activeMutationKey === 'invite-create'}
            onClick={onCreate}
            variant="contained"
          >
            {activeMutationKey === 'invite-create' ? 'Creating…' : 'Create invite'}
          </Button>
          <HelpTooltip title="The invite URL and token are only displayed once. Copy them before navigating away." />
        </Stack>

        <ResponsiveTableCard
          ariaLabel="Pending invites"
          isEmpty={invites.length === 0}
          emptyState="No recent invites exist for this workspace."
        >
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
              {invites.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.email}</TableCell>
                  <TableCell>{readableRole(item.role)}</TableCell>
                  <TableCell>{readableInviteStatus(item.status)}</TableCell>
                  <TableCell>{formatDateTime(item.expires_at)}</TableCell>
                  <TableCell align="right">
                    <Button
                      disabled={!canManage || item.status !== 'pending' || activeMutationKey === `invite-revoke:${item.id}`}
                      onClick={() => onRevoke(item.id)}
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
        </ResponsiveTableCard>
      </Stack>
    </DataCard>
  )
}

export const InvitesPanel = memo(InvitesPanelBase)
export default InvitesPanel
