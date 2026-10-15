export interface ApiRequest {
  path: string
  method?: string
  body?: unknown
  profile?: string | null
  connectionId?: string | null
  timeoutMs?: number
  upload?: { filename: string; contentType?: string; bytes: ArrayBuffer }
}
export function apiUrl(request: ApiRequest, origin: string): URL {
  if (!request.path.startsWith('/api/') || /[\\\x00-\x20]/.test(request.path)) throw new Error('Only same-origin /api/ requests are supported')
  const url = new URL(request.path, origin)
  if (url.origin !== origin || !url.pathname.startsWith('/api/') || /%2e|%2f|%5c/i.test(request.path) || /^\/api\/(native|internal)/.test(url.pathname) || url.searchParams.has('native_dial') || url.searchParams.has('internal')) throw new Error('Invalid API path')
  if (request.connectionId && request.connectionId !== 'browser') throw new Error('This browser has one operator-configured backend')
  if (request.profile != null) url.searchParams.set('profile', request.profile || 'default')
  return url
}
export async function browserApi<T>(request: ApiRequest): Promise<T> {
  const url = apiUrl(request, location.origin)
  const headers = new Headers()
  let body: BodyInit | undefined
  if (request.upload) {
    const form = new FormData()
    form.append('file', new Blob([request.upload.bytes], { type: request.upload.contentType }), request.upload.filename)
    body = form
  } else if (request.body !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(request.body)
  }
  const response = await fetch(url, { method: request.method || 'GET', body, headers, credentials: 'same-origin', redirect: 'error', signal: AbortSignal.timeout(request.timeoutMs || 60000) })
  if (response.status === 401 || (response.status === 403 && url.pathname.startsWith('/api/auth/'))) window.dispatchEvent(new Event('hermes-auth-required'))
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
export async function gatewayWsUrl(profile?: string | null): Promise<string> {
  const { ticket } = await browserApi<{ ticket: string }>({ path: '/api/auth/ws-ticket', method: 'POST' })
  if (!ticket) throw new Error('Backend did not issue a public browser ticket')
  const url = new URL('/api/ws', location.origin)
  url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  url.searchParams.set('ticket', ticket)
  if (profile) url.searchParams.set('profile', profile)
  return url.toString()
}
