import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import net from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { CDP } from './perf/lib/cdp.mjs'

const require = createRequire(import.meta.url)
const electron = require('electron')
const hermesRoot = fileURLToPath(new URL('../../../', import.meta.url))

const pluginSource = `
import { ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx } from 'react/jsx-runtime'

function SmokePage() {
  const [ready] = useState(true)
  return jsx('div', {
    'data-testid': 'runtime-plugin-smoke',
    children: ready ? 'Runtime SDK loaded' : ''
  })
}

export default {
  id: 'runtime-plugin-smoke',
  register(ctx) {
    globalThis.__HERMES_RUNTIME_PLUGIN_SMOKE__ = [
      typeof ROUTES_AREA,
      typeof SIDEBAR_NAV_AREA,
      typeof useState,
      typeof jsx
    ]
    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/runtime-plugin-smoke' },
        render: () => jsx(SmokePage, {})
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { codicon: 'extensions', label: 'Runtime plugin smoke', path: '/runtime-plugin-smoke' }
      }
    ])
  }
}
`

async function availablePort() {
  const server = net.createServer()
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const address = server.address()
  await new Promise(resolve => server.close(resolve))

  if (!address || typeof address === 'string') {
    throw new Error('could not allocate a CDP port')
  }

  return address.port
}

const delay = ms => new Promise(resolve => setTimeout(resolve, ms))

test('production bundle loads runtime plugins through SDK and React shims', { timeout: 75_000 }, async () => {
  const root = mkdtempSync(join(tmpdir(), 'hermes-runtime-plugin-test-'))
  const hermesHome = join(root, 'home')
  const userData = join(root, 'user-data')
  const pluginDir = join(hermesHome, 'desktop-plugins', 'runtime-plugin-smoke')
  const desktopLog = join(hermesHome, 'logs', 'desktop.log')
  const port = await availablePort()

  mkdirSync(pluginDir, { recursive: true })
  writeFileSync(join(pluginDir, 'plugin.js'), pluginSource)
  writeFileSync(
    join(hermesHome, 'config.yaml'),
    `model:
  default: smoke-model
  provider: smoke
providers:
  smoke:
    api: http://127.0.0.1:9/v1
    name: Runtime smoke
    api_mode: chat_completions
    key_env: RUNTIME_SMOKE_API_KEY
    models:
      smoke-model: {}
`
  )
  writeFileSync(join(hermesHome, '.env'), 'RUNTIME_SMOKE_API_KEY=runtime-smoke-key\n')

  const child = spawn(
    electron,
    ['.', `--user-data-dir=${userData}`, `--remote-debugging-port=${port}`],
    {
      cwd: new URL('..', import.meta.url),
      env: {
        ...process.env,
        HERMES_DESKTOP_CDP_PORT: String(port),
        HERMES_DESKTOP_HERMES_ROOT: hermesRoot,
        HERMES_DESKTOP_IGNORE_EXISTING: '1',
        HERMES_HOME: hermesHome
      },
      stdio: 'ignore'
    }
  )

  let cdp

  try {
    cdp = await CDP.connect({ port, timeoutMs: 30_000 })
    const deadline = Date.now() + 15_000
    let marker

    while (Date.now() < deadline) {
      marker = await cdp.eval('globalThis.__HERMES_RUNTIME_PLUGIN_SMOKE__ ?? null')
      if (marker) break
      await delay(200)
    }

    const sdkType = await cdp.eval('typeof globalThis.__HERMES_PLUGIN_SDK__')
    const log = (() => {
      try {
        return readFileSync(desktopLog, 'utf8')
      } catch {
        return ''
      }
    })()

    assert.deepEqual(marker, ['string', 'string', 'function', 'function'], `runtime plugin did not load (SDK global: ${sdkType})\n${log}`)

    const clicked = await cdp.eval(`(() => {
      const label = document.querySelector('[data-tour="sidebar-nav-runtime-plugin-smoke:nav"]')
      const button = label?.closest('button')
      if (!button) return false
      button.click()
      return true
    })()`)
    assert.equal(clicked, true, `runtime plugin nav contribution did not render\n${log}`)

    // A clean HERMES_HOME also starts an isolated local backend. The route is
    // registered immediately, but the first-run launch overlay can cover the
    // workspace for several seconds before the contributed page mounts.
    const renderDeadline = Date.now() + 20_000
    let pageText = null
    while (Date.now() < renderDeadline) {
      pageText = await cdp.eval(`document.querySelector('[data-testid="runtime-plugin-smoke"]')?.textContent ?? null`)
      if (pageText) break
      await delay(100)
    }
    const renderState = await cdp.eval(`({
      href: location.href,
      bodyText: document.body.innerText.slice(0, 1_000),
      nav: document.querySelector('[data-tour="sidebar-nav-runtime-plugin-smoke:nav"]')?.parentElement?.outerHTML ?? null
    })`)
    assert.equal(
      pageText,
      'Runtime SDK loaded',
      `runtime plugin route did not render\n${JSON.stringify(renderState, null, 2)}\n${log}`
    )
  } finally {
    if (cdp) {
      const socketClosed =
        cdp.ws.readyState === WebSocket.CLOSED
          ? Promise.resolve()
          : new Promise(resolve => cdp.ws.addEventListener('close', resolve, { once: true }))
      cdp.close()
      await Promise.race([socketClosed, delay(1_000)])
    }

    const childClosed =
      child.exitCode !== null || child.signalCode !== null
        ? Promise.resolve()
        : new Promise(resolve => child.once('close', resolve))
    child.kill('SIGTERM')
    const closedGracefully = await Promise.race([
      childClosed.then(() => true),
      delay(3_000).then(() => false)
    ])
    if (!closedGracefully && child.exitCode === null && child.signalCode === null) {
      child.kill('SIGKILL')
      await Promise.race([new Promise(resolve => child.once('close', resolve)), delay(3_000)])
    }
    child.unref()
    rmSync(root, { recursive: true, force: true })
  }
})
