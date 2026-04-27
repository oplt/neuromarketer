import { apiRequest } from '../../lib/api'
import type { AccountControlCenter, AccountSecurityOverview } from './types'

type AccountCacheEntry<T> = {
  sessionToken: string
  value: T
  loadedAt: number
}

const ACCOUNT_CACHE_TTL_MS = 30_000

let controlCenterCache: AccountCacheEntry<AccountControlCenter> | null = null
let inFlightControlCenterRequest: Promise<AccountControlCenter> | null = null
let securityOverviewCache: AccountCacheEntry<AccountSecurityOverview> | null = null
let inFlightSecurityOverviewRequest: Promise<AccountSecurityOverview> | null = null

function isAccountCacheFresh(cacheEntry: AccountCacheEntry<unknown> | null, sessionToken: string) {
  return (
    cacheEntry !== null &&
    cacheEntry.sessionToken === sessionToken &&
    Date.now() - cacheEntry.loadedAt <= ACCOUNT_CACHE_TTL_MS
  )
}

export async function fetchAccountControlCenter(sessionToken: string, force = false): Promise<AccountControlCenter> {
  const cachedValue = controlCenterCache
  if (!force && cachedValue && isAccountCacheFresh(cachedValue, sessionToken)) {
    return cachedValue.value
  }
  if (!force && inFlightControlCenterRequest) {
    return inFlightControlCenterRequest
  }

  const request = apiRequest<AccountControlCenter>('/api/v1/account/control-center', { sessionToken })
    .then((response) => {
      controlCenterCache = {
        sessionToken,
        value: response,
        loadedAt: Date.now(),
      }
      return response
    })
    .finally(() => {
      inFlightControlCenterRequest = null
    })

  inFlightControlCenterRequest = request
  return request
}

export async function fetchAccountSecurityOverview(
  sessionToken: string,
  force = false,
): Promise<AccountSecurityOverview> {
  const cachedValue = securityOverviewCache
  if (!force && cachedValue && isAccountCacheFresh(cachedValue, sessionToken)) {
    return cachedValue.value
  }
  if (!force && inFlightSecurityOverviewRequest) {
    return inFlightSecurityOverviewRequest
  }

  const request = apiRequest<AccountSecurityOverview>('/api/v1/account/security/overview', { sessionToken })
    .then((response) => {
      securityOverviewCache = {
        sessionToken,
        value: response,
        loadedAt: Date.now(),
      }
      return response
    })
    .finally(() => {
      inFlightSecurityOverviewRequest = null
    })

  inFlightSecurityOverviewRequest = request
  return request
}

export function __resetAccountPageRequestCacheForTests() {
  controlCenterCache = null
  inFlightControlCenterRequest = null
  securityOverviewCache = null
  inFlightSecurityOverviewRequest = null
}
