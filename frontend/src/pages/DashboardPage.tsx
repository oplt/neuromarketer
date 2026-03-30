import AutoGraphRounded from '@mui/icons-material/AutoGraphRounded'
import BoltRounded from '@mui/icons-material/BoltRounded'
import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded'
import HomeRounded from '@mui/icons-material/HomeRounded'
import LogoutRounded from '@mui/icons-material/LogoutRounded'
import ManageAccountsRounded from '@mui/icons-material/ManageAccountsRounded'
import PersonRounded from '@mui/icons-material/PersonRounded'
import PlayCircleRounded from '@mui/icons-material/PlayCircleRounded'
import PsychologyRounded from '@mui/icons-material/PsychologyRounded'
import {
  Avatar,
  Box,
  Button,
  Chip,
  LinearProgress,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Stack,
  Typography,
} from '@mui/material'
import type { AuthSession, DashboardTab } from '../lib/session'
import AccountPage from './AccountPage'
import AnalysisPage from './AnalysisPage'
import ProfilePage from './ProfilePage'
import './dashboard-page.css'

type DashboardPageProps = {
  session: AuthSession
  activeTab: DashboardTab
  onTabChange: (tab: DashboardTab) => void
  onSignOut: () => void
}

const menuItems = [
  { id: 'home', label: 'Home', icon: HomeRounded },
  { id: 'account', label: 'Account', icon: ManageAccountsRounded },
  { id: 'profile', label: 'Profile', icon: PersonRounded },
  { id: 'analysis', label: 'Analysis', icon: AutoGraphRounded },
] as const satisfies ReadonlyArray<{
  id: DashboardTab
  label: string
  icon: typeof HomeRounded
}>

const homeMetrics = [
  {
    label: 'Creative versions under review',
    value: '18',
    detail: '6 are queued for prediction today',
    progress: 72,
    icon: PlayCircleRounded,
    tone: '#3b5bdb',
  },
  {
    label: 'Prediction jobs completed',
    value: '42',
    detail: 'Average turnaround 14 minutes',
    progress: 86,
    icon: AutoGraphRounded,
    tone: '#0f766e',
  },
  {
    label: 'Optimization opportunities',
    value: '11',
    detail: '4 CTA issues worth resolving this week',
    progress: 61,
    icon: BoltRounded,
    tone: '#f97316',
  },
]

const queueItems = [
  { name: 'Spring launch hero cut', status: 'Running', eta: '09 min', score: 'Attention +12%' },
  { name: 'Retention email narrative', status: 'Queued', eta: '14 min', score: 'Memory watch' },
  { name: 'Social proof static set', status: 'Ready', eta: 'Ready', score: 'Compare candidates' },
]

function DashboardPage({
  session,
  activeTab,
  onTabChange,
  onSignOut,
}: DashboardPageProps) {
  return (
    <Box className="dashboard-page">
      <Box className="dashboard-page__glow dashboard-page__glow--left" />
      <Box className="dashboard-page__glow dashboard-page__glow--right" />

      <Box className="dashboard-shell">
        <Paper className="dashboard-sidebar" elevation={0}>
          <Stack spacing={3}>
            <Stack spacing={1.5}>
              <Chip
                className="dashboard-chip"
                color="primary"
                label="NeuroMarketer"
                sx={{ alignSelf: 'flex-start', borderRadius: 999 }}
              />
              <Box>
                <Typography variant="h5">Creative Ops Console</Typography>
                <Typography color="text.secondary" variant="body2">
                  A lighter dashboard shell inspired by the Mantis layout language.
                </Typography>
              </Box>
            </Stack>

            <List disablePadding sx={{ display: 'grid', gap: 1 }}>
              {menuItems.map((item) => {
                const Icon = item.icon
                const isActive = activeTab === item.id
                return (
                  <ListItemButton
                    className={`dashboard-nav-item ${isActive ? 'is-active' : ''}`}
                    key={item.id}
                    onClick={() => onTabChange(item.id)}
                  >
                    <ListItemIcon>
                      <Icon color={isActive ? 'primary' : 'inherit'} />
                    </ListItemIcon>
                    <ListItemText primary={item.label} />
                  </ListItemButton>
                )
              })}
            </List>

            <Paper className="dashboard-sidebar__panel" elevation={0}>
              <Stack spacing={1.5}>
                <Typography variant="overline">Workspace focus</Typography>
                <Typography variant="h6">Pre-launch decision quality</Typography>
                <Typography color="text.secondary" variant="body2">
                  Keep attention, memory, and conversion-proxy outputs visible without exposing raw
                  model internals.
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip icon={<PsychologyRounded />} label="Interpretability" size="small" />
                  <Chip icon={<CheckCircleRounded />} label="Reliable async jobs" size="small" />
                </Stack>
              </Stack>
            </Paper>

            <Button
              color="inherit"
              onClick={onSignOut}
              startIcon={<LogoutRounded />}
              sx={{ alignSelf: 'flex-start', mt: 'auto' }}
            >
              Sign out
            </Button>
          </Stack>
        </Paper>

        <Box className="dashboard-main">
          <Paper className="dashboard-topbar" elevation={0}>
            <Stack
              alignItems={{ md: 'center' }}
              direction={{ xs: 'column', md: 'row' }}
              justifyContent="space-between"
              spacing={2}
            >
              <Box>
                <Typography variant="overline">Signed-in workspace</Typography>
                <Typography variant="h4">{getDashboardTitle(activeTab)}</Typography>
                <Typography color="text.secondary" variant="body2">
                  {getDashboardSubtitle(activeTab)}
                </Typography>
              </Box>

              <Stack alignItems="center" direction="row" spacing={1.5}>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography variant="subtitle1">{session.fullName}</Typography>
                  <Typography color="text.secondary" variant="body2">
                    {session.organizationName || session.email}
                  </Typography>
                </Box>
                <Avatar sx={{ bgcolor: 'primary.main', width: 46, height: 46 }}>
                  {session.fullName.charAt(0).toUpperCase()}
                </Avatar>
              </Stack>
            </Stack>
          </Paper>

          {renderActivePage(activeTab, session)}
        </Box>
      </Box>
    </Box>
  )
}

function HomeTab() {
  return (
    <Stack spacing={3}>
      <Box className="dashboard-grid dashboard-grid--metrics">
        {homeMetrics.map((metric) => {
          const Icon = metric.icon
          return (
            <Paper className="dashboard-card dashboard-card--metric" elevation={0} key={metric.label}>
              <Stack direction="row" justifyContent="space-between" spacing={2}>
                <Box>
                  <Typography color="text.secondary" variant="overline">
                    {metric.label}
                  </Typography>
                  <Typography variant="h3">{metric.value}</Typography>
                </Box>
                <Avatar sx={{ bgcolor: `${metric.tone}1a`, color: metric.tone }}>
                  <Icon />
                </Avatar>
              </Stack>
              <Typography color="text.secondary" variant="body2">
                {metric.detail}
              </Typography>
              <LinearProgress
                sx={{
                  height: 8,
                  borderRadius: 999,
                  bgcolor: `${metric.tone}14`,
                  '& .MuiLinearProgress-bar': { bgcolor: metric.tone },
                }}
                value={metric.progress}
                variant="determinate"
              />
            </Paper>
          )
        })}
      </Box>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
          <Stack spacing={2.5}>
            <Chip color="primary" label="Dashboard home" sx={{ alignSelf: 'flex-start' }} />
            <Typography variant="h4">See creative testing activity at a glance.</Typography>
            <Typography color="text.secondary" variant="body1">
              This home tab is meant to feel like a compact admin workspace: current jobs, account
              health, and the creative feedback loop are visible without forcing users through a
              dense navigation tree.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} useFlexGap flexWrap="wrap">
              <Chip label="Attention" />
              <Chip label="Emotion" />
              <Chip label="Memory" />
              <Chip label="Cognitive load" />
              <Chip label="Conversion proxy" />
            </Stack>
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Typography variant="h6">Active queue</Typography>
            <Stack spacing={1.5}>
              {queueItems.map((item) => (
                <Box className="queue-row" key={item.name}>
                  <Box>
                    <Typography variant="subtitle1">{item.name}</Typography>
                    <Typography color="text.secondary" variant="body2">
                      {item.score}
                    </Typography>
                  </Box>
                  <Stack alignItems="flex-end" spacing={0.5}>
                    <Chip
                      color={item.status === 'Running' ? 'primary' : item.status === 'Ready' ? 'success' : 'default'}
                      label={item.status}
                      size="small"
                    />
                    <Typography color="text.secondary" variant="caption">
                      {item.eta}
                    </Typography>
                  </Stack>
                </Box>
              ))}
            </Stack>
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}

function renderActivePage(tab: DashboardTab, session: AuthSession) {
  if (tab === 'account') {
    return <AccountPage session={session} />
  }
  if (tab === 'profile') {
    return <ProfilePage session={session} />
  }
  if (tab === 'analysis') {
    return <AnalysisPage session={session} />
  }
  return <HomeTab />
}

function getDashboardTitle(tab: DashboardTab): string {
  if (tab === 'account') {
    return 'Account'
  }
  if (tab === 'profile') {
    return 'Profile'
  }
  if (tab === 'analysis') {
    return 'Analysis'
  }
  return 'Home'
}

function getDashboardSubtitle(tab: DashboardTab): string {
  if (tab === 'account') {
    return 'Workspace identity, capacity, and platform access posture.'
  }
  if (tab === 'profile') {
    return 'Personal details and recent activity inside the workspace.'
  }
  if (tab === 'analysis') {
    return 'Upload video, audio, or text assets and stage them for multimodal review.'
  }
  return 'Creative prediction activity, queue health, and immediate operating context.'
}

export default DashboardPage
