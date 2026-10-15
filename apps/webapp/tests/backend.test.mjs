import test from 'node:test'
import assert from 'node:assert/strict'
import { asgiClient } from './asgi-client.mjs'
test('real Hermes ASGI auth, public tickets, RPC, profiles and settings (no listener or model)', { timeout: 90000 }, async () => {
  const backend = await asgiClient()
  try {
    for (const path of ['/api/auth/me', '/api/fs/read?path=/etc/passwd', '/api/sessions', '/api/config']) {
      assert.equal((await backend.call({ path })).status, 401, path)
    }
    assert.equal((await backend.call({ path: '/api/auth/ws-ticket', method: 'POST' })).status, 401)
    const login = await backend.call({ path: '/auth/password-login', method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ provider: 'basic', username: 'webapp-test', password: 'wrong' }) })
    assert.equal(login.status, 401)
    const signedIn = await backend.call({ path: '/auth/password-login', method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ provider: 'basic', username: 'webapp-test', password: 'isolated-browser-smoke-only', next: '/' }) })
    assert.equal(signedIn.status, 200)
    assert(signedIn.headers.some(([key, value]) => key === 'set-cookie' && /HttpOnly/i.test(value)))
    const identity = await backend.call({ path: '/api/auth/me' })
    assert.equal(identity.status, 200); assert.equal(JSON.parse(identity.body).provider, 'basic')
    for (const path of ['/api/profiles', '/api/config', '/api/sessions']) {
      const result = await backend.call({ path }); assert.equal(result.status, 200, `${path}: ${result.body.slice(0, 200)}`)
    }
    const history = JSON.parse((await backend.call({ path: '/api/profiles/sessions/sidebar?profile=default' })).body)
    assert(history.recents.sessions.some(row => row.title === 'Browser smoke history'))
    const configBefore = JSON.parse((await backend.call({ path: '/api/config?profile=default' })).body)
    const changed = { ...configBefore, agent: { ...configBefore.agent, max_turns: 7 } }
    const saved = await backend.call({ path: '/api/config?profile=default', method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ config: changed }) })
    assert.equal(saved.status, 200, saved.body)
    assert.equal(JSON.parse((await backend.call({ path: '/api/config?profile=default' })).body).agent.max_turns, 7)
    await backend.call({ path: '/api/config?profile=default', method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ config: configBefore }) })
    const mint = await backend.call({ path: '/api/auth/ws-ticket', method: 'POST' })
    assert.equal(mint.status, 200)
    const ticket = JSON.parse(mint.body).ticket
    const ws = await backend.call({ op: 'ws-open', path: `/api/ws?ticket=${encodeURIComponent(ticket)}` })
    const frames = [], waiters = []
    backend.subscribe(ws.id, frame => { if (frame.data) { for (const line of frame.data.trim().split('\n')) frames.push(JSON.parse(line)); for (const wake of waiters.splice(0)) wake() } })
    async function waitFor(predicate) {
      const deadline = Date.now() + 15000
      while (!frames.some(predicate)) {
        assert(Date.now() < deadline, `RPC timeout: ${JSON.stringify(frames).slice(0, 1200)}`)
        await new Promise(resolve => { waiters.push(resolve); setTimeout(resolve, 200) })
      }
      return frames.find(predicate)
    }
    const ready = await waitFor(frame => frame.method === 'event' && frame.params?.type === 'gateway.ready')
    assert(ready.params)
    backend.send({ op: 'ws-send', socket: ws.id, data: JSON.stringify({ jsonrpc: '2.0', id: 50, method: 'session.list', params: {} }) })
    const sessions = await waitFor(frame => frame.id === 50)
    assert.equal(sessions.error, undefined, JSON.stringify(sessions))
    await assert.rejects(backend.call({ op: 'ws-open', path: `/api/ws?ticket=${encodeURIComponent(ticket)}` }), /WebSocketDisconnect/)
    backend.send({ op: 'ws-close', socket: ws.id })
    await backend.call({ path: '/auth/logout', method: 'POST' })
    assert.equal((await backend.call({ path: '/api/auth/me' })).status, 401)
  } finally { await backend.close() }
})
