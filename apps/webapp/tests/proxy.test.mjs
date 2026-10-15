import test from 'node:test'
import assert from 'node:assert/strict'
import http from 'node:http'
import { PassThrough, Writable, Duplex } from 'node:stream'
import { once } from 'node:events'
import fs from 'node:fs/promises'
import path from 'node:path'
import { configuration, createService, safePath } from '../server.mjs'
const config = configuration({ WEBAPP_PUBLIC_ORIGIN: 'http://localhost:8080' })
class Response extends Writable {
  headers = {}; body = ''; statusCode = 200; headersSent = false
  setHeader(k, v) { this.headers[k.toLowerCase()] = v }
  writeHead(status, headers = {}) { this.statusCode = status; for (const [k,v] of Object.entries(headers)) this.setHeader(k,v); this.headersSent = true }
  _write(chunk, _encoding, cb) { this.body += chunk; cb() }
}
async function request(server, url, { headers = {}, method = 'GET', body = '' } = {}) {
  const req = new PassThrough(); req.url = url; req.method = method; req.headers = { host: 'localhost:8080', ...headers }
  const res = new Response(); const finished = once(res, 'finish')
  server.emit('request', req, res); req.end(body); await finished
  return res
}
test('configuration defaults to loopback and rejects target credentials/paths and ambiguous exposure', () => {
  assert.equal(configuration({}).host, '127.0.0.1')
  for (const backend of ['file:///etc', 'http://user:secret@localhost', 'http://localhost/api', 'http://localhost/?url=evil']) assert.throws(() => configuration({ WEBAPP_BACKEND: backend }))
  assert.throws(() => configuration({ WEBAPP_HOST: '0.0.0.0' }))
})
test('path boundary rejects encoded and raw traversal, backslashes, native doors and absolute targets', async () => {
  for (const p of ['http://evil/api', '//evil/api', '/api/../secret', '/%2e%2e/config', '/a/%252e%252e/config', '/a%5cb', '/%00', '/%zz', '/api/ws?native_dial=1', '/auth/native/token', '/api/native/control']) assert.equal(safePath(p), null, p)
  const server = createService(config)
  for (const p of ['/../.env', '/%2e%2e/.env', '/auth/native/token', '/api/ws?native_dial=1']) assert.equal((await request(server, p)).statusCode, 400)
})
test('production static handler serves only real built files and rejects symlink escapes and source reads', async () => {
  const base = new URL('../.scratch/proxy-fixture', import.meta.url).pathname
  await fs.mkdir(path.join(base, 'dist'), { recursive: true })
  await fs.writeFile(path.join(base, 'secret'), 'private')
  await fs.writeFile(path.join(base, 'dist/index.html'), '<h1>built renderer</h1>')
  await fs.rm(path.join(base, 'dist/escape'), { force: true }); await fs.symlink(path.join(base, 'secret'), path.join(base, 'dist/escape'))
  const server = createService(config, { dist: path.join(base, 'dist') })
  assert.equal((await request(server, '/')).body, '<h1>built renderer</h1>')
  for (const p of ['/escape', '/src/adapter.ts', '/server.mjs', '/.env']) assert.equal((await request(server, p)).statusCode, 404)
  assert.equal((await request(server, '/', { method: 'POST' })).statusCode, 405)
})
test('rejects rebinding and cross-origin API requests before contacting backend', async t => {
  const call = t.mock.method(http, 'request', () => { throw new Error('must not dial') })
  const server = createService(config)
  assert.equal((await request(server, '/api/config', { headers: { host: 'attacker.invalid:8080' } })).statusCode, 403)
  assert.equal((await request(server, '/api/config', { method: 'POST', headers: { origin: 'https://evil.invalid' } })).statusCode, 403)
  assert.equal(call.mock.callCount(), 0)
})
test('HTTP proxy preserves backend auth failures, cookies, methods and profile paths without injecting secrets', async t => {
  let options, sent = ''
  t.mock.method(http, 'request', value => {
    options = value
    const upstream = new PassThrough(); upstream.on('data', bytes => { sent += bytes })
    upstream.on('finish', () => {
      const response = new PassThrough(); response.statusCode = 401; response.headers = { 'content-type': 'application/json', 'set-cookie': ['session=rotated; HttpOnly; SameSite=Lax'], 'access-control-allow-origin': '*' }
      upstream.emit('response', response); response.end('{"detail":"Unauthorized"}')
    })
    return upstream
  })
  const res = await request(createService(config), '/api/config?profile=secondary', { method: 'POST', headers: { cookie: 'session=browser', origin: 'http://localhost:8080', 'x-forwarded-host': 'evil.invalid', 'proxy-authorization': 'secret' }, body: '{"a":1}' })
  assert.equal(options.hostname, '127.0.0.1'); assert.equal(options.port, '9119'); assert.equal(options.path, '/api/config?profile=secondary'); assert.equal(options.method, 'POST')
  assert.equal(options.headers.cookie, 'session=browser'); assert.equal(options.headers.origin, 'http://localhost:8080')
  assert.equal(options.headers['x-forwarded-host'], 'localhost:8080'); assert.equal(options.headers.authorization, undefined); assert.equal(options.headers['proxy-authorization'], undefined)
  assert.equal(sent, '{"a":1}'); assert.equal(res.statusCode, 401); assert.match(res.body, /Unauthorized/)
  assert.equal(res.headers['set-cookie'][0], 'session=rotated; HttpOnly; SameSite=Lax'); assert.equal(res.headers['access-control-allow-origin'], undefined)
})
class Socket extends Duplex {
  output = ''
  _read() {}
  _write(bytes, _encoding, cb) { this.output += bytes; cb() }
}
test('WebSocket proxy retains Origin and public ticket and forwards upgrade plus buffered bytes', async t => {
  let options
  const peer = new Socket()
  t.mock.method(http, 'request', value => {
    options = value; const upstream = new PassThrough()
    queueMicrotask(() => upstream.emit('upgrade', { headers: { upgrade: 'websocket', connection: 'Upgrade', 'sec-websocket-accept': 'accepted' } }, peer, Buffer.from('server-head')))
    return upstream
  })
  const req = new PassThrough(); req.url = '/api/ws?ticket=public-one-use'; req.method = 'GET'; req.headers = { host: 'localhost:8080', origin: 'http://localhost:8080', upgrade: 'websocket', connection: 'Upgrade' }
  const socket = new Socket(); const server = createService(config)
  server.emit('upgrade', req, socket, Buffer.from('client-head')); req.end()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(options.path, '/api/ws?ticket=public-one-use'); assert.equal(options.headers.origin, 'http://localhost:8080')
  assert.match(socket.output, /101 Switching Protocols/); assert.match(socket.output, /server-head/); assert.equal(peer.output, 'client-head')
  peer.push(Buffer.from('stream-frame')); await new Promise(resolve => setImmediate(resolve)); assert.match(socket.output, /stream-frame/)
  socket.destroy(); peer.destroy()
})
test('WebSocket boundary refuses absent/foreign Origin, native dials and non-API upgrades', () => {
  for (const [url, origin] of [['/api/ws', undefined], ['/api/ws', 'https://evil.invalid'], ['/api/ws?native_dial=1', 'http://localhost:8080'], ['/proxy?url=http://evil', 'http://localhost:8080']]) {
    const req = new PassThrough(); req.url = url; req.method = 'GET'; req.headers = { host: 'localhost:8080', origin }
    const socket = new Socket(); createService(config).emit('upgrade', req, socket, Buffer.alloc(0)); assert.match(socket.output, /403 Forbidden/)
  }
})
