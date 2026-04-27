import { Suspense, lazy, startTransition, useState } from 'react'
import { Box, Chip, CircularProgress, CssBaseline, Paper, Stack, ThemeProvider, Typography, createTheme } from '@mui/material'
import {
  clearStoredSession,
  readStoredSession,
  storeSession,
  type AuthSession,
  type DashboardTab,
} from './lib/session'

const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const HomePage = lazy(() => import('./pages/HomePage'))

const appTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#3b5bdb',
    },
    secondary: {
      main: '#14b8a6',
    },
    background: {
      default: '#eef3fb',
      paper: '#ffffff',
    },
    text: {
      primary: '#182230',
      secondary: '#5f6b7a',
    },
  },
  shape: {
    borderRadius: 18,
  },
  typography: {
    fontFamily: '"Manrope", sans-serif',
    h1: {
      fontFamily: '"Montserrat", sans-serif',
      fontWeight: 800,
    },
    h2: {
      fontFamily: '"Montserrat", sans-serif',
      fontWeight: 800,
    },
    h3: {
      fontFamily: '"Montserrat", sans-serif',
      fontWeight: 700,
    },
    button: {
      fontWeight: 700,
      textTransform: 'none',
    },
  },
})

function App() {
  const [session, setSession] = useState<AuthSession | null>(() => readStoredSession())
  const [activeTab, setActiveTab] = useState<DashboardTab>('home')

  const handleSignedIn = (nextSession: AuthSession) => {
    storeSession(nextSession)
    startTransition(() => {
      setSession(nextSession)
      setActiveTab('home')
    })
  }

  const handleSignedOut = () => {
    const sessionToken = session?.sessionToken
    if (sessionToken) {
      void fetch('/api/v1/auth/signout', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${sessionToken}`,
        },
      }).catch(() => null)
    }
    clearStoredSession()
    startTransition(() => {
      setSession(null)
      setActiveTab('home')
    })
  }

  return (
    <ThemeProvider theme={appTheme}>
      <CssBaseline />
      <div className="app-root">
        <Suspense fallback={<AppShellFallback isSignedIn={Boolean(session)} />}>
          {session ? (
            <DashboardPage
              activeTab={activeTab}
              onSignOut={handleSignedOut}
              onTabChange={setActiveTab}
              session={session}
            />
          ) : (
            <HomePage onSignedIn={handleSignedIn} />
          )}
        </Suspense>
      </div>
    </ThemeProvider>
  )
}

function AppShellFallback({ isSignedIn }: { isSignedIn: boolean }) {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        p: 3,
        background:
          'radial-gradient(circle at top right, rgba(59, 91, 219, 0.12), transparent 26%), radial-gradient(circle at left bottom, rgba(20, 184, 166, 0.08), transparent 24%), linear-gradient(180deg, #eef3fb 0%, #e8eef8 100%)',
      }}
    >
      <Paper
        elevation={0}
        sx={{
          width: 'min(100%, 520px)',
          borderRadius: 4,
          border: '1px solid rgba(24, 34, 48, 0.08)',
          background: 'rgba(255, 255, 255, 0.9)',
          boxShadow: '0 24px 54px rgba(34, 49, 70, 0.08)',
          p: 3,
        }}
      >
        <Stack spacing={2} alignItems="flex-start">
          <Chip color="primary" label={isSignedIn ? 'Loading workspace' : 'Loading sign-in'} />
          <CircularProgress size={28} />
          <Typography variant="h5">
            {isSignedIn ? 'Preparing the creative ops console.' : 'Preparing the NeuroMarketer shell.'}
          </Typography>
          <Typography color="text.secondary" variant="body2">
            The next view is being loaded on demand so the initial bundle stays smaller.
          </Typography>
        </Stack>
      </Paper>
    </Box>
  )
}

export default App
