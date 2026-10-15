import { expect, it, vi } from 'vitest'
// @ts-expect-error Node-only harness helper intentionally uses ESM JavaScript.
import { asgiClient } from './asgi-client.mjs'
import { createBrowserAdapter } from '../src/adapter'
import { writeFile } from 'node:fs/promises'
const mounted = vi.hoisted(() => ({ root: null as { unmount(): void } | null }))
vi.mock('react-dom/client', async importOriginal => {
  const actual = await importOriginal<typeof import('react-dom/client')>()
  return { ...actual, createRoot: (...args: Parameters<typeof actual.createRoot>) => {
    mounted.root = actual.createRoot(...args)
    return mounted.root
  } }
})
it('mounts the actual Desktop renderer through the browser adapter against real Hermes ASGI handlers', async () => {
  const backend = await asgiClient('renderer')
  const errors: string[] = []
  const handler = (event: ErrorEvent) => { errors.push(event.message) }
  window.addEventListener('error', handler)
  vi.stubGlobal('fetch', async (input: URL | string, init: RequestInit = {}) => {
    const url = new URL(String(input), location.origin)
    const response = await backend.call({ path: url.pathname + url.search, method: init.method || 'GET', headers: Object.fromEntries(new Headers(init.headers).entries()), body: typeof init.body === 'string' ? init.body : '' })
    if (url.pathname.endsWith('/sidebar')) await writeFile(`${process.cwd().endsWith('/apps/webapp') ? '' : 'apps/webapp/'}.scratch/sidebar-response.json`, response.body)
    return new Response(response.body, { status: response.status, headers: Object.fromEntries(response.headers) })
  })
  class AsgiSocket extends EventTarget {
    static OPEN = 1
    static CLOSED = 3
    readyState = 0; bufferedAmount = 0; id = 0
    constructor(url: string) {
      super()
      const parsed = new URL(url)
      void backend.call({ op: 'ws-open', path: parsed.pathname + parsed.search }).then((result: { id: number }) => {
        this.id = result.id; this.readyState = 1
        this.dispatchEvent(new Event('open'))
        backend.subscribe(this.id, (frame: { data?: string; closed?: string }) => {
          if (frame.data && this.readyState === 1) this.dispatchEvent(new MessageEvent('message', { data: frame.data }))
        })
      }).catch((error: Error) => { errors.push(error.message); this.dispatchEvent(new Event('error')) })
    }
    send(data: string) { backend.send({ op: 'ws-send', socket: this.id, data }) }
    close() { if (this.id && this.readyState === 1) backend.send({ op: 'ws-close', socket: this.id }); this.readyState = 3; this.dispatchEvent(new CloseEvent('close')) }
  }
  vi.stubGlobal('WebSocket', AsgiSocket)
  try {
    await backend.call({ path: '/auth/password-login', method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ provider: 'basic', username: 'webapp-test', password: 'isolated-browser-smoke-only' }) })
    document.body.innerHTML = '<div id="root"></div>'
    window.hermesDesktop = createBrowserAdapter()
    await import('../../desktop/src/main')
    await new Promise(resolve => setTimeout(resolve, 4000))
    const later = Array.from(document.querySelectorAll('button')).find(button => button.textContent?.includes("I'll choose a provider later"))
    later?.click()
    await new Promise(resolve => setTimeout(resolve, 1000))
    await writeFile(`${process.cwd().endsWith('/apps/webapp') ? '' : 'apps/webapp/'}.scratch/renderer-dom.txt`, document.body.textContent || '')
    expect(errors).toEqual([])
    expect(document.querySelector('#root')?.childElementCount).toBeGreaterThan(0)
    expect(document.body.textContent).not.toContain('Something went wrong')
    await vi.waitFor(() => expect(document.body.textContent).toContain('Browser smoke history'), { timeout: 15000 })
    const { $gatewayState } = await import('../../desktop/src/store/session')
    await vi.waitFor(() => {
      expect($gatewayState.get()).toBe('open')
      expect(document.body.textContent).not.toContain('CONNECTING')
    }, { timeout: 15000 })
    await writeFile(`${process.cwd().endsWith('/apps/webapp') ? '' : 'apps/webapp/'}.scratch/renderer-connected.txt`, document.body.textContent || '')
  } finally {
    mounted.root?.unmount()
    window.removeEventListener('error', handler)
    await backend.close()
  }
})
