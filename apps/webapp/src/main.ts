import { createBrowserAdapter } from './adapter'
import './webapp.css'

function authPanel(message: string) {
  const root = document.getElementById('root')!
  root.replaceChildren()
  const panel = document.createElement('main')
  panel.className = 'webapp-login'
  const title = document.createElement('h1'); title.textContent = 'Hermes'
  const description = document.createElement('p'); description.textContent = message
  const link = document.createElement('a'); link.href = '/login?next=%2F'; link.textContent = 'Sign in to Hermes'
  const retry = document.createElement('button'); retry.textContent = 'Retry connection'; retry.onclick = () => location.reload()
  panel.append(title, description, link, retry); root.append(panel)
}
function controls() {
  const bar = document.createElement('details'); bar.id = 'webapp-controls'
  const label = document.createElement('summary'); label.textContent = 'Browser controls'
  const capabilities = document.createElement('p'); capabilities.textContent = 'Chat, sessions, profiles and backend settings use Hermes APIs. Native windows, SSH management, embedded browser, OS integration and runtime plugins are unavailable.'
  const logout = document.createElement('button'); logout.textContent = 'Sign out'; logout.onclick = async () => {
    await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' }); location.assign('/login?next=%2F')
  }
  const status = document.createElement('p'); status.role = 'status'
  window.addEventListener('hermes-capability-error', event => { status.textContent = (event as CustomEvent<string>).detail; bar.open = true })
  bar.append(label, capabilities, logout, status); document.body.append(bar)
}
window.addEventListener('hermes-auth-required', () => {
  // A fresh login resets all renderer caches and sockets together.
  location.assign('/login?next=%2F')
}, { once: true })
async function start() {
  authPanel('Connecting to the authenticated Hermes backend…')
  try {
    const response = await fetch('/api/auth/me', { credentials: 'same-origin', redirect: 'error', signal: AbortSignal.timeout(15000) })
    if (!response.ok) { authPanel(response.status === 401 || response.status === 403 ? 'Sign in using the backend’s configured dashboard authentication provider.' : `Backend returned HTTP ${response.status}. Check the service configuration, then retry.`); return }
    const identity = await response.json() as { provider: string }
    if (identity.provider === 'loopback') { authPanel('This backend uses a native loopback token. Configure Hermes dashboard authentication to enable browser sessions.'); return }
    window.hermesDesktop = createBrowserAdapter()
    document.getElementById('root')!.replaceChildren()
    controls()
    await import('../../desktop/src/main')
  } catch (error) { authPanel(`Unable to connect: ${error instanceof Error ? error.message : String(error)}`) }
}
void start()
