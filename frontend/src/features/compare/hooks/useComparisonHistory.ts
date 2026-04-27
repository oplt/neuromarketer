import { useCallback, useEffect, useState } from 'react'
import { runWhenIdle } from '../../../lib/defer'
import { fetchComparisonHistory } from '../api'
import type { AnalysisComparisonHistoryItem, CompareBanner } from '../types'

type UseComparisonHistoryArgs = {
  sessionToken?: string
  onError: (banner: CompareBanner) => void
  deferInitial?: boolean
}

type UseComparisonHistoryResult = {
  comparisonHistory: AnalysisComparisonHistoryItem[]
  isLoading: boolean
  reload: () => Promise<void>
  setComparisonHistory: React.Dispatch<React.SetStateAction<AnalysisComparisonHistoryItem[]>>
}

export function useComparisonHistory({
  sessionToken,
  onError,
  deferInitial = true,
}: UseComparisonHistoryArgs): UseComparisonHistoryResult {
  const [comparisonHistory, setComparisonHistory] = useState<AnalysisComparisonHistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const loadComparisonHistory = useCallback(async () => {
    if (!sessionToken) {
      setComparisonHistory([])
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    try {
      setComparisonHistory(await fetchComparisonHistory(sessionToken))
    } catch (error) {
      onError({
        type: 'error',
        message: error instanceof Error ? error.message : 'Unable to load compare history.',
      })
    } finally {
      setIsLoading(false)
    }
  }, [sessionToken, onError])

  useEffect(() => {
    if (deferInitial) {
      const cancelDeferredLoad = runWhenIdle(() => {
        void loadComparisonHistory()
      })
      return cancelDeferredLoad
    }
    void loadComparisonHistory()
  }, [deferInitial, loadComparisonHistory])

  const reload = useCallback(async () => {
    await loadComparisonHistory()
  }, [loadComparisonHistory])

  return { comparisonHistory, isLoading, reload, setComparisonHistory }
}
