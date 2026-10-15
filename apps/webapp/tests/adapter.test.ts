import { afterEach, expect, it, vi } from 'vitest'
import { apiUrl, browserApi, gatewayWsUrl } from '../src/transport'
import { createBrowserAdapter, safeExternalUrl } from '../src/adapter'
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })
it('rejects off-origin, normalized traversal, native routing and unknown backend paths', () => {
  for (const path of ['https://evil.invalid/api/config', '//evil.invalid/api/config', '/api/../etc/passwd', '/api/%2e%2e/etc', '/api/evil\\file']) expect(() => apiUrl({ path }, location.origin)).toThrow()
  expect(() => apiUrl({ path: '/api/config', connectionId: 'attacker' }, location.origin)).toThrow()
  const url = apiUrl({ path: '/api/config?view=full', profile: 'research team' }, location.origin)
  expect(url.searchParams.get('profile')).toBe('research team')
  expect(url.searchParams.get('view')).toBe('full')
})
it('uses browser cookies and profile scoping for HTTP reads and writes', async () => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify({ ok: true })))
  vi.stubGlobal('fetch', fetcher)
  await browserApi({ path: '/api/config', profile: 'secondary', method: 'PATCH', body: { theme: 'dark' } })
  const [url, init] = fetcher.mock.calls[0] as unknown as [URL, RequestInit]
  expect(url.searchParams.get('profile')).toBe('secondary')
  expect(init.credentials).toBe('same-origin'); expect(init.redirect).toBe('error')
  expect(new Headers(init.headers).has('Authorization')).toBe(false)
  expect(init.body).toBe('{"theme":"dark"}')
})
it('mints a new public ticket for every WebSocket dial, without native control tickets', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response('{"ticket":"first"}')).mockResolvedValueOnce(new Response('{"ticket":"second"}'))
  vi.stubGlobal('fetch', fetcher)
  const first = new URL(await gatewayWsUrl('secondary')); const second = new URL(await gatewayWsUrl())
  expect(first.searchParams.get('ticket')).toBe('first'); expect(second.searchParams.get('ticket')).toBe('second')
  expect(first.searchParams.get('profile')).toBe('secondary'); expect(first.searchParams.has('native_dial')).toBe(false)
  expect(first.host).toBe(location.host); expect(fetcher.mock.calls[0][0].pathname).toBe('/api/auth/ws-ticket')
})
it('fails closed on rejected auth and notifies the browser session owner', async () => {
  const listener = vi.fn(); window.addEventListener('hermes-auth-required', listener)
  vi.stubGlobal('fetch', vi.fn(async () => new Response('Unauthorized', { status: 401 })))
  await expect(gatewayWsUrl()).rejects.toThrow('401'); expect(listener).toHaveBeenCalledOnce()
  window.removeEventListener('hermes-auth-required', listener)
})
it('keeps descriptors credential-free and routes profiles to the same authenticated backend', async () => {
  const bridge = createBrowserAdapter()
  const descriptor = await bridge.getConnectionFor!({ connectionId: 'browser', profile: 'secondary' })
  expect(descriptor.token).toBe(''); expect(descriptor.wsUrl).not.toContain('ticket=')
  expect(descriptor.sharedRemote).toBe(true); expect(descriptor.profile).toBe('secondary')
  await expect(bridge.getConnectionFor!({ connectionId: 'other' })).rejects.toThrow()
  await expect(bridge.readFileDataUrl('/etc/passwd')).rejects.toThrow('native Desktop')
  expect(bridge.terminal).toBeUndefined(); expect(bridge.glassSupported).toBe(false)
  await bridge.profile.setDefault({ connectionId: 'browser', profile: 'secondary' })
  expect(await bridge.profile.getDefault()).toEqual({ connectionId: 'browser', profile: 'secondary' })
})
it('surfaces a filesystem permission denial without navigating away from the conversation', async () => {
  const listener = vi.fn(); window.addEventListener('hermes-auth-required', listener)
  vi.stubGlobal('fetch', vi.fn(async () => new Response('Path denied', { status: 403 })))
  await expect(browserApi({ path: '/api/fs/read?path=restricted' })).rejects.toThrow('403')
  expect(listener).not.toHaveBeenCalled()
  window.removeEventListener('hermes-auth-required', listener)
})
it('permits safe external web links only', () => {
  expect(safeExternalUrl('https://example.com/path')).toBe('https://example.com/path')
  for (const url of ['file:///etc/passwd', 'javascript:alert(1)', 'https://user:secret@example.com']) expect(() => safeExternalUrl(url)).toThrow()
})
