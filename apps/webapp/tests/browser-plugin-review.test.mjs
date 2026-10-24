import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';
import { once } from 'node:events';
import net from 'node:net';
import { snapshot } from '../plugin-host.mjs';
import { BrowserPluginRuntime } from '../src/browser-plugin-runtime.mjs';
const exec = promisify(execFile);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const tmp = await fs.mkdtemp(path.join(process.env.TMPDIR, 'review-tests-'));
const root = path.join(tmp, 'plugins'), store = path.join(tmp, 'store'), pkg = path.join(root, 'sample');
await fs.mkdir(pkg, { recursive: true });
await fs.mkdir(store, { mode: 0o700 });
const config = { store, profiles: { default: [{ path: root, layout: 'standalone' }] } };
const manifest = JSON.stringify({ id: 'sample', name: 'Sample', entry: 'plugin.js', assets: ['asset.txt'] });
const code = "export default {id:'sample',register(){}}";
await fs.writeFile(path.join(pkg, 'browser-plugin.json'), manifest);
await fs.writeFile(path.join(pkg, 'plugin.js'), code);
await fs.writeFile(path.join(pkg, 'asset.txt'), 'inert');
const snap = await snapshot(config, 'default', 'sample');
test.after(() => fs.rm(tmp, { recursive: true, force: true }));
function setup() {
  let slow = false, mode = 'valid', disposed = 0, active = 0, maxActive = 0, scope = 'default';
  const runtime = new BrowserPluginRuntime({
    scope: () => scope, reserved: () => false, drop() {}, publish() {}, report() {},
    request: async route => {
      const profile = scope, state = mode;
      active++; maxActive = Math.max(active, maxActive);
      try {
        if (slow) await sleep(35);
        if (state === 'failure') throw Error('slow inventory failure');
        if (route.includes('/sample/')) return { ...snap, approved: true, principal: 'owner', profile };
        return { principal: 'owner', profile, plugins: state === 'removal' ? [] : [{ id: 'sample', digest: state === 'changed' ? 'changed' : snap.digest, approved: state !== 'revoked', ...(state === 'error' ? { error: 'source rejected' } : {}) }] };
      } finally { active--; }
    },
    evaluate: async () => ({ default: { id: 'sample', register() {} } }),
    activate: async () => () => disposed++,
  });
  return { runtime, slow: () => { slow = true; }, mode: v => { mode = v; }, scope: v => { scope = v; }, get disposed() { return disposed; }, get maxActive() { return maxActive; } };
}
for (const mode of ['revoked', 'removal', 'changed', 'error', 'failure']) {
  test(`sustained slow polling reconciles ${mode} without starvation`, async () => {
    const f = setup();
    await f.runtime.scan(); await f.runtime.enable('sample');
    assert.equal(f.runtime.records.get('sample').live, true);
    f.slow(); f.mode(mode);
    const pending = [];
    const timer = setInterval(() => pending.push(f.runtime.scan()), 20);
    try {
      await sleep(240);
      assert.equal(f.disposed, 1, 'must dispose while periodic polling is still running');
      assert.notEqual(f.runtime.records.get('sample')?.live, true);
      assert.equal(f.maxActive, 1, 'same-generation inventory requests must be coalesced');
    } finally { clearInterval(timer); await Promise.all(pending); f.runtime.reset(); }
  });
}
for (const change of ['reset', 'profile']) {
  test(`slow coalesced scan cannot overwrite fresh ${change} generation`, async () => {
    const f = setup(); await f.runtime.scan(); f.slow();
    const old = f.runtime.scan();
    if (change === 'reset') f.runtime.reset(); else f.scope('work');
    await f.runtime.scan(); await old;
    assert.equal(f.runtime.profile, change === 'profile' ? 'work' : 'default');
    assert.equal(f.runtime.records.get('sample').profile, f.runtime.profile);
    f.runtime.reset();
  });
}
for (const change of ['reset', 'profile']) for (const failure of [false, true]) {
  test(`late ${failure ? 'failed' : 'successful'} scan cannot replace fresh ${change} inventory`, async () => {
    const f = setup(); await f.runtime.scan();
    const original = f.runtime.options.request;
    let release, reached;
    const gate = new Promise(r => { release = r; });
    const ready = new Promise(r => { reached = r; });
    let first = true;
    f.runtime.options.request = async route => {
      const data = await original(route);
      if (first) { first = false; reached(); await gate; if (failure) throw Error('stale failure'); }
      return data;
    };
    const old = f.runtime.scan(); await ready;
    if (change === 'reset') f.runtime.reset(); else f.scope('work');
    await f.runtime.scan();
    const fresh = f.runtime.records.get('sample');
    try { assert.ok(fresh); }
    finally { release(); await old; }
    assert.equal(f.runtime.records.get('sample'), fresh);
    assert.equal(f.runtime.profile, change === 'profile' ? 'work' : 'default');
    f.runtime.reset();
  });
}
for (const name of ['browser-plugin.json', 'plugin.js', 'asset.txt']) {
  test(`rejects FIFO ${name} before blocking, including unapproved inventory`, async () => {
    const target = path.join(pkg, name), saved = await fs.readFile(target);
    await fs.unlink(target); await exec('mkfifo', [target]);
    try {
      const script = `import assert from 'node:assert/strict'; import { snapshot, inventory } from ${JSON.stringify(new URL('../plugin-host.mjs', import.meta.url).href)}; const cfg=${JSON.stringify(config)}; await assert.rejects(snapshot(cfg,'default','sample'), /rejected/); const rows=await inventory(cfg,'default'); assert.match(rows[0].error,/rejected/); console.log('rejected snapshot and inventory');`;
      const result = await exec(process.execPath, ['--input-type=module', '-e', script], { timeout: 2000, killSignal: 'SIGKILL' });
      assert.match(result.stdout, /rejected snapshot and inventory/);
    } finally { await fs.unlink(target); await fs.writeFile(target, saved); }
  });
}
test('rejects directory and Unix socket entries without reading', async () => {
  const target = path.join(pkg, 'asset.txt'), saved = await fs.readFile(target);
  await fs.unlink(target); await fs.mkdir(target);
  try { await assert.rejects(snapshot(config, 'default', 'sample'), /size\/type rejected/); }
  finally { await fs.rmdir(target); }
  const socket = net.createServer();
  socket.listen(target); await once(socket, 'listening');
  try { await assert.rejects(snapshot(config, 'default', 'sample')); }
  finally { await new Promise(r => socket.close(r)); await fs.writeFile(target, saved); }
});
test('dev launcher loads owner-controlled opt-in config before serving plugin routes', async () => {
  const cfg = path.join(tmp, 'host.json');
  await fs.writeFile(cfg, JSON.stringify(config), { mode: 0o600 });
  const allocator = net.createServer(); allocator.listen(0, '127.0.0.1'); await once(allocator, 'listening');
  const port = allocator.address().port; await new Promise(r => allocator.close(r));
  const child = spawn(process.execPath, [new URL('../scripts/dev.mjs', import.meta.url).pathname], { cwd: new URL('..', import.meta.url), env: { ...process.env, WEBAPP_PLUGIN_CONFIG: cfg, WEBAPP_PORT: String(port), WEBAPP_PUBLIC_ORIGIN: `http://127.0.0.1:${port}` }, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = ''; child.stdout.on('data', b => logs += b); child.stderr.on('data', b => logs += b);
  const closed = once(child, 'close');
  try {
    const until = Date.now() + 15000;
    while (!logs.includes('Hermes Webapp dev:') && child.exitCode === null && Date.now() < until) await sleep(50);
    assert.match(logs, /Hermes Webapp dev:/);
    const response = await fetch(`http://127.0.0.1:${port}/api/browser-plugins`, { signal: AbortSignal.timeout(2000) });
    assert.equal(response.status, 401, 'configured route must require cookie auth, not return unconfigured 404');
  } finally { child.kill('SIGKILL'); await closed; }
});
