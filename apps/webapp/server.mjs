import http from 'node:http'
import https from 'node:https'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.dirname(fileURLToPath(import.meta.url))
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.wasm': 'application/wasm', '.mp3': 'audio/mpeg', '.webp': 'image/webp', '.ico': 'image/x-icon' }
export function configuration(env = process.env) {
  const backend = new URL(env.WEBAPP_BACKEND || 'http://127.0.0.1:9119')
  if (!['http:', 'https:'].includes(backend.protocol) || backend.username || backend.password || backend.pathname !== '/' || backend.search || backend.hash) throw new Error('WEBAPP_BACKEND must be an HTTP(S) origin without credentials, path, query or fragment')
  const host = env.WEBAPP_HOST || '127.0.0.1'
  const port = Number(env.WEBAPP_PORT || 8080)
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Invalid WEBAPP_PORT')
  const publicOrigin = new URL(env.WEBAPP_PUBLIC_ORIGIN || `http://${host.includes(':') ? `[${host}]` : host}:${port}`)
  if (!['http:', 'https:'].includes(publicOrigin.protocol) || publicOrigin.username || publicOrigin.password || publicOrigin.pathname !== '/' || publicOrigin.search || publicOrigin.hash) throw new Error('WEBAPP_PUBLIC_ORIGIN must be an HTTP(S) origin')
  if (!['127.0.0.1', '::1', 'localhost'].includes(host) && !env.WEBAPP_PUBLIC_ORIGIN) throw new Error('Remote binding requires WEBAPP_PUBLIC_ORIGIN and authenticated backend setup; see README')
  return { backend, host, port, publicOrigin }
}
export function safePath(raw) {
  if (!raw?.startsWith('/') || raw.startsWith('//') || /[\\\x00-\x20#]/.test(raw)) return null
  let decoded
  try { decoded = decodeURIComponent(raw.split('?')[0]) } catch { return null }
  if (/[\\\x00-\x20%]/.test(decoded) || decoded.split('/').some(p => p === '..' || p === '.')) return null
  const url = new URL(raw, 'http://local.invalid')
  if (url.searchParams.has('native_dial') || url.searchParams.has('internal')) return null
  if (decoded.startsWith('/auth/native') || decoded.startsWith('/api/internal') || decoded.startsWith('/api/native')) return null
  return decoded
}
const authPaths = new Set(['/login', '/auth/login', '/auth/callback', '/auth/password-login', '/auth/logout'])
export function isProxyPath(p) { return p.startsWith('/api/') || authPaths.has(p) }
function reject(res, status, message) { res.writeHead(status, { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' }); res.end(message) }
function allowedRequest(req, config) {
  if (req.headers.host !== config.publicOrigin.host) return false
  // Defense against cross-site POSTs, WS hijacking, and DNS rebinding. Do not manufacture Origin.
  if (req.headers.origin && req.headers.origin !== config.publicOrigin.origin) return false
  if (req.headers['sec-fetch-site'] === 'cross-site' && req.method !== 'GET') return false
  return true
}
function upstreamHeaders(req, config) {
  const headers = { ...req.headers, host: config.backend.host }
  for (const key of Object.keys(headers)) if (key.startsWith('x-forwarded-') || ['forwarded', 'proxy-authorization', 'proxy-connection'].includes(key)) delete headers[key]
  // Only the server's configured public origin can influence OAuth callback URLs.
  headers['x-forwarded-host'] = config.publicOrigin.host
  headers['x-forwarded-proto'] = config.publicOrigin.protocol.slice(0, -1)
  return headers
}
export function createService(config, { dist = path.join(root, 'dist'), devOrigin } = {}) {
  const transport = config.backend.protocol === 'https:' ? https : http
  const sockets = new Set()
  function proxy(req, res, target, client, upgradeHead) {
    const headers = upstreamHeaders(req, config)
    if (target !== config.backend) headers.host = target.host
    const upstream = client.request({ protocol: target.protocol, hostname: target.hostname.replace(/^\[|\]$/g, ''), port: target.port, method: req.method, path: req.url, headers, timeout: 60000 })
    upstream.on('error', () => { if (res.writeHead) { if (!res.headersSent) reject(res, 502, 'Hermes backend unavailable'); else res.destroy() } else res.destroy() })
    upstream.on('timeout', () => upstream.destroy())
    upstream.on('response', incoming => {
      if (!res.writeHead) { res.end(`HTTP/1.1 ${incoming.statusCode} Upgrade rejected\r\nConnection: close\r\n\r\n`); incoming.resume(); return }
      const responseHeaders = { ...incoming.headers, 'cache-control': 'no-store' }
      // No browser credentials or permissive CORS are added by this proxy.
      delete responseHeaders['access-control-allow-origin']
      delete responseHeaders['access-control-allow-credentials']
      res.writeHead(incoming.statusCode, responseHeaders)
      incoming.pipe(res)
    })
    upstream.on('upgrade', (incoming, socket, head) => {
      sockets.add(socket); socket.on('close', () => sockets.delete(socket))
      res.write(`HTTP/1.1 101 Switching Protocols\r\n${Object.entries(incoming.headers).map(([k,v]) => `${k}: ${v}`).join('\r\n')}\r\n\r\n`)
      if (head.length) res.write(head)
      if (upgradeHead?.length) socket.write(upgradeHead)
      socket.on('error', () => res.destroy()); res.on('error', () => socket.destroy())
      res.on('close', () => socket.destroy()); socket.on('close', () => res.destroy())
      res.pipe(socket).pipe(res)
    })
    req.on('aborted', () => upstream.destroy())
    req.pipe(upstream)
  }
  const server = http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff')
    res.setHeader('Referrer-Policy', 'no-referrer')
    res.setHeader('X-Frame-Options', 'DENY')
    if (!allowedRequest(req, config)) return reject(res, 403, 'Host or Origin rejected')
    const p = safePath(req.url)
    if (!p) return reject(res, 400, 'Invalid path')
    if (isProxyPath(p)) return proxy(req, res, config.backend, transport)
    if (devOrigin) return proxy(req, res, new URL(devOrigin), http)
    if (!['GET', 'HEAD'].includes(req.method)) return reject(res, 405, 'Method not allowed')
    try {
      const base = await fs.realpath(dist)
      const relative = p === '/' ? 'index.html' : p.slice(1)
      // Only built public files are served. No repository or fallback filesystem reads.
      const candidate = await fs.realpath(path.join(base, relative))
      if (!candidate.startsWith(base + path.sep)) return reject(res, 404, 'Not found')
      if (!(await fs.stat(candidate)).isFile()) return reject(res, 404, 'Not found')
      res.setHeader('Content-Type', mime[path.extname(candidate)] || 'application/octet-stream')
      res.setHeader('Cache-Control', relative.startsWith('assets/') ? 'public, max-age=31536000, immutable' : 'no-store')
      res.end(req.method === 'HEAD' ? undefined : await fs.readFile(candidate))
    } catch { reject(res, 404, 'Not found') }
  })
  server.on('upgrade', (req, socket, head) => {
    const p = safePath(req.url)
    if (!allowedRequest(req, config) || !req.headers.origin || !p || (!p.startsWith('/api/') && !(devOrigin && p === '/'))) {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return
    }
    proxy(req, socket, p.startsWith('/api/') ? config.backend : new URL(devOrigin), p.startsWith('/api/') ? transport : http, head)
  })
  server.on('close', () => { for (const socket of sockets) socket.destroy() })
  return server
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const config = configuration()
  createService(config).listen(config.port, config.host, () => console.log(`Hermes Webapp: ${config.publicOrigin.origin} → ${config.backend.origin}`))
}
