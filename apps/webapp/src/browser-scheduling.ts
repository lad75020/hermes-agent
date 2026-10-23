/** Desktop runs in Chromium; browser deployments may lack its idle scheduling API. */
export function installBrowserScheduling(target: Window = window): void {
  if (typeof target.requestIdleCallback === 'function' && typeof target.cancelIdleCallback === 'function') return
  // Replace the pair together so cancellation always owns the matching timer handle.
  target.requestIdleCallback = callback => target.setTimeout(() => {
    callback({ didTimeout: true, timeRemaining: () => 0 })
  }, 1)
  target.cancelIdleCallback = handle => target.clearTimeout(handle)
}
