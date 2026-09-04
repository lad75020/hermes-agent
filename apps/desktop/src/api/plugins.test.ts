import { afterEach, describe, expect, it, vi } from 'vitest'

import { setApiRequestConnection, setApiRequestProfile } from '@/hermes'

import { activeConnection, pluginRest } from './plugins'

// desktop.getConnection/getConnectionFor are IPC round-trips into the main
// process with no timeout of their own (#93454). A wedged main-process
// round-trip must reject instead of hanging pluginSocket's connect() forever.
describe('activeConnection connection timeout (#93454)', () => {
  afterEach(() => {
    setApiRequestConnection(null)
    setApiRequestProfile(null)
    Reflect.deleteProperty(window, 'hermesDesktop')
    vi.useRealTimers()
  })

  it('rejects instead of hanging forever when getConnection() wedges', async () => {
    vi.useFakeTimers()
    setApiRequestProfile('coder')
    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: { getConnection: vi.fn(() => new Promise(() => undefined)) }
    })

    const pending = expect(activeConnection()).rejects.toThrow('Timed out connecting to profile "coder"')

    await vi.advanceTimersByTimeAsync(20_000)
    await pending
  })

  it('rejects instead of hanging forever when getConnectionFor() wedges', async () => {
    vi.useFakeTimers()
    setApiRequestConnection('gw-tailscale')
    setApiRequestProfile('research')
    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: {
        getConnection: vi.fn(() => new Promise(() => undefined)),
        getConnectionFor: vi.fn(() => new Promise(() => undefined))
      }
    })

    const pending = expect(activeConnection()).rejects.toThrow('Timed out connecting to profile "research"')

    await vi.advanceTimersByTimeAsync(20_000)
    await pending
  })
})

describe('pluginRest profile scoping', () => {
  afterEach(() => {
    setApiRequestConnection(null)
    setApiRequestProfile(null)
    Reflect.deleteProperty(window, 'hermesDesktop')
  })

  it('lets a global plugin opt out of the active profile route', async () => {
    const api = vi.fn(async (_request: Record<string, unknown>) => ({ ok: true }))
    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: { api }
    })
    setApiRequestProfile('ollama')

    await pluginRest('history-search', '/search/sessions', { method: 'POST', profile: null })

    expect(api).toHaveBeenCalledWith(expect.objectContaining({
      path: '/api/plugins/history-search/search/sessions',
      method: 'POST'
    }))
    expect(api.mock.calls[0]?.[0]).not.toHaveProperty('profile')
  })

  it('keeps ordinary plugins scoped to the active profile', async () => {
    const api = vi.fn(async (_request: Record<string, unknown>) => ({ ok: true }))
    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: { api }
    })
    setApiRequestProfile('ollama')

    await pluginRest('kanban', '/board')

    expect(api).toHaveBeenCalledWith(expect.objectContaining({ profile: 'ollama' }))
  })
})
