type ApiRequestOptions = {
  method?: string
  sessionToken?: string
  body?: BodyInit | object
  headers?: Record<string, string>
  signal?: AbortSignal
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

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

  const response = await fetch(buildApiUrl(path), init)
  const parsedBody = (await response.json().catch(() => null)) as
    | {
        detail?: string
        error?: {
          message?: string
        }
      }
    | null

  if (!response.ok) {
    throw new Error(parsedBody?.error?.message || parsedBody?.detail || 'Request failed.')
  }

  return parsedBody as T
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
    request.open('PUT', url)
    request.setRequestHeader('Content-Type', contentType)

    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        return
      }
      onProgress?.(Math.round((event.loaded / event.total) * 100))
    }

    request.onerror = () => reject(new Error('Upload failed.'))
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(100)
        resolve()
        return
      }
      reject(new Error(`Upload failed with status ${request.status}.`))
    }
    request.send(file)
  })
}

function buildApiUrl(path: string) {
  if (/^https?:\/\//.test(path)) {
    return path
  }
  return `${apiBaseUrl}${path}`
}
