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

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null
  }
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

export function safeReadStorageItem(storage: Storage | null, key: string): string | null {
  if (!storage) {
    return null
  }
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

export function safeWriteStorageItem(storage: Storage | null, key: string, value: string): boolean {
  if (!storage) {
    return false
  }
  try {
    storage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

export function safeRemoveStorageItem(storage: Storage | null, key: string): boolean {
  if (!storage) {
    return false
  }
  try {
    storage.removeItem(key)
    return true
  } catch {
    return false
  }
}

export const readStoredSession = (): AuthSession | null => {
  const storage = getSessionStorage()
  const rawValue = safeReadStorageItem(storage, SESSION_STORAGE_KEY)
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
  const storage = getSessionStorage()
  try {
    safeWriteStorageItem(storage, SESSION_STORAGE_KEY, JSON.stringify(session))
  } catch {
    // ignore JSON serialization or quota failures
  }
}

export const clearStoredSession = (): void => {
  const storage = getSessionStorage()
  safeRemoveStorageItem(storage, SESSION_STORAGE_KEY)
}
