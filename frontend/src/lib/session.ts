export type DashboardTab = 'home' | 'account' | 'profile' | 'analysis' | 'compare' | 'settings'

export type AuthSession = {
  userId?: string
  email: string
  fullName: string
  organizationName?: string
  organizationSlug?: string
  defaultProjectId?: string
  defaultProjectName?: string
  sessionToken?: string
}

const SESSION_STORAGE_KEY = 'neuromarketer.auth.session'

export const readStoredSession = (): AuthSession | null => {
  if (typeof window === 'undefined') {
    return null
  }

  const rawValue = window.sessionStorage.getItem(SESSION_STORAGE_KEY)
  if (!rawValue) {
    return null
  }

  try {
    const parsed = JSON.parse(rawValue) as AuthSession
    if (!parsed.email) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export const storeSession = (session: AuthSession): void => {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session))
}

export const clearStoredSession = (): void => {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.removeItem(SESSION_STORAGE_KEY)
}
