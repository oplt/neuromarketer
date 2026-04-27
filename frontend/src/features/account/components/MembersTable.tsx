import ManageAccountsRounded from '@mui/icons-material/ManageAccountsRounded'
import {
  Alert,
  Button,
  Chip,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { memo } from 'react'

import DataCard from '../../../components/layout/DataCard'
import ResponsiveTableCard from '../../../components/common/ResponsiveTableCard'
import type { AccountControlCenter, AccountPermissions, OrgRoleValue } from '../types'
import { formatDateTime, readableRole } from '../utils'

type MembersTableProps = {
  controlCenter: AccountControlCenter | null
  permissions?: AccountPermissions
  drafts: Record<string, OrgRoleValue>
  onDraftsChange: (next: (current: Record<string, OrgRoleValue>) => Record<string, OrgRoleValue>) => void
  activeMutationKey: string | null
  onSaveRole: (membershipId: string) => void
}

function MembersTableBase({
  controlCenter,
  permissions,
  drafts,
  onDraftsChange,
  activeMutationKey,
  onSaveRole,
}: MembersTableProps) {
  const members = controlCenter?.members ?? []
  const canManage = Boolean(permissions?.can_manage_members)

  return (
    <DataCard
      title="Workspace members"
      subtitle="Review current roles and update access without database changes."
      helpTooltip="Owners can change every role. Admins can manage members but not other admins."
      action={<Chip icon={<ManageAccountsRounded />} label={`${members.length} members`} variant="outlined" />}
    >
      <Stack spacing={2}>
        {!canManage ? (
          <Alert severity="info">Only workspace owners can change member roles. Members can still view current access.</Alert>
        ) : null}
        <ResponsiveTableCard
          ariaLabel="Workspace members"
          isEmpty={members.length === 0}
          emptyState="No workspace members were found."
        >
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
              {members.map((member) => (
                <TableRow key={member.membership_id}>
                  <TableCell>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Typography variant="body2">{member.full_name || 'Workspace member'}</Typography>
                      {member.is_current_user ? <Chip label="You" size="small" variant="outlined" /> : null}
                    </Stack>
                  </TableCell>
                  <TableCell>{member.email}</TableCell>
                  <TableCell sx={{ minWidth: 180 }}>
                    {canManage ? (
                      <TextField
                        onChange={(event) =>
                          onDraftsChange((current) => ({
                            ...current,
                            [member.membership_id]: event.target.value as OrgRoleValue,
                          }))
                        }
                        select
                        size="small"
                        value={drafts[member.membership_id] || member.role}
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
                    {canManage ? (
                      <Button
                        disabled={
                          activeMutationKey === `member-role:${member.membership_id}` ||
                          (drafts[member.membership_id] || member.role) === member.role
                        }
                        onClick={() => onSaveRole(member.membership_id)}
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
        </ResponsiveTableCard>
      </Stack>
    </DataCard>
  )
}

export const MembersTable = memo(MembersTableBase)
export default MembersTable
