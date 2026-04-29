import { Avatar, Box, Divider, Paper, Stack, Typography } from '@mui/material'
import HelpTooltip from '../components/layout/HelpTooltip'
import type { AuthSession } from '../lib/session'

type ProfilePageProps = {
  session: AuthSession
}

function ProfilePage({ session }: ProfilePageProps) {
  return (
    <Box className="dashboard-grid dashboard-grid--content">
      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Stack alignItems="center" direction="row" spacing={2}>
            <Avatar sx={{ bgcolor: 'primary.main', width: 68, height: 68 }}>
              {session.fullName.charAt(0).toUpperCase()}
            </Avatar>
            <Box>
              <Stack alignItems="center" direction="row" spacing={0.5}>
                <Typography variant="h6">{session.fullName}</Typography>
                <HelpTooltip title="Manage your name, email, and security settings on the Account page." />
              </Stack>
              <Typography color="text.secondary" variant="body2">
                {session.email}
              </Typography>
            </Box>
          </Stack>
          <Divider />
          <DetailRow label="Default workspace" value={session.organizationName || 'Primary workspace'} />
          <DetailRow label="Profile status" value="Active" />
          <Typography color="text.secondary" variant="body2">
            Manage roles and member access from the Account page.
          </Typography>
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

export default ProfilePage
