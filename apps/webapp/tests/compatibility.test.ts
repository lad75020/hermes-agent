import { afterEach, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createBrowserAdapter } from '../src/adapter'
import { resolveDesktopGatewayWsUrl } from '@/lib/gateway-ws-url'
import type { PreviewTarget } from '../../desktop/src/store/preview'
import { PreviewPane } from '../src/preview-pane'

vi.mock('@/app/chat/right-rail/preview-file', () => ({
  LocalFilePreview: ({ target, reloadKey }: { target: PreviewTarget; reloadKey: number }) => createElement('p', null, `file:${target.path}:${reloadKey}`)
}))
vi.mock('@/app/chat/right-rail/preview-artifact', () => ({
  ArtifactPreview: ({ target }: { target: PreviewTarget }) => createElement('p', null, `artifact:${target.url}`)
}))
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

it('routes registry-scoped dials through the fixed backend guard before minting a ticket', async () => {
  const bridge = createBrowserAdapter()
  const fetcher = vi.fn(async () => new Response('{"ticket":"public"}'))
  vi.stubGlobal('fetch', fetcher)
  const connection = await bridge.getConnection('secondary')
  await expect(resolveDesktopGatewayWsUrl(bridge, { ...connection, connectionId: 'foreign' })).rejects.toThrow('operator')
  expect(fetcher).not.toHaveBeenCalled()
  const url = new URL(await resolveDesktopGatewayWsUrl(bridge, connection))
  expect(url.searchParams.get('profile')).toBe('secondary')
  expect(url.searchParams.get('ticket')).toBe('public')
})

it('distinguishes an explicit primary profile from a remembered selection on descriptors and dials', async () => {
  const bridge = createBrowserAdapter()
  await bridge.profile.remember('research')
  expect((await bridge.getConnection()).profile).toBe('research')
  expect((await bridge.getConnection(null)).profile).toBe('default')
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{"ticket":"public"}')))
  expect(new URL(await bridge.getGatewayWsUrl() as string).searchParams.get('profile')).toBe('research')
  expect(new URL(await bridge.getGatewayWsUrl(null) as string).searchParams.get('profile')).toBe('default')
})

it('does not let a caller mutate the single-backend registry', async () => {
  const bridge = createBrowserAdapter()
  const registry = await bridge.connections.list()
  registry.connections[0].id = 'foreign'
  registry.connections.length = 0
  expect((await bridge.connections.list()).connections.map(row => row.id)).toEqual(['browser'])
  await expect(bridge.connections.test('foreign')).rejects.toThrow('operator')
})

it('reports clipboard success using the current boolean bridge contract', async () => {
  const writeText = vi.fn(async () => {})
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  expect(await createBrowserAdapter().writeClipboard('hello')).toBe(true)
  expect(writeText).toHaveBeenCalledWith('hello')
})

it('preserves shared file and artifact previews while refusing Electron guests and unsafe links', () => {
  const base = { label: 'example', source: '/workspace/readme.md', url: 'file:///workspace/readme.md' }
  const file = renderToStaticMarkup(createElement(PreviewPane, { target: { ...base, kind: 'file', path: base.source }, reloadRequest: 3 }))
  expect(file).toContain('file:/workspace/readme.md:3')
  const artifact = renderToStaticMarkup(createElement(PreviewPane, { target: { ...base, kind: 'artifact', url: 'artifact:one' } }))
  expect(artifact).toContain('artifact:artifact:one')
  const web = renderToStaticMarkup(createElement(PreviewPane, { target: { ...base, kind: 'url', url: 'https://example.com' } }))
  expect(web).toContain('requires Hermes Desktop')
  expect(web).toContain('noopener noreferrer')
  const unsafe = renderToStaticMarkup(createElement(PreviewPane, { target: { ...base, kind: 'url', url: 'javascript:alert(1)' } }))
  expect(unsafe).not.toContain('<a')
})

it('rejects native-only attachment and export actions with a visible capability explanation', async () => {
  const bridge = createBrowserAdapter()
  const listener = vi.fn()
  window.addEventListener('hermes-capability-error', listener)
  try {
    await expect(bridge.saveTextFileAs!({ content: 'session' })).rejects.toThrow('native Desktop')
    await expect(bridge.saveClipboardImage()).rejects.toThrow('native Desktop')
    await expect(bridge.readFileDataUrlForAttach!('/private/file')).rejects.toThrow('native Desktop')
    expect(listener).toHaveBeenCalledTimes(3)
  } finally { window.removeEventListener('hermes-capability-error', listener) }
})
