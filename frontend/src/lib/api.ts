type ApiRequestOptions = {
  method?: string
  sessionToken?: string
  body?: BodyInit | object
  headers?: Record<string, string>
  signal?: AbortSignal
}

type DevRequestLogEntry = {
  kind: 'fetch' | 'upload' | 'stream'
  method: string
  path: string
  status: 'started' | 'succeeded' | 'failed' | 'connected' | 'closed'
  durationMs?: number
  detail?: string
  loggedAt: string
}

type EventStreamOptions<T> = {
  path: string
  sessionToken: string
  onMessage: (event: { event: string; data: T }) => void
  onError?: (error: Error) => void
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const isDevEnv = import.meta.env.DEV || import.meta.env.MODE === 'test'
const DEV_LOG_LIMIT = 200

function recordDevRequestLog(entry: DevRequestLogEntry) {
  if (!isDevEnv || typeof window === 'undefined') {
    return
  }

  const hostWindow = window as Window & {
    __NEURO_REQUEST_LOG__?: DevRequestLogEntry[]
  }
  const nextEntry: DevRequestLogEntry = {
    ...entry,
    loggedAt: entry.loggedAt || new Date().toISOString(),
  }
  const currentLog = hostWindow.__NEURO_REQUEST_LOG__ || (hostWindow.__NEURO_REQUEST_LOG__ = [])
  if (currentLog.length >= DEV_LOG_LIMIT) {
    currentLog.splice(0, currentLog.length - DEV_LOG_LIMIT + 1)
  }
  currentLog.push(nextEntry)
  const detailSuffix = nextEntry.detail ? ` · ${nextEntry.detail}` : ''
  console.debug(
    `[dev-request] ${nextEntry.kind.toUpperCase()} ${nextEntry.method} ${nextEntry.path} ${nextEntry.status}${detailSuffix}`,
    nextEntry,
  )
}

type ApiErrorBody = {
  detail?: string
  error?: {
    message?: string
  }
}

function isJsonContentType(contentType: string | null): boolean {
  if (!contentType) {
    return false
  }
  return /\bapplication\/(?:[\w.+-]+\+)?json\b/i.test(contentType)
}

async function readResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204 || response.status === 205) {
    return null
  }
  const contentLength = response.headers.get('Content-Length')
  if (contentLength === '0') {
    return null
  }
  const contentType = response.headers.get('Content-Type')
  if (!isJsonContentType(contentType)) {
    return null
  }
  try {
    const text = await response.text()
    if (!text) {
      return null
    }
    return JSON.parse(text)
  } catch {
    return null
  }
}

function buildErrorMessage(parsed: ApiErrorBody | null, status: number, fallback = 'Request failed.'): string {
  return parsed?.error?.message || parsed?.detail || `${status} ${fallback}`
}

export class ApiError extends Error {
  readonly status: number
  readonly detail?: string
  constructor(message: string, status: number, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function apiRequest<T>(
  path: string,
  { method = 'GET', sessionToken, body, headers, signal }: ApiRequestOptions = {},
): Promise<T> {
  const requestHeaders = new Headers(headers)
  const init: RequestInit = {
    method,
    headers: requestHeaders,
    signal,
  }

  if (sessionToken) {
    requestHeaders.set('Authorization', `Bearer ${sessionToken}`)
  }

  if (body !== undefined) {
    const isNativeBody =
      body instanceof FormData || body instanceof Blob || body instanceof URLSearchParams || typeof body === 'string'
    init.body = isNativeBody ? body : JSON.stringify(body)
    if (!isNativeBody && !requestHeaders.has('Content-Type')) {
      requestHeaders.set('Content-Type', 'application/json')
    }
  }

  const startedAt = performance.now()
  recordDevRequestLog({
    kind: 'fetch',
    method,
    path,
    status: 'started',
    loggedAt: new Date().toISOString(),
  })

  const response = await fetch(buildApiUrl(path), init)
  const parsedBody = (await readResponseBody(response)) as ApiErrorBody | T | null

  if (!response.ok) {
    const message = buildErrorMessage(parsedBody as ApiErrorBody | null, response.status)
    recordDevRequestLog({
      kind: 'fetch',
      method,
      path,
      status: 'failed',
      durationMs: Math.round(performance.now() - startedAt),
      detail: message,
      loggedAt: new Date().toISOString(),
    })
    throw new ApiError(message, response.status, (parsedBody as ApiErrorBody | null)?.detail)
  }

  recordDevRequestLog({
    kind: 'fetch',
    method,
    path,
    status: 'succeeded',
    durationMs: Math.round(performance.now() - startedAt),
    detail: String(response.status),
    loggedAt: new Date().toISOString(),
  })
  return parsedBody as T
}

export async function apiFetch(
  path: string,
  { method = 'GET', sessionToken, body, headers, signal }: ApiRequestOptions = {},
): Promise<Response> {
  const requestHeaders = new Headers(headers)
  const init: RequestInit = {
    method,
    headers: requestHeaders,
    signal,
  }

  if (sessionToken) {
    requestHeaders.set('Authorization', `Bearer ${sessionToken}`)
  }

  if (body !== undefined) {
    const isNativeBody =
      body instanceof FormData || body instanceof Blob || body instanceof URLSearchParams || typeof body === 'string'
    init.body = isNativeBody ? body : JSON.stringify(body)
    if (!isNativeBody && !requestHeaders.has('Content-Type')) {
      requestHeaders.set('Content-Type', 'application/json')
    }
  }

  const startedAt = performance.now()
  recordDevRequestLog({
    kind: 'fetch',
    method,
    path,
    status: 'started',
    loggedAt: new Date().toISOString(),
  })

  const response = await fetch(buildApiUrl(path), init)
  if (!response.ok) {
    const parsedBody = (await readResponseBody(response.clone())) as ApiErrorBody | null
    const message = buildErrorMessage(parsedBody, response.status)

    recordDevRequestLog({
      kind: 'fetch',
      method,
      path,
      status: 'failed',
      durationMs: Math.round(performance.now() - startedAt),
      detail: message,
      loggedAt: new Date().toISOString(),
    })
    throw new ApiError(message, response.status, parsedBody?.detail)
  }

  recordDevRequestLog({
    kind: 'fetch',
    method,
    path,
    status: 'succeeded',
    durationMs: Math.round(performance.now() - startedAt),
    detail: String(response.status),
    loggedAt: new Date().toISOString(),
  })
  return response
}

type UploadToUrlOptions = {
  file: Blob
  url: string
  contentType: string
  onProgress?: (progressPercent: number) => void
}

export function uploadToSignedUrl({
  file,
  url,
  contentType,
  onProgress,
}: UploadToUrlOptions): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    const startedAt = performance.now()
    request.open('PUT', url)
    request.setRequestHeader('Content-Type', contentType)
    recordDevRequestLog({
      kind: 'upload',
      method: 'PUT',
      path: url,
      status: 'started',
      loggedAt: new Date().toISOString(),
    })

    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        return
      }
      onProgress?.(Math.round((event.loaded / event.total) * 100))
    }

    request.onerror = () => {
      recordDevRequestLog({
        kind: 'upload',
        method: 'PUT',
        path: url,
        status: 'failed',
        durationMs: Math.round(performance.now() - startedAt),
        detail: 'Upload failed.',
        loggedAt: new Date().toISOString(),
      })
      reject(new Error('Upload failed.'))
    }
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(100)
        recordDevRequestLog({
          kind: 'upload',
          method: 'PUT',
          path: url,
          status: 'succeeded',
          durationMs: Math.round(performance.now() - startedAt),
          detail: String(request.status),
          loggedAt: new Date().toISOString(),
        })
        resolve()
        return
      }
      recordDevRequestLog({
        kind: 'upload',
        method: 'PUT',
        path: url,
        status: 'failed',
        durationMs: Math.round(performance.now() - startedAt),
        detail: `Upload failed with status ${request.status}.`,
        loggedAt: new Date().toISOString(),
      })
      reject(new Error(`Upload failed with status ${request.status}.`))
    }
    request.send(file)
  })
}

type UploadToApiOptions = {
  path: string
  sessionToken: string
  file: Blob
  fileName: string
  fields?: Record<string, string>
  onProgress?: (progressPercent: number) => void
}

export function uploadToApi<T>({
  path,
  sessionToken,
  file,
  fileName,
  fields,
  onProgress,
}: UploadToApiOptions): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    const startedAt = performance.now()
    request.open('POST', buildApiUrl(path))
    request.setRequestHeader('Authorization', `Bearer ${sessionToken}`)
    recordDevRequestLog({
      kind: 'upload',
      method: 'POST',
      path,
      status: 'started',
      loggedAt: new Date().toISOString(),
    })

    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        return
      }
      onProgress?.(Math.round((event.loaded / event.total) * 100))
    }

    request.onerror = () => {
      recordDevRequestLog({
        kind: 'upload',
        method: 'POST',
        path,
        status: 'failed',
        durationMs: Math.round(performance.now() - startedAt),
        detail: 'Backend upload failed.',
        loggedAt: new Date().toISOString(),
      })
      reject(new Error('Backend upload failed.'))
    }
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        try {
          recordDevRequestLog({
            kind: 'upload',
            method: 'POST',
            path,
            status: 'succeeded',
            durationMs: Math.round(performance.now() - startedAt),
            detail: String(request.status),
            loggedAt: new Date().toISOString(),
          })
          resolve(JSON.parse(request.responseText) as T)
        } catch {
          reject(new Error('Backend upload succeeded but returned invalid JSON.'))
        }
        return
      }

      try {
        const parsedBody = JSON.parse(request.responseText) as ApiErrorBody
        const message = buildErrorMessage(parsedBody, request.status, 'Backend upload failed.')
        recordDevRequestLog({
          kind: 'upload',
          method: 'POST',
          path,
          status: 'failed',
          durationMs: Math.round(performance.now() - startedAt),
          detail: message,
          loggedAt: new Date().toISOString(),
        })
        reject(new ApiError(message, request.status, parsedBody.detail))
      } catch {
        const message = `Backend upload failed with status ${request.status}.`
        recordDevRequestLog({
          kind: 'upload',
          method: 'POST',
          path,
          status: 'failed',
          durationMs: Math.round(performance.now() - startedAt),
          detail: message,
          loggedAt: new Date().toISOString(),
        })
        reject(new ApiError(message, request.status))
      }
    }

    const formData = new FormData()
    Object.entries(fields || {}).forEach(([key, value]) => {
      formData.append(key, value)
    })
    formData.append('file', file, fileName)
    request.send(formData)
  })
}

export function subscribeToEventStream<T>({
  path,
  sessionToken,
  onMessage,
  onError,
}: EventStreamOptions<T>): () => void {
  const controller = new AbortController()
  const startedAt = performance.now()
  let unsubscribed = false

  recordDevRequestLog({
    kind: 'stream',
    method: 'GET',
    path,
    status: 'started',
    loggedAt: new Date().toISOString(),
  })

  void (async () => {
    try {
      const response = await fetch(buildApiUrl(path), {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${sessionToken}`,
          Accept: 'text/event-stream',
        },
        signal: controller.signal,
      })

      if (!response.ok) {
        const parsedBody = (await readResponseBody(response)) as ApiErrorBody | null
        throw new ApiError(buildErrorMessage(parsedBody, response.status, 'Unable to open event stream.'), response.status)
      }

      if (!response.body) {
        throw new Error('Event stream body is unavailable.')
      }

      recordDevRequestLog({
        kind: 'stream',
        method: 'GET',
        path,
        status: 'connected',
        durationMs: Math.round(performance.now() - startedAt),
        detail: String(response.status),
        loggedAt: new Date().toISOString(),
      })

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      try {
        while (!controller.signal.aborted && !unsubscribed) {
          const { done, value } = await reader.read()
          if (done) {
            break
          }

          buffer += decoder.decode(value, { stream: true })
          const frames = buffer.split('\n\n')
          buffer = frames.pop() || ''

          for (const frame of frames) {
            try {
              const parsedEvent = parseSseFrame<T>(frame)
              if (parsedEvent) {
                onMessage(parsedEvent)
              }
            } catch (frameError) {
              // A single malformed frame must not kill the whole stream.
              if (isDevEnv) {
                console.debug('[dev-request] malformed SSE frame skipped', frameError)
              }
            }
          }
        }
      } finally {
        try {
          await reader.cancel()
        } catch {
          // ignore
        }
      }
    } catch (error) {
      if (controller.signal.aborted || unsubscribed) {
        return
      }
      recordDevRequestLog({
        kind: 'stream',
        method: 'GET',
        path,
        status: 'failed',
        durationMs: Math.round(performance.now() - startedAt),
        detail: error instanceof Error ? error.message : 'Event stream failed.',
        loggedAt: new Date().toISOString(),
      })
      onError?.(error instanceof Error ? error : new Error('Event stream failed.'))
    }
  })()

  return () => {
    if (unsubscribed) {
      return
    }
    unsubscribed = true
    recordDevRequestLog({
      kind: 'stream',
      method: 'GET',
      path,
      status: 'closed',
      durationMs: Math.round(performance.now() - startedAt),
      loggedAt: new Date().toISOString(),
    })
    controller.abort()
  }
}

function buildApiUrl(path: string) {
  if (/^https?:\/\//.test(path)) {
    return path
  }
  return `${apiBaseUrl}${path}`
}

export function parseSseFrame<T>(frame: string): { event: string; data: T } | null {
  const trimmed = frame.replace(/\r\n/g, '\n').trim()
  if (!trimmed) {
    return null
  }

  const lines = trimmed
    .split('\n')
    .map((line) => line.trimEnd())
    .filter((line) => line.length > 0)

  if (lines.length === 0 || lines.every((line) => line.startsWith(':'))) {
    return null
  }

  let eventName = 'message'
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith(':')) {
      continue
    }
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim() || 'message'
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trim())
    }
  }

  if (dataLines.length === 0) {
    return null
  }

  const payload = dataLines.join('\n')
  if (!payload) {
    return null
  }

  return {
    event: eventName,
    data: JSON.parse(payload) as T,
  }
}
