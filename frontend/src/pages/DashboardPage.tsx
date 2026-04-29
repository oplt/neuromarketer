import { Suspense, lazy, memo, useCallback, useMemo } from 'react'
import AutoGraphRounded from '@mui/icons-material/AutoGraphRounded'
import CompareArrowsRounded from '@mui/icons-material/CompareArrowsRounded'
import HomeRounded from '@mui/icons-material/HomeRounded'
import LogoutRounded from '@mui/icons-material/LogoutRounded'
import ManageAccountsRounded from '@mui/icons-material/ManageAccountsRounded'
import SettingsRounded from '@mui/icons-material/SettingsRounded'
import {
  Avatar,
  Box,
  Button,
  Chip,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material'
import HelpTooltip from '../components/layout/HelpTooltip'
import type { AuthSession, DashboardTab } from '../lib/session'
const AccountPage = lazy(() => import('./AccountPage'))
const AnalysisPage = lazy(() => import('./AnalysisPage'))
const ComparePage = lazy(() => import('./ComparePage'))
const ProfilePage = lazy(() => import('./ProfilePage'))
const SettingsPage = lazy(() => import('./SettingsPage'))

type DashboardPageProps = {
  session: AuthSession
  activeTab: DashboardTab
  onTabChange: (tab: DashboardTab) => void
  onSignOut: () => void
}

type MenuItem = {
  id: DashboardTab
  label: string
  icon: typeof HomeRounded
  hidden?: boolean
}

const primaryMenuItems: ReadonlyArray<MenuItem> = [
  { id: 'home', label: 'Home', icon: HomeRounded },
  { id: 'analysis', label: 'Analyze', icon: AutoGraphRounded },
  { id: 'compare', label: 'Compare', icon: CompareArrowsRounded },
]

const footerMenuItems: ReadonlyArray<MenuItem> = [
  { id: 'account', label: 'Account', icon: ManageAccountsRounded },
  { id: 'settings', label: 'Settings', icon: SettingsRounded },
]

function DashboardPage({
  session,
  activeTab,
  onTabChange,
  onSignOut,
}: DashboardPageProps) {
  const visiblePrimaryItems = useMemo(() => primaryMenuItems.filter((item) => !item.hidden), [])
  const visibleFooterItems = useMemo(() => footerMenuItems.filter((item) => !item.hidden), [])

  const handleTabChange = useCallback(
    (tab: DashboardTab) => {
      onTabChange(tab)
    },
    [onTabChange],
  )

  const renderActivePage = useCallback(() => {
    if (activeTab === 'account') {
      return <AccountPage session={session} />
    }
    if (activeTab === 'profile') {
      return <ProfilePage session={session} />
    }
    if (activeTab === 'analysis') {
      return <AnalysisPage onOpenCompareWorkspace={() => handleTabChange('compare')} session={session} />
    }
    if (activeTab === 'compare') {
      return <ComparePage onOpenAnalysis={() => handleTabChange('analysis')} session={session} />
    }
    if (activeTab === 'settings') {
      return <SettingsPage session={session} />
    }
    return <HomeTab onTabChange={handleTabChange} />
  }, [activeTab, session, handleTabChange])

  return (
    <Box className="dashboard-page">
      <Box className="dashboard-shell">
        <Paper className="dashboard-sidebar" elevation={0}>
          <Stack spacing={0} sx={{ flex: 1, height: '100%', minHeight: 0, gap: 0 }}>
            <Box className="dashboard-sidebar__brand" component="header">
              <Chip
                className="dashboard-chip"
                color="primary"
                label="NEURALIS"
                size="small"
                sx={{ borderRadius: 999, fontWeight: 700 }}
              />
              <Typography className="dashboard-sidebar__brand-title" component="p" variant="subtitle2">
                Creative Ops Console
              </Typography>
            </Box>

            <Box
              aria-label="Primary navigation"
              component="nav"
              sx={{ flex: '1 1 auto', minHeight: 0, display: 'flex', overflow: 'hidden' }}
            >
              <List
                className="dashboard-sidebar__nav-scroll dashboard-sidebar__nav-list"
                disablePadding
                sx={{ py: 0.5, flex: 1, minHeight: 0, width: '100%', overflow: 'hidden' }}
              >
                {visiblePrimaryItems.map((item) => {
                  const Icon = item.icon
                  const isActive = activeTab === item.id
                  return (
                    <ListItem disablePadding key={item.id}>
                      <ListItemButton
                        aria-current={isActive ? 'page' : undefined}
                        className={`dashboard-nav-item ${isActive ? 'is-active' : ''}`}
                        onClick={() => handleTabChange(item.id)}
                      >
                        <ListItemIcon>
                          <Icon color={isActive ? 'primary' : 'inherit'} fontSize="medium" />
                        </ListItemIcon>
                        <ListItemText primary={item.label} primaryTypographyProps={{ variant: 'body1' }} />
                      </ListItemButton>
                    </ListItem>
                  )
                })}
              </List>
            </Box>

            <Box className="dashboard-sidebar__footer">
              <Box aria-label="Account and session" component="nav">
                <List className="dashboard-sidebar__nav-list" disablePadding sx={{ pb: 0.5 }}>
                  {visibleFooterItems.map((item) => {
                    const Icon = item.icon
                    const isActive = activeTab === item.id
                    return (
                      <ListItem disablePadding key={item.id}>
                        <ListItemButton
                          aria-current={isActive ? 'page' : undefined}
                          className={`dashboard-nav-item ${isActive ? 'is-active' : ''}`}
                          onClick={() => handleTabChange(item.id)}
                        >
                          <ListItemIcon>
                            <Icon color={isActive ? 'primary' : 'inherit'} fontSize="medium" />
                          </ListItemIcon>
                          <ListItemText primary={item.label} primaryTypographyProps={{ variant: 'body1' }} />
                        </ListItemButton>
                      </ListItem>
                    )
                  })}
                </List>
              </Box>
              <Button
                className="dashboard-sidebar__sign-out"
                color="inherit"
                fullWidth
                onClick={onSignOut}
                startIcon={<LogoutRounded fontSize="medium" />}
                sx={{ justifyContent: 'flex-start' }}
              >
                Sign out
              </Button>
            </Box>
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
                <Typography variant="overline">Workspace</Typography>
                <Stack alignItems="center" direction="row" spacing={0.75}>
                  <Typography variant="h4">{getDashboardTitle(activeTab)}</Typography>
                  <HelpTooltip title={getDashboardTooltip(activeTab)} />
                </Stack>
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

          <Suspense fallback={<DashboardTabFallback tab={activeTab} />}>{renderActivePage()}</Suspense>
        </Box>
      </Box>
    </Box>
  )
}

type HomeTabProps = {
  onTabChange: (tab: DashboardTab) => void
}

function HomeTabBase({ onTabChange }: HomeTabProps) {
  return (
    <Stack spacing={3}>
      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
          <Stack spacing={2.5}>
            <Typography color="primary" variant="overline">
              Start here
            </Typography>
            <Typography variant="h4">Run a pre-flight check before you spend ad budget.</Typography>
            <Typography color="text.secondary" variant="body1">
              Upload one creative or compare a few variants. The product is strongest when it helps you decide:
              ship, fix, or kill.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25}>
              <Button
                onClick={() => onTabChange('analysis')}
                size="medium"
                startIcon={<AutoGraphRounded />}
                variant="contained"
              >
                Run analysis
              </Button>
              <Button
                onClick={() => onTabChange('compare')}
                size="medium"
                startIcon={<CompareArrowsRounded />}
                variant="outlined"
              >
                Compare versions
              </Button>
            </Stack>
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Stack alignItems="center" direction="row" spacing={0.5}>
              <Typography variant="h6">No fake workspace stats</Typography>
              <HelpTooltip title="This panel stays intentionally empty until it is connected to real API-backed activity." />
            </Stack>
            <Typography color="text.secondary" variant="body2">
              Queue totals, recent wins, and calibration confidence should only appear here after they come from
              real workspace data.
            </Typography>
            <Button onClick={() => onTabChange('analysis')} startIcon={<AutoGraphRounded />} variant="outlined">
              Analyze first creative
            </Button>
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}

const HomeTab = memo(HomeTabBase)

function DashboardTabFallback({ tab }: { tab: DashboardTab }) {
  const title = getDashboardTitle(tab)
  return (
    <Stack spacing={3}>
      <Paper className="dashboard-card dashboard-card--hero" elevation={0}>
        <Stack spacing={2.5}>
          <Typography variant="h4">Preparing the {title.toLowerCase()} workspace.</Typography>
          <Skeleton animation="wave" height={24} sx={{ borderRadius: 999, maxWidth: 280 }} variant="rounded" />
          <Skeleton animation="wave" height={18} sx={{ borderRadius: 999, maxWidth: 360 }} variant="rounded" />
        </Stack>
      </Paper>

      <Box className="dashboard-grid dashboard-grid--content">
        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Skeleton animation="wave" height={28} sx={{ borderRadius: 2, maxWidth: 220 }} variant="rounded" />
            <Skeleton animation="wave" height={18} sx={{ borderRadius: 2 }} variant="rounded" />
            <Skeleton animation="wave" height={18} sx={{ borderRadius: 2, maxWidth: '82%' }} variant="rounded" />
            <Skeleton animation="wave" height={18} sx={{ borderRadius: 2, maxWidth: '68%' }} variant="rounded" />
          </Stack>
        </Paper>

        <Paper className="dashboard-card" elevation={0}>
          <Stack spacing={2}>
            <Skeleton animation="wave" height={28} sx={{ borderRadius: 2, maxWidth: 180 }} variant="rounded" />
            <Skeleton animation="wave" height={18} sx={{ borderRadius: 2 }} variant="rounded" />
            <Skeleton animation="wave" height={120} sx={{ borderRadius: 4 }} variant="rounded" />
          </Stack>
        </Paper>
      </Box>
    </Stack>
  )
}

function getDashboardTitle(tab: DashboardTab): string {
  if (tab === 'account') return 'Account'
  if (tab === 'profile') return 'Profile'
  if (tab === 'analysis') return 'Analyze'
  if (tab === 'compare') return 'Compare'
  if (tab === 'settings') return 'Settings'
  return 'Home'
}

function getDashboardTooltip(tab: DashboardTab): string {
  if (tab === 'account') return 'Workspace identity, access, and security controls.'
  if (tab === 'profile') return 'Personal account details.'
  if (tab === 'analysis') return 'Upload assets and run multimodal scoring.'
  if (tab === 'compare') return 'Rank versions and revisit comparison decisions.'
  if (tab === 'settings') return 'Workspace, model, and admin configuration.'
  return 'Live queue health and recent prediction activity.'
}

export default DashboardPage
