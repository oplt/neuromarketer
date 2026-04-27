import {
  Button,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import { memo, useMemo } from 'react'

import DataCard from '../../../components/layout/DataCard'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import ResponsiveTableCard from '../../../components/common/ResponsiveTableCard'
import type { AccountSecurityOverview } from '../types'
import { formatDateTime, summarizeSessionClient } from '../utils'
import { DetailRow } from './Shared'

type SessionsTableProps = {
  securityOverview: AccountSecurityOverview | null
  activeMutationKey: string | null
  onRevoke: (sessionId: string, isCurrent: boolean) => void
}

function SessionsTableBase({ securityOverview, activeMutationKey, onRevoke }: SessionsTableProps) {
  const sessions = useMemo(() => securityOverview?.sessions ?? [], [securityOverview?.sessions])
  const policy = securityOverview?.session_policy

  return (
    <DataCard
      title="Session security"
      subtitle="Active browser sessions and the workspace session policy."
      helpTooltip="Sessions are revoked immediately on Sign out. Idle and absolute TTL are enforced server-side."
    >
      <Stack spacing={2}>
        <Stack spacing={1.1}>
          <DetailRow label="Absolute TTL" value={policy ? `${policy.absolute_ttl_minutes} min` : '—'} />
          <DetailRow label="Idle timeout" value={policy ? `${policy.idle_ttl_minutes} min` : '—'} />
          <DetailRow label="Touch cadence" value={policy ? `${policy.touch_interval_seconds} s` : '—'} />
        </Stack>
        <ResponsiveTableCard
          ariaLabel="Active sessions"
          isEmpty={sessions.length === 0}
          emptyState="No active sessions are recorded for this account."
        >
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
              {sessions.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Typography variant="body2">{item.token_prefix}</Typography>
                      {item.is_current ? <Chip label="Current" size="small" variant="outlined" /> : null}
                    </Stack>
                  </TableCell>
                  <TableCell>{summarizeSessionClient(item)}</TableCell>
                  <TableCell>{formatDateTime(item.last_seen_at)}</TableCell>
                  <TableCell>
                    <Stack alignItems="center" direction="row" spacing={0.5}>
                      <Typography variant="body2">{formatDateTime(item.expires_at)}</Typography>
                      <HelpTooltip
                        title={`Idle expires at ${formatDateTime(item.idle_expires_at)}`}
                        ariaLabel="Session expiry details"
                      />
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      disabled={Boolean(item.revoked_at) || activeMutationKey === `session-revoke:${item.id}`}
                      onClick={() => onRevoke(item.id, item.is_current)}
                      size="small"
                      variant="outlined"
                    >
                      {activeMutationKey === `session-revoke:${item.id}`
                        ? 'Revoking…'
                        : item.is_current
                          ? 'Sign out'
                          : 'Revoke'}
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

export const SessionsTable = memo(SessionsTableBase)
export default SessionsTable
