import { afterEach, expect, it, vi } from 'vitest'
import { createBrowserAdapter } from '../src/adapter'
import { apiUrl } from '../src/transport'
import { setApiRequestConnection, setApiRequestProfile } from '@/api/client'
import { readDesktopFileDataUrl, readDesktopFileText } from '@/lib/desktop-fs'
import { pluginRest, pluginSocket } from '@/api/plugins'
import { resolveSpeakStreamUrl } from '@/lib/voice-playback'
import { resolveSiblingWsUrl } from '@/lib/sibling-ws-url'
import { $connection } from '@/store/session'
import { $keepAwakeMode, setKeepAwakeMode } from '@/store/keep-awake'
import { discoverRuntimePlugins, uninstallDiskPlugin } from '@/contrib/runtime-loader'

afterEach(() => {
  setApiRequestProfile(null); setApiRequestConnection(null); $connection.set(null)
  vi.unstubAllGlobals(); localStorage.clear()
})

it('reads backend attachment/preview paths through the actual scoped renderer filesystem helpers', async () => {
  window.hermesDesktop = createBrowserAdapter()
  $connection.set(await window.hermesDesktop.getConnection('research team'))
  setApiRequestProfile('research team'); setApiRequestConnection('browser')
  const paths: URL[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: URL) => {
    paths.push(url)
    return new Response(JSON.stringify(url.pathname.endsWith('read-text') ? { text: 'preview content', path: '/workspace/read me.md' } : { dataUrl: 'data:image/png;base64,aGVsbG8=' }))
  }))
  expect((await readDesktopFileText('/workspace/read me.md')).text).toBe('preview content')
  expect(await readDesktopFileDataUrl('/workspace/image.png')).toBe('data:image/png;base64,aGVsbG8=')
  expect(paths.map(url => url.searchParams.get('path'))).toEqual(['/workspace/read me.md', '/workspace/image.png'])
  expect(paths.every(url => url.searchParams.get('profile') === 'research team')).toBe(true)
  await window.hermesDesktop.settings.getDefaultProjectDir()
  expect(paths.at(-1)?.pathname).toBe('/api/fs/default-cwd')
  expect(paths.at(-1)?.searchParams.get('profile')).toBe('research team')
  for (const path of ['/api/%2fconfig', '/api/%2e%2e/config', '/api/plugins/../config', '/api/config#ignored']) {
    expect(() => apiUrl({ path }, location.origin)).toThrow()
  }
})

it('keeps bundled plugin REST scoped and cookie-auth plugin sockets on polling without native grants', async () => {
  window.hermesDesktop = createBrowserAdapter()
  setApiRequestProfile('research'); setApiRequestConnection('browser')
  const fetcher = vi.fn(async () => new Response('{"ok":true}'))
  const socket = vi.fn()
  vi.stubGlobal('fetch', fetcher); vi.stubGlobal('WebSocket', socket)
  const stop = pluginSocket('kanban', '/events', vi.fn())
  try {
    await expect(pluginRest('kanban', '/board')).resolves.toEqual({ ok: true })
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledOnce())
    expect(fetcher.mock.calls[0][0].pathname).toBe('/api/plugins/kanban/board')
    expect(fetcher.mock.calls[0][0].searchParams.get('profile')).toBe('research')
    expect(socket).not.toHaveBeenCalled()
    expect(window.hermesDesktop.getPluginWsUrl).toBeUndefined()
    await discoverRuntimePlugins()
    expect((await uninstallDiskPlugin('fixture-plugin')).ok).toBe(false)
  } finally { stop() }
})

it('uses a fresh public cookie ticket and explicit owner profile for voice and sibling streams', async () => {
  window.hermesDesktop = createBrowserAdapter()
  setApiRequestProfile('foreground'); setApiRequestConnection('browser')
  let serial = 0
  const fetcher = vi.fn(async () => new Response(JSON.stringify({ ticket: `public-${++serial}` })))
  vi.stubGlobal('fetch', fetcher)
  const voice = new URL((await resolveSpeakStreamUrl({ connectionId: 'browser', profile: 'tile' }))!)
  const display = new URL(await resolveSiblingWsUrl({ connectionId: 'browser', profile: 'tile' }, '/api/display/ws', { stripGatewayCredential: true }))
  expect(voice.pathname).toBe('/api/audio/speak-stream')
  expect(voice.searchParams.get('profile')).toBe('tile')
  expect(voice.searchParams.get('ticket')).toBe('public-1')
  expect(display.pathname).toBe('/api/display/ws')
  expect(display.searchParams.get('profile')).toBe('tile')
  expect(display.searchParams.has('ticket')).toBe(false)
  expect(fetcher).toHaveBeenCalledTimes(2)
  expect(voice.searchParams.has('native_dial')).toBe(false)
  await expect(resolveSiblingWsUrl({ connectionId: 'foreign', profile: 'tile' }, '/api/display/ws')).rejects.toThrow('operator')
  expect(fetcher).toHaveBeenCalledTimes(2)
})

it('denies microphone capture and power integration explicitly without requesting device access', async () => {
  const listener = vi.fn()
  window.addEventListener('hermes-capability-error', listener)
  try {
    expect(await createBrowserAdapter().requestMicrophoneAccess()).toBe(false)
    setKeepAwakeMode('always')
    expect($keepAwakeMode.get()).toBe('off')
    expect(listener).toHaveBeenCalledTimes(2)
  } finally { window.removeEventListener('hermes-capability-error', listener) }
})

it('keeps direct voice provider credentials out of the browser and uses relay fallback', async () => {
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  const direct = await import('@/lib/voice-client-direct')
  expect(await direct.directTtsConfig()).toBeNull()
  expect(await direct.fetchVoiceClientConfig()).toBeNull()
  expect(await direct.fetchVoiceClientConfigFor({ connectionId: 'browser', profile: 'research' })).toBeNull()
  expect(await direct.transcribeAudioClientDirect(new Blob(['audio']))).toBeNull()
  expect(fetcher).not.toHaveBeenCalled()
})
