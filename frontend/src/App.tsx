import { startTransition, useState } from 'react'
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material'
import './App.css'
import DashboardPage from './pages/DashboardPage'
import HomePage from './pages/HomePage'
import {
  clearStoredSession,
  readStoredSession,
  storeSession,
  type AuthSession,
  type DashboardTab,
} from './lib/session'

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
      </div>
    </ThemeProvider>
  )
}

export default App
