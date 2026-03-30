import { Box, Divider, LinearProgress, Paper, Stack, Typography } from '@mui/material'
import type { AuthSession } from '../lib/session'

type AccountPageProps = {
  session: AuthSession
}

function AccountPage({ session }: AccountPageProps) {
  return (
    <Box className="dashboard-grid dashboard-grid--content">
      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Typography variant="h6">Account overview</Typography>
          <Typography color="text.secondary" variant="body2">
            Keep this tab operational rather than noisy: workspace identity, billing posture, and
            platform usage belong here.
          </Typography>
          <Divider />
          <DetailRow label="Workspace" value={session.organizationName || 'Primary workspace'} />
          <DetailRow label="Plan" value="Growth preview" />
          <DetailRow label="API access" value="Ready for org-scoped keys" />
          <DetailRow label="Object storage" value="S3-compatible uploads enabled" />
        </Stack>
      </Paper>

      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Typography variant="h6">Usage posture</Typography>
          <Typography color="text.secondary" variant="body2">
            The account tab can grow into billing and enterprise controls later. For now it should
            still look like a real admin destination.
          </Typography>
          <LinearProgress sx={{ height: 10, borderRadius: 999 }} value={58} variant="determinate" />
          <DetailRow label="Prediction capacity" value="58% of monthly allocation" />
          <DetailRow label="Active projects" value="7" />
          <DetailRow label="Webhook endpoints" value="Planned next" />
        </Stack>
      </Paper>
    </Box>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack alignItems="center" direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
      <Typography sx={{ textAlign: 'right' }} variant="subtitle2">
        {value}
      </Typography>
    </Stack>
  )
}

export default AccountPage
