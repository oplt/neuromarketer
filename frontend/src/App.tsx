import { Suspense, lazy, startTransition, useState } from 'react'
import { Box, CircularProgress, CssBaseline, Stack, ThemeProvider, Typography, createTheme } from '@mui/material'
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
        bgcolor: 'background.default',
      }}
    >
      <Stack alignItems="center" spacing={1.5}>
        <CircularProgress size={28} />
        <Typography color="text.secondary" variant="body2">
          {isSignedIn ? 'Loading workspace…' : 'Loading sign-in…'}
        </Typography>
      </Stack>
    </Box>
  )
}

export default App
