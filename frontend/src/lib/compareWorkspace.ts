export type CompareWorkspaceSnapshot = {
  selectedJobIds: string[]
  baselineJobId: string | null
  activeComparisonId: string | null
}

const defaultSnapshot: CompareWorkspaceSnapshot = {
  selectedJobIds: [],
  baselineJobId: null,
  activeComparisonId: null,
}

export function buildCompareWorkspaceStorageKey(scope: string) {
  return `neuromarketer.compare.workspace.${scope}`
}

export function readCompareWorkspaceSnapshot(storageKey: string): CompareWorkspaceSnapshot {
  if (typeof window === 'undefined') {
    return defaultSnapshot
  }

  const rawValue = window.sessionStorage.getItem(storageKey)
  if (!rawValue) {
    return defaultSnapshot
  }

  try {
    const parsed = JSON.parse(rawValue) as Partial<CompareWorkspaceSnapshot>
    const selectedJobIds = Array.isArray(parsed.selectedJobIds)
      ? parsed.selectedJobIds.filter((value): value is string => typeof value === 'string' && value.length > 0)
      : []
    const baselineJobId = typeof parsed.baselineJobId === 'string' && parsed.baselineJobId ? parsed.baselineJobId : null
    const activeComparisonId =
      typeof parsed.activeComparisonId === 'string' && parsed.activeComparisonId ? parsed.activeComparisonId : null
    return {
      selectedJobIds,
      baselineJobId,
      activeComparisonId,
    }
  } catch {
    return defaultSnapshot
  }
}

export function storeCompareWorkspaceSnapshot(storageKey: string, snapshot: CompareWorkspaceSnapshot) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(storageKey, JSON.stringify(snapshot))
}
