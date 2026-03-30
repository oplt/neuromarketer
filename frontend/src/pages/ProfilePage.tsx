import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded'
import { Avatar, Box, Divider, Paper, Stack, Typography } from '@mui/material'
import type { AuthSession } from '../lib/session'

const profileActivity = [
  'Updated profile details and workspace presentation settings',
  'Reviewed three prediction jobs this morning',
  'Opened compare flow for the spring launch set',
]

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
              <Typography variant="h6">{session.fullName}</Typography>
              <Typography color="text.secondary" variant="body2">
                {session.email}
              </Typography>
            </Box>
          </Stack>
          <Divider />
          <DetailRow label="Role" value="Owner" />
          <DetailRow label="Default workspace" value={session.organizationName || 'Primary workspace'} />
          <DetailRow label="Profile status" value="Active" />
        </Stack>
      </Paper>

      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Typography variant="h6">Recent activity</Typography>
          <Stack spacing={1.25}>
            {profileActivity.map((item) => (
              <Box className="activity-row" key={item}>
                <CheckCircleRounded color="primary" fontSize="small" />
                <Typography color="text.secondary" variant="body2">
                  {item}
                </Typography>
              </Box>
            ))}
          </Stack>
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
