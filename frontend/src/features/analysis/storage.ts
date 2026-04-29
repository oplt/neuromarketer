import type { AnalysisWizardSnapshot } from './types'

export function buildSelectedAssetStorageKey(scope: string) {
  return `neuromarketer.analysis.selected-asset.${scope}`
}

export function buildSelectedJobStorageKey(scope: string) {
  return `neuromarketer.analysis.selected-job.${scope}`
}

export function buildAnalysisWizardStorageKey(scope: string) {
  return `neuromarketer.analysis.wizard.${scope}`
}

export function readSelectedAnalysisAssetId(storageKey: string) {
  if (typeof window === 'undefined') {
    return null
  }
  return window.sessionStorage.getItem(storageKey)
}

export function readSelectedAnalysisJobId(storageKey: string) {
  if (typeof window === 'undefined') {
    return null
  }
  return window.sessionStorage.getItem(storageKey)
}

export function storeSelectedAnalysisAssetId(storageKey: string, assetId: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(storageKey, assetId)
}

export function clearSelectedAnalysisAssetId(storageKey: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.removeItem(storageKey)
}

export function storeSelectedAnalysisJobId(storageKey: string, jobId: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(storageKey, jobId)
}

export function clearSelectedAnalysisJobId(storageKey: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.removeItem(storageKey)
}

export function readAnalysisWizardSnapshot(storageKey: string): AnalysisWizardSnapshot | null {
  if (typeof window === 'undefined') {
    return null
  }

  const rawSnapshot = window.sessionStorage.getItem(storageKey)
  if (!rawSnapshot) {
    return null
  }

  try {
    const parsed = JSON.parse(rawSnapshot) as Partial<AnalysisWizardSnapshot>
    if (!parsed || typeof parsed !== 'object') {
      return null
    }
    const mediaType = parsed.mediaType
    const selectionMode = parsed.selectionMode
    if (
      (mediaType !== 'video' && mediaType !== 'audio' && mediaType !== 'text') ||
      (selectionMode !== 'auto' && selectionMode !== 'asset' && selectionMode !== 'job')
    ) {
      return null
    }

    return {
      mediaType,
      objective: typeof parsed.objective === 'string' ? parsed.objective : '',
      goalTemplate: typeof parsed.goalTemplate === 'string' ? parsed.goalTemplate : '',
      channel: typeof parsed.channel === 'string' ? parsed.channel : '',
      audienceSegment: typeof parsed.audienceSegment === 'string' ? parsed.audienceSegment : '',
      selectionMode,
    }
  } catch {
    return null
  }
}

export function storeAnalysisWizardSnapshot(storageKey: string, snapshot: AnalysisWizardSnapshot) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(storageKey, JSON.stringify(snapshot))
}
