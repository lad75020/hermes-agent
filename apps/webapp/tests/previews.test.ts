import { afterEach, expect, it, vi } from 'vitest'
import { createElement } from 'react'
import { cleanup, render, waitFor } from '@testing-library/react'
import { PreviewPane } from '../src/preview-pane'
import { createBrowserAdapter } from '../src/adapter'
import { setApiRequestConnection, setApiRequestProfile } from '@/api/client'
import { $connection } from '@/store/session'
import { upsertArtifact, artifactPreviewTarget, clearArtifactRegistry } from '@/store/artifacts'

afterEach(() => {
  cleanup(); clearArtifactRegistry(); $connection.set(null)
  setApiRequestProfile(null); setApiRequestConnection(null); vi.unstubAllGlobals()
})

it('renders backend image bytes using the real file preview component and its owner profile', async () => {
  window.hermesDesktop = createBrowserAdapter()
  $connection.set(await window.hermesDesktop.getConnection('research'))
  setApiRequestProfile('research'); setApiRequestConnection('browser')
  const fetcher = vi.fn(async () => new Response('{"dataUrl":"data:image/png;base64,aGVsbG8="}'))
  vi.stubGlobal('fetch', fetcher)
  const view = render(createElement(PreviewPane, { target: {
    kind: 'file', previewKind: 'image', label: 'image', path: '/workspace/image.png', source: '/workspace/image.png', url: 'file:///workspace/image.png'
  } }))
  await waitFor(() => expect(view.container.querySelector('img')?.getAttribute('src')).toBe('data:image/png;base64,aGVsbG8='))
  expect(fetcher.mock.calls[0][0].searchParams.get('profile')).toBe('research')
  expect(view.container.textContent).not.toContain('requires Hermes Desktop')
})

it('retains the actual artifact sandbox with scripts isolated from the app and no popup privileges', async () => {
  window.hermesDesktop = createBrowserAdapter()
  const record = upsertArtifact('fixture-session', { kind: 'html', language: 'html', title: 'Fixture' }, '<html><body>Browser artifact fixture</body></html>')!.record
  const view = render(createElement(PreviewPane, { target: artifactPreviewTarget(record) }))
  const frame = view.container.querySelector('iframe')!
  expect(frame).not.toBeNull()
  expect(frame.getAttribute('sandbox')).toBe('allow-scripts')
  expect(frame.getAttribute('srcdoc')).toContain('Browser artifact fixture')
  expect(frame.hasAttribute('allowpopups')).toBe(false)
  expect(view.container.querySelector('webview')).toBeNull()
})
