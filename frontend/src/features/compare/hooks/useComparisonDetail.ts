import { useCallback, useState } from 'react'
import { fetchComparisonDetails } from '../api'
import type { AnalysisComparison, CompareBanner } from '../types'

type UseComparisonDetailArgs = {
  sessionToken?: string
  onError: (banner: CompareBanner) => void
}

type UseComparisonDetailResult = {
  activeComparison: AnalysisComparison | null
  comparisonLoadingId: string | null
  loadComparison: (comparisonId: string) => Promise<AnalysisComparison | null>
  setActiveComparison: React.Dispatch<React.SetStateAction<AnalysisComparison | null>>
}

export function useComparisonDetail({
  sessionToken,
  onError,
}: UseComparisonDetailArgs): UseComparisonDetailResult {
  const [activeComparison, setActiveComparison] = useState<AnalysisComparison | null>(null)
  const [comparisonLoadingId, setComparisonLoadingId] = useState<string | null>(null)

  const loadComparison = useCallback(
    async (comparisonId: string) => {
      if (!sessionToken) {
        return null
      }
      setComparisonLoadingId(comparisonId)
      try {
        const comparison = await fetchComparisonDetails(sessionToken, comparisonId)
        setActiveComparison(comparison)
        return comparison
      } catch (error) {
        onError({
          type: 'error',
          message: error instanceof Error ? error.message : 'Unable to load the selected comparison.',
        })
        return null
      } finally {
        setComparisonLoadingId((current) => (current === comparisonId ? null : current))
      }
    },
    [sessionToken, onError],
  )

  return {
    activeComparison,
    comparisonLoadingId,
    loadComparison,
    setActiveComparison,
  }
}
