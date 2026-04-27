import RefreshRounded from '@mui/icons-material/RefreshRounded'
import ShieldRounded from '@mui/icons-material/ShieldRounded'
import { Box, Button, Chip, LinearProgress, Stack } from '@mui/material'
import { memo } from 'react'

import DataCard from '../../../components/layout/DataCard'
import HelpTooltip from '../../../components/layout/HelpTooltip'
import type { AuthSession } from '../../../lib/session'
import type { AccountControlCenter, AccountWorkspaceStats } from '../types'
import { DetailRow } from './Shared'

type OverviewPanelProps = {
  session: AuthSession
  controlCenter: AccountControlCenter | null
  stats?: AccountWorkspaceStats
  currentUserRoleLabel: string
  permissionSummary: string
  isLoading: boolean
  isRefreshing: boolean
  hasSessionToken: boolean
  onRefresh: () => void
}

function OverviewPanelBase({
  session,
  controlCenter,
  stats,
  currentUserRoleLabel,
  permissionSummary,
  isLoading,
  isRefreshing,
  hasSessionToken,
  onRefresh,
}: OverviewPanelProps) {
  return (
    <Box className="dashboard-grid dashboard-grid--content">
      <DataCard
        hero
        title="Workspace control center"
        subtitle="Identity, posture, and the active workspace this account manages."
        action={
          <Button
            disabled={isLoading || isRefreshing || !hasSessionToken}
            onClick={onRefresh}
            size="small"
            startIcon={<RefreshRounded />}
            variant="outlined"
          >
            Refresh
          </Button>
        }
      >
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip
              icon={<ShieldRounded />}
              label={controlCenter?.workspace_name || session.organizationName || 'Workspace'}
            />
            <Chip label={currentUserRoleLabel} variant="outlined" />
            <Chip label={controlCenter?.workspace_slug || session.organizationSlug || 'workspace'} variant="outlined" />
          </Stack>
          <Stack spacing={1.1}>
            <DetailRow label="Billing email" value={controlCenter?.billing_email || session.email} />
            <DetailRow label="Current project" value={session.defaultProjectName || 'Default Analysis Project'} />
            <DetailRow
              label="Session posture"
              value={permissionSummary}
              helpTooltip={
                <HelpTooltip title="Lists which administrative actions the current role can perform in this workspace." />
              }
            />
          </Stack>
        </Stack>
      </DataCard>

      <DataCard
        title="Usage snapshot"
        subtitle="Practical signals for operations and internal billing reviews."
      >
        <Stack spacing={1.1}>
          <DetailRow label="Members" value={stats ? String(stats.member_count) : '—'} />
          <DetailRow label="Projects" value={stats ? String(stats.project_count) : '—'} />
          <DetailRow label="Completed analyses" value={stats ? String(stats.completed_analysis_count) : '—'} />
          <DetailRow label="Active API keys" value={stats ? String(stats.active_api_key_count) : '—'} />
          <DetailRow label="Active webhooks" value={stats ? String(stats.active_webhook_count) : '—'} />
        </Stack>
        {isRefreshing ? <LinearProgress sx={{ borderRadius: 999, height: 8, mt: 1 }} /> : null}
      </DataCard>
    </Box>
  )
}

export const OverviewPanel = memo(OverviewPanelBase)
export default OverviewPanel
