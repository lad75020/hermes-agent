import { spawn } from 'node:child_process'
import readline from 'node:readline'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
export async function asgiClient(name = 'integration') {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
  fs.mkdirSync(path.join(root, '.scratch'), { recursive: true })
  const child = spawn(process.env.WEBAPP_PYTHON || path.resolve(root, '../../venv/bin/python'), [path.join(root, 'scripts/backend-harness.py')], {
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', HERMES_HOME: path.join(root, `.scratch/${name}-home`), HERMES_RUNTIME_DIR: path.join(root, `.scratch/${name}-runtime`), TMPDIR: path.join(root, '.scratch') }, stdio: ['pipe', 'pipe', fs.openSync(path.join(root, `.scratch/${name}-backend.log`), 'w')]
  })
  let serial = 0, readyResolve, readyReject
  const ready = new Promise((resolve, reject) => { readyResolve = resolve; readyReject = reject })
  child.on('error', readyReject)
  child.on('exit', code => readyReject(new Error(`ASGI harness exited (${code}); see .scratch/${name}-backend.log`)))
  const pending = new Map(), listeners = new Map(), frames = new Map()
  const lines = readline.createInterface({ input: child.stdout })
  lines.on('line', line => {
    const data = JSON.parse(line)
    if (data.ready) readyResolve()
    else if (data.socket) {
      const fn = listeners.get(data.socket)
      if (fn) fn(data); else frames.set(data.socket, [...(frames.get(data.socket) || []), data])
    } else {
      const item = pending.get(data.id)
      if (item) { clearTimeout(item.timer); pending.delete(data.id); data.error ? item.reject(new Error(data.error)) : item.resolve(data) }
    }
  })
  function send(request) { child.stdin.write(JSON.stringify({ ...request, id: ++serial }) + '\n'); return serial }
  function call(request) {
    const id = serial + 1
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`ASGI timeout: ${request.path || request.op}`)) }, 30000)
      pending.set(id, { resolve, reject, timer }); send(request)
    })
  }
  await Promise.race([ready, new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('ASGI startup timeout')), 30000); ready.finally(() => clearTimeout(timer)) })])
  return { call, send, subscribe(id, fn) { listeners.set(id, fn); for (const frame of frames.get(id) || []) fn(frame); frames.delete(id) },
    async close() { send({ op: 'stop' }); child.stdin.end(); for (const p of pending.values()) clearTimeout(p.timer); child.kill('SIGTERM'); lines.close() } }
}
