import { describe, expect, it, vi } from 'vitest'

import { BackendConnectionSupersededError, createBackendConnectionState } from './backend-connection-state'
import { BackendDialClaims } from './backend-dial-claim'
import { backendScopeKey, parseBackendScopeKey } from './connection-registry'
import { resolveDesktopConnectionRequest } from './desktop-profile'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void

  const promise = new Promise<T>((done, fail) => {
    resolve = done
    reject = fail
  })

  return { promise, resolve, reject }
}

describe('backend dials across a bootstrap reset', () => {
  it.each(['default', 'research'])('reconciles an obsolete claim with the current %s primary', async profile => {
    const claims = new BackendDialClaims()
    const state = createBackendConnectionState<never, { profile: string; baseUrl: string }>()
    const oldReady = deferred<{ profile: string; baseUrl: string }>()
    const oldAttempt = state.startAttempt()

    const oldConnection = oldReady.promise.then(connection => {
      state.assertCurrentAttempt(oldAttempt)

      return connection
    })

    state.setPromise(oldAttempt, oldConnection)
    const dial = vi.fn(() => state.getPromise()!)
    const primaryScope = backendScopeKey(null, profile)
    const beforeReset = claims.run(primaryScope, dial)

    state.invalidate()
    const currentAttempt = state.startAttempt()
    const ready = { profile, baseUrl: 'http://127.0.0.1:53151' }
    const currentConnection = Promise.resolve(ready)
    state.setPromise(currentAttempt, currentConnection)

    // A reloaded renderer joins the pre-reset claim while an independent
    // fleet route recovers. That secondary must not stand in for the primary.
    const afterReset = claims.run(primaryScope, dial)
    const fleetReady = { profile, baseUrl: 'https://fleet.example.com' }
    const fleetDial = vi.fn(async () => fleetReady)
    const fleet = claims.run(backendScopeKey('fleet-gateway', profile), fleetDial)
    expect(await fleet).toBe(fleetReady)
    oldReady.resolve({ profile, baseUrl: 'http://127.0.0.1:53150' })

    expect(await Promise.all([beforeReset, afterReset])).toEqual([ready, ready])
    expect(dial).toHaveBeenCalledTimes(2)
    expect(fleetDial).toHaveBeenCalledTimes(1)
    expect(state.getPromise()).toBe(currentConnection)
    expect(state.getProcess()).toBeNull()
    expect(claims.inFlight(primaryScope)).toBe(false)
  })

  it('reports the replacement failure to every waiter instead of the obsolete attempt error', async () => {
    const claims = new BackendDialClaims()
    const state = createBackendConnectionState<never, string>()
    const oldReady = deferred<string>()
    const oldAttempt = state.startAttempt()

    const oldConnection = oldReady.promise.then(connection => {
      state.assertCurrentAttempt(oldAttempt)

      return connection
    })

    state.setPromise(oldAttempt, oldConnection)
    const dial = vi.fn(() => state.getPromise()!)
    const first = claims.run('research', dial)

    state.invalidate()
    const replacement = deferred<string>()
    state.setPromise(state.startAttempt(), replacement.promise)
    const second = claims.run('research', dial)
    const failure = Object.assign(new Error('Gateway sign-in required'), { statusCode: 401 })
    const results = Promise.allSettled([first, second])
    oldReady.resolve('obsolete')
    replacement.reject(failure)

    expect(await results).toEqual([
      { status: 'rejected', reason: failure },
      { status: 'rejected', reason: failure }
    ])
    expect(dial).toHaveBeenCalledTimes(2)
    expect(state.getPromise()).toBe(replacement.promise)
    expect(claims.inFlight('research')).toBe(false)
  })

  it('bounds repeated supersessions and releases the claim for explicit recovery', async () => {
    const claims = new BackendDialClaims()
    const state = createBackendConnectionState()

    const dial = vi.fn(() => {
      const attempt = state.startAttempt()
      state.invalidate()
      state.assertCurrentAttempt(attempt)
    })

    await expect(claims.run('research', dial)).rejects.toBeInstanceOf(BackendConnectionSupersededError)
    expect(dial).toHaveBeenCalledTimes(3)
    expect(claims.inFlight('research')).toBe(false)
    await expect(claims.run('research', () => 'recovered')).resolves.toBe('recovered')
  })

  it('does not retry an ordinary error with the same message as a supersession', async () => {
    const claims = new BackendDialClaims()
    const failure = new Error(new BackendConnectionSupersededError().message)

    const dial = vi.fn(() => {
      throw failure
    })

    await expect(claims.run('research', dial)).rejects.toBe(failure)
    expect(dial).toHaveBeenCalledTimes(1)
  })
})

describe('BackendDialClaims (#90812)', () => {
  it('coalesces two concurrent dials for the same (connectionId, profile) onto ONE backend spawn', async () => {
    const claims = new BackendDialClaims()
    let spawns = 0
    let resolveSpawn: ((value: { baseUrl: string }) => void) | undefined

    const dial = vi.fn(() => {
      spawns += 1

      return new Promise<{ baseUrl: string }>(resolve => {
        resolveSpawn = resolve
      })
    })

    // Two renderer windows race the same reconnect: reconnectGateway()'s
    // in-flight lock is per-renderer, so BOTH invoke the main-process dial.
    const first = claims.run('conn:office-ssh::default', dial)
    const second = claims.run('conn:office-ssh::default', dial)

    expect(spawns).toBe(1)

    resolveSpawn?.({ baseUrl: 'http://127.0.0.1:53150' })

    const [firstResult, secondResult] = await Promise.all([first, second])

    // The second caller receives the FIRST dial's result, not its own spawn.
    expect(firstResult).toBe(secondResult)
    expect(firstResult).toEqual({ baseUrl: 'http://127.0.0.1:53150' })
    expect(dial).toHaveBeenCalledTimes(1)
  })

  it('scopes claims by key: different (connectionId, profile) pairs dial independently', async () => {
    const claims = new BackendDialClaims()
    const dialA = vi.fn(async () => 'a')
    const dialB = vi.fn(async () => 'b')

    const [a, b] = await Promise.all([
      claims.run('conn:office-ssh::default', dialA),
      claims.run('conn:office-ssh::work', dialB)
    ])

    expect(a).toBe('a')
    expect(b).toBe('b')
    expect(dialA).toHaveBeenCalledTimes(1)
    expect(dialB).toHaveBeenCalledTimes(1)
  })

  it('releases the claim once the dial settles so a later reconnect can dial again (bounded, not latched)', async () => {
    const claims = new BackendDialClaims()
    const dial = vi.fn(async () => 'fresh')

    await claims.run('default', dial)
    expect(claims.inFlight('default')).toBe(false)

    await claims.run('default', dial)
    expect(dial).toHaveBeenCalledTimes(2)
  })

  it('propagates a failed dial to every coalesced waiter and never caches the rejection', async () => {
    const claims = new BackendDialClaims()
    let rejectSpawn: ((error: Error) => void) | undefined

    const failingDial = vi.fn(
      () =>
        new Promise<never>((_resolve, reject) => {
          rejectSpawn = reject
        })
    )

    const first = claims.run('conn:office-ssh::default', failingDial)
    const second = claims.run('conn:office-ssh::default', failingDial)
    expect(failingDial).toHaveBeenCalledTimes(1)

    rejectSpawn?.(new Error('ssh dial failed'))

    await expect(first).rejects.toThrow('ssh dial failed')
    await expect(second).rejects.toThrow('ssh dial failed')

    // Fail closed but not latched: the NEXT dial attempt runs fresh.
    const recovered = vi.fn(async () => 'recovered')
    await expect(claims.run('conn:office-ssh::default', recovered)).resolves.toBe('recovered')
    expect(recovered).toHaveBeenCalledTimes(1)
  })

  it('a synchronously-throwing dial rejects the claim instead of escaping the coalescing seam', async () => {
    const claims = new BackendDialClaims()

    await expect(
      claims.run('default', () => {
        throw new Error('spawn refused')
      })
    ).rejects.toThrow('spawn refused')

    expect(claims.inFlight('default')).toBe(false)
  })
})

describe('parseBackendScopeKey (#90812/#93910)', () => {
  it('round-trips the composite pool key back to (connectionId, profile)', () => {
    expect(parseBackendScopeKey('conn:office-ssh::default')).toEqual({
      connectionId: 'office-ssh',
      profile: 'default'
    })
    expect(parseBackendScopeKey('conn:office-ssh::work')).toEqual({ connectionId: 'office-ssh', profile: 'work' })
  })

  it('treats a bare profile key as the local/primary scope', () => {
    expect(parseBackendScopeKey('default')).toEqual({ connectionId: null, profile: 'default' })
    expect(parseBackendScopeKey('work')).toEqual({ connectionId: null, profile: 'work' })
  })
})

describe('resolved window routes share one dial claim (#90812)', () => {
  it.each([null, 'office-ssh'])(
    'coalesces resolved window routes without absorbing a same-named source (%s)',
    async connectionId => {
      const claims = new BackendDialClaims()
      const source = { connectionId, profile: 'work', registryScoped: connectionId !== null }
      const route = resolveDesktopConnectionRequest(undefined, source, 'default')
      const key = backendScopeKey(route.connectionId, route.profile)
      const dial = vi.fn(async () => ({ baseUrl: 'http://localhost:53150' }))
      const other = vi.fn(async () => ({ baseUrl: 'http://localhost:53151' }))

      const [first, second, separate] = await Promise.all([
        claims.run(key, dial),
        claims.run(key, dial),
        claims.run(backendScopeKey('another-source', route.profile), other)
      ])

      expect(first).toBe(second)
      expect(first).not.toBe(separate)
      expect(dial).toHaveBeenCalledTimes(1)
      expect(other).toHaveBeenCalledTimes(1)
    }
  )
})
