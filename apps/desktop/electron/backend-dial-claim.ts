import { BackendConnectionSupersededError } from './backend-connection-state'

// A reset can retire the primary while a renderer still holds its dial claim.
// Re-resolve the SAME scope, joining the replacement if one exists. Keep this
// bounded so repeated resets still end at the caller's recovery surface.
async function dialCurrentBackend<T>(dial: () => Promise<T> | T): Promise<T> {
  for (let retry = 0; ; retry += 1) {
    try {
      return await dial()
    } catch (error) {
      if (!(error instanceof BackendConnectionSupersededError) || retry >= 2) {
        throw error
      }
    }
  }
}

/**
 * backend-dial-claim.ts
 *
 * Single-owner reconnect/dial claim for backend spawns, keyed by the pool
 * scope key from backendScopeKey(connectionId, profile) (#90812).
 *
 * Why this exists: reconnectGateway()'s in-flight lock lives at renderer
 * module scope, so it only dedupes reconnects INSIDE one window. Two windows
 * (main + a session pop-out) racing the same wake both invoke the main-process
 * dial IPC, and for a pooled SSH connection the loser of the pool-entry race
 * could bootstrap a duplicate remote backend. Electron main is the single
 * owner of backend lifecycles, so the claim belongs here: the first dial for a
 * (connectionId, profile) key runs; every concurrent caller for the same key
 * awaits and receives that first dial's result.
 *
 * Bounded by construction: a claim exists only while its dial promise is
 * unsettled — both outcomes release it, so a failed dial is never cached and
 * the next reconnect attempt runs fresh (fail closed, not latched).
 */
export class BackendDialClaims {
  readonly #inflightByKey = new Map<string, Promise<unknown>>()

  /** Whether a dial for this key is currently in flight (test/diagnostic seam). */
  inFlight(key: string): boolean {
    return this.#inflightByKey.has(key)
  }

  run<T>(key: string, dial: () => Promise<T> | T): Promise<T> {
    const existing = this.#inflightByKey.get(key) as Promise<T> | undefined

    if (existing) {
      return existing
    }

    // The claim spans supersession retries, so all waiters reconcile together
    // without starting competing dials. Real failures still reject the claim.
    const pending = dialCurrentBackend(dial)

    const release = () => {
      if (this.#inflightByKey.get(key) === pending) {
        this.#inflightByKey.delete(key)
      }
    }

    this.#inflightByKey.set(key, pending)
    // Release on both outcomes without creating an unhandled rejected branch.
    void pending.then(release, release)

    return pending
  }
}
