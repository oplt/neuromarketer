export function runWhenIdle(task: () => void, timeoutMs = 250): () => void {
  if (typeof window === 'undefined') {
    task()
    return () => {}
  }

  const idleWindow = window as Window & {
    requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number
    cancelIdleCallback?: (handle: number) => void
  }

  if (typeof idleWindow.requestIdleCallback === 'function') {
    const handle = idleWindow.requestIdleCallback(task, { timeout: timeoutMs })
    return () => idleWindow.cancelIdleCallback?.(handle)
  }

  const timeoutId = window.setTimeout(task, 0)
  return () => window.clearTimeout(timeoutId)
}
