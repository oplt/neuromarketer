import { useCallback, useEffect, useState } from 'react'
import { fetchCompletedAnalyses } from '../api'
import type { AnalysisJobListItem, CompareBanner } from '../types'

type UseComparisonCandidatesArgs = {
  sessionToken?: string
  onError: (banner: CompareBanner) => void
}

type UseComparisonCandidatesResult = {
  analysisHistory: AnalysisJobListItem[]
  isLoading: boolean
  reload: () => Promise<void>
}

export function useComparisonCandidates({
  sessionToken,
  onError,
}: UseComparisonCandidatesArgs): UseComparisonCandidatesResult {
  const [analysisHistory, setAnalysisHistory] = useState<AnalysisJobListItem[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const loadAnalyses = useCallback(async () => {
    if (!sessionToken) {
      setAnalysisHistory([])
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    try {
      const completedItems = await fetchCompletedAnalyses(sessionToken)
      setAnalysisHistory(completedItems)
    } catch (error) {
      onError({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load completed analyses.',
      })
    } finally {
      setIsLoading(false)
    }
  }, [sessionToken, onError])

  useEffect(() => {
    void loadAnalyses()
  }, [loadAnalyses])

  const reload = useCallback(async () => {
    await loadAnalyses()
  }, [loadAnalyses])

  return { analysisHistory, isLoading, reload }
}
