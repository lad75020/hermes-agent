import { afterEach, expect, it, vi } from 'vitest'
import { installBrowserScheduling } from '../src/browser-scheduling'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('runs and cancels idle work when the browser has no idle callback APIs', () => {
  vi.useFakeTimers()
  vi.stubGlobal('requestIdleCallback', undefined)
  vi.stubGlobal('cancelIdleCallback', undefined)
  installBrowserScheduling()
  const callback = vi.fn()
  const canceled = vi.fn()
  window.requestIdleCallback(callback, { timeout: 5000 })
  window.cancelIdleCallback(window.requestIdleCallback(canceled))
  expect(callback).not.toHaveBeenCalled()
  vi.runAllTimers()
  expect(callback).toHaveBeenCalledOnce()
  expect(callback.mock.calls[0][0].didTimeout).toBe(true)
  expect(callback.mock.calls[0][0].timeRemaining()).toBe(0)
  expect(canceled).not.toHaveBeenCalled()
})

it('preserves native idle scheduling when the browser provides the complete pair', () => {
  const request = vi.fn()
  const cancel = vi.fn()
  vi.stubGlobal('requestIdleCallback', request)
  vi.stubGlobal('cancelIdleCallback', cancel)
  installBrowserScheduling()
  expect(window.requestIdleCallback).toBe(request)
  expect(window.cancelIdleCallback).toBe(cancel)
})
