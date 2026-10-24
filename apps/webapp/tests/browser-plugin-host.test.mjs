import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { once } from "node:events";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
const exec = promisify(execFile);
import { configuration, createService } from "../server.mjs";
const mod = await import("../plugin-host.mjs").catch(() => ({}));
test("browser plugin host exports controlled snapshot and approval operations", () => {
  assert.equal(typeof mod.snapshot, "function");
  assert.equal(typeof mod.approve, "function");
});
if (mod.snapshot) {
  const tmp = await fs.mkdtemp(
    path.join(process.env.TMPDIR || os.tmpdir(), "plugin-tests-"),
  );
  const root = path.join(tmp, "plugins"),
    store = path.join(tmp, "store");
  await fs.mkdir(root);
  await fs.mkdir(store, { mode: 0o700 });
  await fs.mkdir(path.join(root, "sample"));
  const pkg = path.join(root, "sample");
  const entry = path.join(pkg, "plugin.js");
  const code =
    "import React from 'react'; import { definePlugin } from '@hermes/plugin-sdk'; globalThis.pluginEvaluated=true; export default { id:'sample',register(ctx) {} };";
  await fs.writeFile(entry, code);
  await fs.writeFile(
    path.join(pkg, "browser-plugin.json"),
    JSON.stringify({
      id: "sample",
      name: "Sample",
      entry: "plugin.js",
      assets: ["icon.png"],
    }),
  );
  await fs.writeFile(path.join(pkg, "icon.png"), "fixture");
  const config = {
    profiles: {
      default: [{ path: root, layout: "standalone" }],
      work: [{ path: root, layout: "standalone" }],
    },
    store,
  };
  test("snapshot hashes all exact deliverable bytes and requires exact reviewed digest", async () => {
    const a = await mod.snapshot(config, "default", "sample");
    assert.equal(a.approved, false);
    assert.equal(a.files.length, 3);
    await assert.rejects(
      mod.approve(config, "default", "sample", "0".repeat(64)),
      /digest/i,
    );
    await mod.approve(config, "default", "sample", a.digest);
    assert.equal(
      (await mod.snapshot(config, "default", "sample")).approved,
      true,
    );
    assert.equal(
      (await mod.snapshot(config, "work", "sample")).approved,
      false,
    );
    await fs.writeFile(path.join(pkg, "icon.png"), "changed");
    assert.equal(
      (await mod.snapshot(config, "default", "sample")).approved,
      false,
    );
    await fs.writeFile(path.join(pkg, "icon.png"), "fixture");
  });
  test("rejects traversal, reserved ids, symlinks, undeclared and unsafe imports", async () => {
    for (const id of ["..", "%2e%2e", "constructor", "__proto__", "a/b"])
      await assert.rejects(mod.snapshot(config, "default", id));
    await fs.rename(entry, entry + ".save");
    await fs.symlink(entry + ".save", entry);
    await assert.rejects(mod.snapshot(config, "default", "sample"), /symlink/i);
    await fs.unlink(entry);
    await fs.rename(entry + ".save", entry);
    for (const src of [
      "import 'https://evil/a.js'; export default {}",
      "import './other.js'; export default {}",
      "import('react'); export default {}",
      "import.meta.url; export default {}",
      "export * from 'node:fs'",
      "import x from /* hi */ 'unknown'",
      "import('https://evil/'+Date.now())",
    ]) {
      await fs.writeFile(entry, src);
      await assert.rejects(
        mod.snapshot(config, "default", "sample"),
        /import|module/i,
      );
    }
    await fs.writeFile(entry, code);
    const duplicate = {
      ...config,
      profiles: {
        default: [...config.profiles.default, ...config.profiles.default],
      },
    };
    await assert.rejects(
      mod.snapshot(duplicate, "default", "sample"),
      /duplicate/i,
    );
  });
  test("owner config permissions, unified opt-in discovery and pinned directory race", async () => {
    const configPath = path.join(tmp, "host.json");
    await fs.writeFile(configPath, JSON.stringify(config), { mode: 0o600 });
    assert.equal((await mod.loadConfig(configPath)).store, store);
    await fs.chmod(configPath, 0o644);
    await assert.rejects(mod.loadConfig(configPath), /Owner-only/);
    await fs.chmod(configPath, 0o600);
    await fs.mkdir(path.join(root, "backend-only"));
    assert.equal(
      (await mod.inventory(config, "default")).some(
        (r) => r.id === "backend-only",
      ),
      false,
    );
    const outside = path.join(tmp, "outside");
    await fs.mkdir(outside);
    await fs.writeFile(
      path.join(outside, "browser-plugin.json"),
      "DO-NOT-READ-OUTSIDE",
    );
    const original = fs.open;
    let swapped = false,
      readOutside = false;
    fs.open = async function (file, ...args) {
      if (
        !swapped &&
        String(file).startsWith("/proc/self/fd/") &&
        String(file).endsWith("/sample")
      ) {
        swapped = true;
        await fs.rename(pkg, pkg + ".saved");
        await fs.symlink(outside, pkg);
      }
      const handle = await original.call(this, file, ...args);
      const read = handle.readFile.bind(handle);
      handle.readFile = async (...a) => {
        const bytes = await read(...a);
        if (bytes.toString().includes("DO-NOT-READ-OUTSIDE"))
          readOutside = true;
        return bytes;
      };
      return handle;
    };
    try {
      await assert.rejects(mod.snapshot(config, "default", "sample"));
      assert.equal(swapped, true);
      assert.equal(readOutside, false);
    } finally {
      fs.open = original;
      if (swapped) {
        await fs.unlink(pkg);
        await fs.rename(pkg + ".saved", pkg);
      }
    }
    const unified = path.join(tmp, "unified");
    await fs.mkdir(path.join(unified, "unified-sample", "desktop"), {
      recursive: true,
    });
    await fs.writeFile(
      path.join(unified, "unified-sample", "desktop", "browser-plugin.json"),
      JSON.stringify({
        id: "unified-sample",
        name: "Unified",
        entry: "plugin.js",
        assets: [],
      }),
    );
    await fs.writeFile(
      path.join(unified, "unified-sample", "desktop", "plugin.js"),
      "export default {id:'unified-sample',register(){}}",
    );
    const c = {
      ...config,
      profiles: { default: [{ path: unified, layout: "unified" }] },
    };
    assert.equal((await mod.inventory(c, "default"))[0].approved, false);
  });
  test("owner CLI exact approval, removal tombstone and package preservation", async () => {
    const configPath = path.join(tmp, "host.json"),
      cli = new URL("../scripts/browser-plugin-owner.mjs", import.meta.url)
        .pathname;
    const run = (command, digest) =>
      exec(process.execPath, [
        cli,
        command,
        configPath,
        "default",
        "sample",
        ...(digest ? [digest] : []),
      ]);
    const info = JSON.parse((await run("inspect")).stdout);
    await assert.rejects(run("approve", "0".repeat(64)));
    await run("approve", info.digest);
    assert.equal(
      (await mod.snapshot(config, "default", "sample")).approved,
      true,
    );
    await run("remove");
    assert.equal(
      (await mod.inventory(config, "default")).some((r) => r.id === "sample"),
      false,
    );
    assert.equal((await fs.stat(entry)).isFile(), true);
    await run("approve", info.digest);
    assert.equal(
      (await mod.snapshot(config, "default", "sample")).approved,
      true,
    );
    await run("revoke");
    assert.equal(
      (await mod.snapshot(config, "default", "sample")).approved,
      false,
    );
  });
  test("TCP delivery cookie authentication, no redirects/cache/credential bypass and revocation", async (t) => {
    const seen = [];
    let authMode = "valid";
    const backend = http.createServer((req, res) => {
      seen.push(req.headers);
      if (authMode === "timeout") return;
      if (authMode === "redirect") {
        res.writeHead(302, { location: "/login" });
        return res.end();
      }
      if (req.headers.cookie !== "session=fixture") {
        res.writeHead(401);
        return res.end("{}");
      }
      res.setHeader("Content-Type", "application/json");
      res.setHeader("Set-Cookie", "session=fixture; HttpOnly; Path=/");
      res.end(
        JSON.stringify(
          authMode === "malformed"
            ? { provider: "basic" }
            : {
                provider: authMode === "loopback" ? "loopback" : "basic",
                user_id: "fixture-owner",
                expires_at: Date.now() / 1000 + 60,
              },
        ),
      );
    });
    backend.listen(0, "127.0.0.1");
    await once(backend, "listening");
    t.after(() => backend.closeAllConnections());
    t.after(() => backend.close());
    const cfg = configuration({
      WEBAPP_BACKEND: `http://127.0.0.1:${backend.address().port}`,
      WEBAPP_PUBLIC_ORIGIN: "http://localhost:8080",
    });
    cfg.plugins = config;
    cfg.pluginAuthTimeout = 40;
    const service = createService(cfg);
    service.listen(0, "127.0.0.1");
    await once(service, "listening");
    t.after(() => service.closeAllConnections());
    t.after(() => service.close());
    const request = (p, headers = {}) =>
      new Promise((resolve, reject) => {
        const req = http.get(
          {
            hostname: "127.0.0.1",
            port: service.address().port,
            path: p,
            headers: { host: "localhost:8080", ...headers },
          },
          (res) => {
            let body = "";
            res.on("data", (b) => (body += b));
            res.on("end", () =>
              resolve({
                status: res.statusCode,
                headers: new Headers(
                  Object.entries(res.headers).map(([k, v]) => [
                    k,
                    Array.isArray(v) ? v.join("\n") : v,
                  ]),
                ),
                body,
              }),
            );
          },
        );
        req.on("error", reject);
      });
    const url = "/api/browser-plugins?profile=default";
    assert.equal(
      (await request(url, { authorization: "Bearer fixture" })).status,
      401,
    );
    const good = await request(url, {
      cookie: "session=fixture",
      authorization: "Bearer ignore",
    });
    assert.equal(good.status, 200);
    assert.equal(good.headers.get("cache-control"), "no-store");
    assert.match(good.headers.get("set-cookie"), /session/);
    assert.ok(seen.every((h) => !h.authorization));
    assert.equal(JSON.parse(good.body).plugins.length, 1);
    for (const mode of ["redirect", "malformed", "loopback", "timeout"]) {
      authMode = mode;
      assert.equal(
        (await request(url, { cookie: "session=fixture" })).status,
        401,
        mode,
      );
    }
    authMode = "valid";
    assert.equal(
      (await request(url, { cookie: "session=fixture", origin: "http://evil" }))
        .status,
      403,
    );
    assert.equal(
      (await request(url + "&root=/etc", { cookie: "session=fixture" })).status,
      400,
    );
    assert.equal(
      (
        await request("/api/browser-plugins?profile=missing", {
          cookie: "session=fixture",
        })
      ).status,
      404,
    );
    const snap = await mod.snapshot(config, "default", "sample");
    await mod.approve(config, "default", "sample", snap.digest);
    const delivery = `/api/browser-plugins/sample/${snap.digest}?profile=default`;
    assert.equal(
      (await request(delivery, { cookie: "session=fixture" })).status,
      200,
    );
    await mod.revoke(config, "default", "sample");
    assert.equal(
      (await request(delivery, { cookie: "session=fixture" })).status,
      403,
    );
    assert.equal((await fs.stat(entry)).isFile(), true);
  });
}
