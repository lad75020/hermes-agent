import test from "node:test";
import assert from "node:assert/strict";
const mod = await import("../src/browser-plugin-runtime.mjs").catch(() => ({}));
test("browser runtime exports a generation-safe host", () =>
  assert.equal(typeof mod.BrowserPluginRuntime, "function"));
if (mod.BrowserPluginRuntime) {
  const crypto = await import("node:crypto");
  const source =
    "import React from 'react'; export default {id:'sample',register(){}}";
  const files = [
    {
      name: "browser-plugin.json",
      bytes: Buffer.from(
        JSON.stringify({ id: "sample", entry: "plugin.js", assets: [] }),
      ).toString("base64"),
    },
    { name: "plugin.js", bytes: Buffer.from(source).toString("base64") },
  ].map((f) => ({
    ...f,
    sha256: crypto
      .createHash("sha256")
      .update(Buffer.from(f.bytes, "base64"))
      .digest("hex"),
  }));
  const digest = crypto
    .createHash("sha256")
    .update(JSON.stringify(files.map(({ name, sha256 }) => ({ name, sha256 }))))
    .digest("hex");
  function setup() {
    let scope = "default",
      approved = true,
      exists = true,
      evaluated = 0,
      activated = 0,
      disposed = 0,
      deferred = null;
    const rows = [];
    const entry = { id: "sample", name: "Sample", digest, approved: true };
    const runtime = new mod.BrowserPluginRuntime({
      scope: () => scope,
      request: async (route) => {
        if (deferred) await deferred;
        if (route.includes("/sample/"))
          return {
            principal: "owner",
            profile: scope,
            ...entry,
            approved,
            files,
          };
        return {
          principal: "owner",
          profile: scope,
          plugins: exists ? [{ ...entry, approved }] : [],
        };
      },
      publish: (r) => rows.push(r),
      drop: () => {},
      reserved: () => false,
      evaluate: async () => {
        evaluated++;
        return { default: { id: "sample", register() {} } };
      },
      activate: async (r, m, alive) => {
        assert.ok(alive());
        activated++;
        return () => {
          disposed++;
        };
      },
    });
    return {
      runtime,
      rows,
      get evaluated() {
        return evaluated;
      },
      get activated() {
        return activated;
      },
      get disposed() {
        return disposed;
      },
      scope: (v) => (scope = v),
      approve: (v) => (approved = v),
      exists: (v) => (exists = v),
      defer: (v) => (deferred = v),
    };
  }
  test("inventory and unapproved enable never evaluate; enabled disable reload disposal", async () => {
    const t = setup();
    await t.runtime.scan();
    assert.equal(t.evaluated, 0);
    t.approve(false);
    await t.runtime.enable("sample");
    assert.equal(t.evaluated, 0);
    t.approve(true);
    await t.runtime.scan();
    await t.runtime.enable("sample");
    assert.equal(t.activated, 1);
    t.runtime.disable("sample");
    assert.equal(t.disposed, 1);
    await t.runtime.enable("sample");
    assert.equal(t.evaluated, 2);
    t.exists(false);
    await t.runtime.scan();
    assert.equal(t.disposed, 2);
  });
  test("stale fetch after disable or profile switch cannot evaluate", async () => {
    for (const change of ["disable", "scope", "logout"]) {
      const t = setup();
      await t.runtime.scan();
      let release;
      t.defer(new Promise((r) => (release = r)));
      const pending = t.runtime.enable("sample");
      if (change === "disable") t.runtime.disable("sample");
      if (change === "scope") t.scope("work");
      if (change === "logout") t.runtime.reset();
      release();
      await pending;
      assert.equal(t.evaluated, 0, change);
    }
  });
  test("changed bytes fail digest before evaluation and reserved IDs never inventory", async () => {
    const t = setup();
    const saved = files[1].bytes;
    files[1].bytes = Buffer.from("globalThis.bad=true").toString("base64");
    await t.runtime.scan();
    await t.runtime.enable("sample");
    assert.equal(t.evaluated, 0);
    assert.equal(t.rows.at(-1).status, "error");
    files[1].bytes = saved;
    const r = setup();
    r.runtime.options.reserved = () => true;
    await r.runtime.scan();
    await r.runtime.enable("sample");
    assert.equal(r.evaluated, 0);
  });
  test("each in-flight activation stage is cancelled by disable, deletion, profile and logout", async () => {
    for (const stage of [1, 2, 3])
      for (const change of ["disable", "deletion", "profile", "logout"]) {
        const t = setup();
        await t.runtime.scan();
        const original = t.runtime.options.request;
        let count = 0,
          release,
          reached;
        const gate = new Promise((r) => (release = r)),
          ready = new Promise((r) => (reached = r));
        t.runtime.options.request = async (route) => {
          const result = await original(route);
          if (++count === stage) {
            reached();
            await gate;
          }
          return result;
        };
        const pending = t.runtime.enable("sample");
        await ready;
        if (change === "disable") t.runtime.disable("sample");
        if (change === "deletion") {
          t.exists(false);
          await t.runtime.scan();
        }
        if (change === "profile") {
          t.scope("work");
          await t.runtime.scan();
        }
        if (change === "logout") t.runtime.reset();
        release();
        await pending;
        assert.equal(t.evaluated, 0, `${stage}/${change}`);
      }
  });
  test("evaluation timeout reports error and late module cannot register", async () => {
    const t = setup();
    await t.runtime.scan();
    let release,
      settled = false;
    t.runtime.options.evaluationTimeoutMs = 5;
    t.runtime.options.evaluate = () => new Promise((r) => (release = r));
    const pending = t.runtime.enable("sample").then(() => (settled = true));
    try {
      await new Promise((r) => setTimeout(r, 40));
      assert.equal(
        settled,
        true,
        "activation must stop awaiting a hung module",
      );
      assert.match(t.rows.at(-1).error, /timed out/);
    } finally {
      release({ default: { id: "sample", register() {} } });
      await pending;
    }
    assert.equal(t.activated, 0);
  });
  test("revocation removes active plugin and stale scans cannot republish", async () => {
    const t = setup();
    await t.runtime.scan();
    await t.runtime.enable("sample");
    t.approve(false);
    await t.runtime.scan();
    assert.equal(t.disposed, 1);
    let release;
    t.defer(new Promise((r) => (release = r)));
    const scan = t.runtime.scan();
    t.runtime.reset();
    release();
    await scan;
    assert.equal(t.runtime.records.size, 0);
  });
}
