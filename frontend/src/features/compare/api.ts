import { apiRequest } from '../../lib/api'
import { buildHistoryItemFromComparison } from './utils'
import type {
  AnalysisComparison,
  AnalysisComparisonHistoryItem,
  AnalysisComparisonHistoryResponse,
  AnalysisJobListItem,
  AnalysisJobListResponse,
} from './types'

type CompareCacheEntry<T> = {
  sessionToken: string
  value: T
  loadedAt: number
}

const COMPARE_CACHE_TTL_MS = 30_000

let analysesCache: CompareCacheEntry<AnalysisJobListItem[]> | null = null
let comparisonsCache: CompareCacheEntry<AnalysisComparisonHistoryItem[]> | null = null
const comparisonDetailCache = new Map<string, CompareCacheEntry<AnalysisComparison>>()
const inFlightCompareRequests = new Map<string, Promise<AnalysisComparison>>()
let inFlightAnalysesRequest: Promise<AnalysisJobListItem[]> | null = null
let inFlightComparisonsRequest: Promise<AnalysisComparisonHistoryItem[]> | null = null

function isCacheFresh(cacheEntry: CompareCacheEntry<unknown> | null, sessionToken: string) {
  return (
    cacheEntry !== null &&
    cacheEntry.sessionToken === sessionToken &&
    Date.now() - cacheEntry.loadedAt <= COMPARE_CACHE_TTL_MS
  )
}

export async function fetchCompletedAnalyses(sessionToken: string): Promise<AnalysisJobListItem[]> {
  const cachedAnalyses = analysesCache
  if (cachedAnalyses && isCacheFresh(cachedAnalyses, sessionToken)) {
    return cachedAnalyses.value
  }
  if (inFlightAnalysesRequest) {
    return inFlightAnalysesRequest
  }

  const request = apiRequest<AnalysisJobListResponse>('/api/v1/analysis/jobs?limit=24', {
    sessionToken,
  })
    .then((response) => {
      const completedItems = response.items.filter(
        (item) => item.has_result && item.job.status === 'completed',
      )
      analysesCache = {
        sessionToken,
        value: completedItems,
        loadedAt: Date.now(),
      }
      return completedItems
    })
    .finally(() => {
      inFlightAnalysesRequest = null
    })

  inFlightAnalysesRequest = request
  return request
}

export async function fetchComparisonHistory(sessionToken: string): Promise<AnalysisComparisonHistoryItem[]> {
  const cachedComparisons = comparisonsCache
  if (cachedComparisons && isCacheFresh(cachedComparisons, sessionToken)) {
    return cachedComparisons.value
  }
  if (inFlightComparisonsRequest) {
    return inFlightComparisonsRequest
  }

  const request = apiRequest<AnalysisComparisonHistoryResponse>(
    '/api/v1/analysis/comparisons?limit=12',
    { sessionToken },
  )
    .then((response) => {
      comparisonsCache = {
        sessionToken,
        value: response.items,
        loadedAt: Date.now(),
      }
      return response.items
    })
    .finally(() => {
      inFlightComparisonsRequest = null
    })

  inFlightComparisonsRequest = request
  return request
}

export async function fetchComparisonDetails(
  sessionToken: string,
  comparisonId: string,
): Promise<AnalysisComparison> {
  const cacheKey = `${sessionToken}:${comparisonId}`
  const cachedValue = comparisonDetailCache.get(cacheKey) || null
  if (cachedValue && isCacheFresh(cachedValue, sessionToken)) {
    return cachedValue.value
  }

  const inFlightRequest = inFlightCompareRequests.get(cacheKey)
  if (inFlightRequest) {
    return inFlightRequest
  }

  const request = apiRequest<AnalysisComparison>(`/api/v1/analysis/comparisons/${comparisonId}`, {
    sessionToken,
  })
    .then((response) => {
      comparisonDetailCache.set(cacheKey, {
        sessionToken,
        value: response,
        loadedAt: Date.now(),
      })
      return response
    })
    .finally(() => {
      inFlightCompareRequests.delete(cacheKey)
    })

  inFlightCompareRequests.set(cacheKey, request)
  return request
}

export function cacheComparisonHistoryEntry(sessionToken: string, comparison: AnalysisComparison) {
  const nextHistoryItem = buildHistoryItemFromComparison(comparison)
  const currentItems =
    isCacheFresh(comparisonsCache, sessionToken) && comparisonsCache !== null ? comparisonsCache.value : []
  comparisonsCache = {
    sessionToken,
    value: [nextHistoryItem, ...currentItems.filter((item) => item.id !== comparison.id)].slice(0, 12),
    loadedAt: Date.now(),
  }
}

export function cacheComparisonDetail(sessionToken: string, comparison: AnalysisComparison) {
  comparisonDetailCache.set(`${sessionToken}:${comparison.id}`, {
    sessionToken,
    value: comparison,
    loadedAt: Date.now(),
  })
}

export function __resetComparePageRequestCacheForTests() {
  analysesCache = null
  comparisonsCache = null
  comparisonDetailCache.clear()
  inFlightCompareRequests.clear()
  inFlightAnalysesRequest = null
  inFlightComparisonsRequest = null
}
