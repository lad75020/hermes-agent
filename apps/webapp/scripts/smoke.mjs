import { chromium } from 'playwright'
import { spawn } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'
import readline from 'node:readline'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repo = path.resolve(root, '../..')
const origin = 'http://hermes-webapp.localhost:8080'
await fs.mkdir(path.join(root, '.scratch/smoke-home'), { recursive: true })
const child = spawn(process.env.WEBAPP_PYTHON || path.join(repo, 'venv/bin/python'), [path.join(root, 'scripts/backend-harness.py')], {
  cwd: repo, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', HERMES_HOME: path.join(root, '.scratch/smoke-home'), HERMES_RUNTIME_DIR: path.join(root, '.scratch/smoke-runtime'), TMPDIR: path.join(root, '.scratch') }, stdio: ['pipe', 'pipe', 'pipe']
})
const backendLog = await fs.open(path.join(root, '.scratch/smoke-backend.log'), 'w')
child.stderr.on('data', data => void backendLog.write(data))
let serial = 0
const pending = new Map(), socketRoutes = new Map(), socketFrames = new Map()
const observedSockets = []
let readyResolve
const ready = new Promise(resolve => { readyResolve = resolve })
readline.createInterface({ input: child.stdout }).on('line', line => {
  const data = JSON.parse(line)
  if (data.ready) readyResolve()
  else if (data.socket) {
    if (data.data) {
      const observed = observedSockets.find(socket => socket.id === data.socket)
      if (observed) {
        const frame = JSON.parse(data.data)
        if (frame.method === 'event' && frame.params?.type === 'gateway.ready') observed.ready = true
        if (frame.id != null && 'result' in frame) observed.replies++
      }
      const route = socketRoutes.get(data.socket)
      if (route) route.send(data.data); else socketFrames.set(data.socket, [...(socketFrames.get(data.socket) || []), data.data])
    }
  } else if (pending.has(data.id)) { const { resolve, reject, timer } = pending.get(data.id); clearTimeout(timer); pending.delete(data.id); data.error ? reject(new Error(data.error)) : resolve(data) }
})
function call(request) {
  const id = ++serial
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Backend timed out: ${request.path || request.op}`)) }, 60000)
    pending.set(id, { resolve, reject, timer }); child.stdin.write(JSON.stringify({ ...request, id }) + '\n')
  })
}
let browser
try {
  await Promise.race([ready, new Promise((_, reject) => setTimeout(() => reject(new Error('Backend harness startup timeout')), 45000))])
  const unauth = await call({ path: '/api/auth/me' }); assert.equal(unauth.status, 401)
  const unauthFs = await call({ path: '/api/fs/read?path=/etc/passwd' }); assert.equal(unauthFs.status, 401)
  const unauthTicket = await call({ path: '/api/auth/ws-ticket', method: 'POST' }); assert.equal(unauthTicket.status, 401)
  console.log('REAL ASGI: unauthenticated identity, filesystem and ticket requests rejected')
  browser = await chromium.launch({ channel: process.env.WEBAPP_BROWSER || 'chrome', headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  // Observe the renderer's own socket, without adding a production diagnostics API.
  await page.addInitScript(() => {
    const NativeSocket = window.WebSocket
    window.__webappSmokeSockets = []
    window.WebSocket = class extends NativeSocket {
      constructor(...args) {
        super(...args)
        const state = { url: String(args[0]).split('?')[0], open: false, ready: false, requests: {}, replies: [], errors: [] }
        window.__webappSmokeSockets.push(state)
        this.addEventListener('open', () => { state.open = true })
        this.addEventListener('close', () => { state.open = false })
        this.addEventListener('message', event => {
          const frame = JSON.parse(event.data)
          if (frame.method === 'event' && frame.params?.type === 'gateway.ready') state.ready = true
          if (frame.id != null && state.requests[frame.id]) {
            if ('result' in frame) state.replies.push(state.requests[frame.id])
            if (frame.error) state.errors.push({ method: state.requests[frame.id], error: frame.error })
          }
        })
        const send = this.send.bind(this)
        this.send = data => {
          const frame = JSON.parse(data)
          if (frame.id != null && frame.method) state.requests[frame.id] = frame.method
          send(data)
        }
      }
    }
  })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') console.log('BROWSER:', message.text().slice(0, 500)) })
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.origin !== origin) return route.abort()
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/') || url.pathname === '/login') {
      const result = await call({ path: url.pathname + url.search, method: route.request().method(), headers: await route.request().allHeaders(), body: route.request().postData() || '' })
      if (url.pathname.includes('ws-ticket')) console.log('TICKET STATUS:', result.status, result.status === 200 ? 'issued' : result.body)
      const headers = Object.fromEntries(result.headers.filter(([key]) => !['content-length', 'content-encoding', 'set-cookie'].includes(key)))
      const cookies = result.headers.filter(([key]) => key === 'set-cookie').map(([,value]) => value)
      if (cookies.length) headers['set-cookie'] = cookies.join('\n')
      return route.fulfill({ status: result.status, headers, body: result.body })
    }
    const file = path.join(root, 'dist', url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname))
    const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' }
    try { await route.fulfill({ body: await fs.readFile(file), contentType: types[path.extname(file)] || 'application/octet-stream' }) } catch { await route.fulfill({ status: 404, body: 'Not found' }) }
  })
  await page.routeWebSocket('**/api/**', async route => {
    const url = new URL(route.url())
    const result = await call({ op: 'ws-open', path: url.pathname + url.search })
    const observed = { id: result.id, ready: false, replies: 0 }
    observedSockets.push(observed)
    socketRoutes.set(result.id, route)
    for (const frame of socketFrames.get(result.id) || []) {
      const data = JSON.parse(frame)
      if (data.method === 'event' && data.params?.type === 'gateway.ready') observed.ready = true
      route.send(frame)
    }
    socketFrames.delete(result.id)
    route.onMessage(data => { child.stdin.write(JSON.stringify({ id: ++serial, op: 'ws-send', socket: result.id, data: data.toString() }) + '\n') })
    route.onClose(() => { socketRoutes.delete(result.id); child.stdin.write(JSON.stringify({ id: ++serial, op: 'ws-close', socket: result.id }) + '\n') })
  })
  await page.goto(origin)
  await page.getByRole('link', { name: 'Sign in to Hermes' }).waitFor()
  await page.getByRole('link', { name: 'Sign in to Hermes' }).click()
  console.log('LOGIN PAGE:', (await page.locator('body').innerText()).slice(0, 1200))
  await page.locator('input[name="username"]').fill('webapp-test')
  await page.locator('input[name="password"]').fill('isolated-browser-smoke-only')
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL(origin + '/')
  const later = page.getByRole('button', { name: "I'll choose a provider later" })
  if (await later.count()) await later.click()
  await page.getByText('Browser smoke history', { exact: true }).first().waitFor({ timeout: 30000 })
  try {
    // Sidebar titles arrive over REST and do not prove that RPC connected.
    await page.waitForTimeout(1000)
    assert.ok(observedSockets.some(socket => socket.ready && socket.replies > 0), `Expected real RPC connection: ${JSON.stringify(observedSockets)}`)
    await page.getByText('CONNECTING', { exact: true }).waitFor({ state: 'hidden', timeout: 30000 })
    await page.locator('[data-glass-opaque]').filter({ has: page.locator('.decode-cursor-blink') }).waitFor({ state: 'hidden', timeout: 30000 })
    await page.locator('[data-slot="composer-root"]').first().waitFor()
    await page.evaluate(() => document.fonts.ready)
  } finally {
    const diagnostics = await page.evaluate(() => {
      const measure = selector => {
        const element = document.querySelector(selector)
        if (!element) return null
        const rect = element.getBoundingClientRect(), style = getComputedStyle(element)
        return { width: rect.width, height: rect.height, x: rect.x, y: rect.y, display: style.display, flexDirection: style.flexDirection, background: style.backgroundColor }
      }
      const theme = getComputedStyle(document.documentElement)
      return {
        stylesheets: [...document.styleSheets].map(sheet => {
          try { return { href: sheet.href, rules: sheet.cssRules.length } } catch { return { href: sheet.href, inaccessible: true } }
        }),
        theme: Object.fromEntries(['--dt-background', '--dt-foreground', '--ui-bg-chrome'].map(key => [key, theme.getPropertyValue(key).trim()])),
        shell: measure('[data-contrib-shell]'), composer: measure('[data-slot="composer-root"]'),
        viewport: { width: innerWidth, height: innerHeight }, sockets: window.__webappSmokeSockets
      }
    })
    await fs.writeFile(path.join(root, '.scratch/browser-diagnostics.json'), JSON.stringify(diagnostics, null, 2))
    await page.screenshot({ path: path.join(root, '.scratch/browser-smoke.png'), fullPage: true })
    console.log('LAYOUT / RPC:', JSON.stringify(diagnostics))
  }
  const diagnostics = JSON.parse(await fs.readFile(path.join(root, '.scratch/browser-diagnostics.json'), 'utf8'))
  assert.equal(diagnostics.shell?.display, 'flex', 'Desktop shell must use Tailwind flex layout')
  assert.equal(diagnostics.shell?.flexDirection, 'column')
  assert.ok(diagnostics.shell?.width >= diagnostics.viewport.width - 2, 'Shell must fill viewport width')
  assert.ok(diagnostics.shell?.height >= diagnostics.viewport.height - 2, 'Shell must fill viewport height')
  for (const [key, value] of Object.entries(diagnostics.theme)) assert.ok(value, `Missing theme variable ${key}`)
  assert.notEqual(diagnostics.shell?.background, 'rgba(0, 0, 0, 0)', 'Shell background must resolve its theme')
  assert.ok(diagnostics.composer?.width > 400 && diagnostics.composer?.height >= 60, 'Composer must have usable geometry')
  assert.ok(diagnostics.composer.y >= 0 && diagnostics.composer.y + diagnostics.composer.height <= diagnostics.viewport.height + 2, 'Composer must fit in the viewport')
  console.log('RENDERED:', (await page.locator('body').innerText()).slice(0, 9000))
  console.log('PAGE ERRORS:', JSON.stringify(errors))
  assert.deepEqual(errors, [])
  await fs.writeFile(path.join(root, '.scratch/browser-smoke.txt'), await page.locator('body').innerText())
  await page.evaluate(() => { location.hash = '#/settings?tab=config:appearance' })
  await page.getByText('Appearance', { exact: true }).first().waitFor({ timeout: 15000 })
  await page.screenshot({ path: path.join(root, '.scratch/browser-settings.png'), fullPage: true })
  assert.deepEqual(errors, [])
} finally {
  await browser?.close()
  child.stdin.end(JSON.stringify({ id: ++serial, op: 'stop' }) + '\n')
  child.kill('SIGTERM')
  await backendLog.close()
}
