import {
  Alert,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from '@mui/material'
import { memo } from 'react'

import DataCard from '../../../components/layout/DataCard'
import ResponsiveTableCard from '../../../components/common/ResponsiveTableCard'
import type { AccountControlCenter, AccountPermissions } from '../types'
import { formatDateTime, summarizeAuditPayload } from '../utils'

type AuditLogTableProps = {
  controlCenter: AccountControlCenter | null
  permissions?: AccountPermissions
}

function AuditLogTableBase({ controlCenter, permissions }: AuditLogTableProps) {
  const canView = Boolean(permissions?.can_view_audit_logs)
  const auditLogs = controlCenter?.audit_logs ?? []

  return (
    <DataCard
      title="Audit trail"
      subtitle="Recent administrative changes for this workspace."
      helpTooltip="Logs key rotations, webhook updates, member role changes, and SSO edits. Use the export from your data warehouse for retention beyond the UI window."
    >
      <Stack spacing={2}>
        {!canView ? (
          <Alert severity="info">Audit history is visible to workspace owners and admins.</Alert>
        ) : null}
        {canView ? (
          <ResponsiveTableCard
            ariaLabel="Audit trail"
            isEmpty={auditLogs.length === 0}
            emptyState="No audit events have been recorded for this workspace yet."
            maxHeight={520}
          >
            <Table size="small" stickyHeader>
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
                {auditLogs.map((entry) => (
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
          </ResponsiveTableCard>
        ) : null}
      </Stack>
    </DataCard>
  )
}

export const AuditLogTable = memo(AuditLogTableBase)
export default AuditLogTable
