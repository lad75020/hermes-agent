import http from "node:http";
import { once } from "node:events";
import fs from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";
import { configuration, createService } from "../server.mjs";
import { snapshot, approve, revoke } from "../plugin-host.mjs";
export const fixtureSource = `import React from 'react';
import * as SDK from '@hermes/plugin-sdk';
const state=globalThis.__browserPluginFixture ||= {evaluations:0,registers:0,disposals:0,ticks:0};
state.evaluations++;
state.reactSame=React===(globalThis.__HERMES_REACT__.default ?? globalThis.__HERMES_REACT__);
state.sdkSame=SDK.host===globalThis.__HERMES_PLUGIN_SDK__.host;
function View(){const [count,setCount]=React.useState(0);return React.createElement('button',{id:'plugin-hook-button',onClick:()=>setCount(count+1)},'Plugin hook '+count)}
export default {id:'browser-fixture',name:'Browser fixture',register(ctx){state.ctx=ctx;state.registers++;ctx.onDispose(()=>{state.disposals++;console.log('BROWSER_PLUGIN_DISPOSED '+state.disposals)});ctx.setInterval(()=>state.ticks++,30);ctx.registerSettingsPage({id:'settings',title:'Browser fixture settings',render:()=>React.createElement(View)});ctx.rest('/echo').then(value=>state.rest=value).catch(error=>state.restError=error.message);state.native=Promise.all([ctx.os.revealPath('/not-a-real-path'),ctx.os.pickOpenPath(),ctx.os.pickSavePath()]).then(result=>state.nativeResult=result)}};`;
export async function startPluginFixture(root, call) {
  const dir = path.join(root, ".scratch/plugin-fixture"),
    plugins = path.join(dir, "plugins"),
    pkg = path.join(plugins, "browser-fixture"),
    store = path.join(dir, "store");
  await fs.mkdir(pkg, { recursive: true });
  await fs.mkdir(store, { recursive: true, mode: 0o700 });
  await fs.chmod(store, 0o700);
  await fs.rm(path.join(store, "approvals.json"), { force: true });
  const workHome = path.join(root, ".scratch/plugin-smoke-home/profiles/work");
  await fs.mkdir(workHome, { recursive: true });
  await fs.writeFile(
    path.join(workHome, "config.yaml"),
    "model:\n  default: webapp-smoke-model\n  provider: openai\nonboarding:\n  run: false\nplugins:\n  enabled: [browser-fixture]\n",
  );
  await fs.writeFile(
    path.join(pkg, "browser-plugin.json"),
    JSON.stringify({
      id: "browser-fixture",
      name: "Browser fixture",
      entry: "plugin.js",
      assets: [],
    }),
  );
  await fs.writeFile(path.join(pkg, "plugin.js"), fixtureSource);
  const config = {
    profiles: {
      default: [{ path: plugins, layout: "standalone" }],
      work: [{ path: plugins, layout: "standalone" }],
    },
    store,
  };
  const bridge = http.createServer(async (req, res) => {
    try {
      const result = await call({
        path: req.url,
        method: req.method,
        headers: req.headers,
      });
      res.writeHead(result.status, Object.fromEntries(result.headers));
      res.end(result.body);
    } catch (error) {
      res.writeHead(502);
      res.end(String(error));
    }
  });
  bridge.listen(0, "127.0.0.1");
  await once(bridge, "listening");
  const cfg = configuration({
    WEBAPP_BACKEND: `http://127.0.0.1:${bridge.address().port}`,
    WEBAPP_PUBLIC_ORIGIN: "http://hermes-webapp.localhost:8080",
  });
  cfg.plugins = config;
  const service = createService(cfg);
  service.listen(0, "127.0.0.1");
  await once(service, "listening");
  return {
    config,
    pkg,
    async approve() {
      const snap = await snapshot(config, "default", "browser-fixture");
      await approve(config, "default", "browser-fixture", snap.digest);
    },
    async revoke() {
      await revoke(config, "default", "browser-fixture");
    },
    async route(route) {
      const req = route.request();
      const headers = await req.allHeaders();
      headers.host = "hermes-webapp.localhost:8080";
      delete headers["content-length"];
      const result = await new Promise((resolve, reject) => {
        const request = http.request(
          {
            hostname: "127.0.0.1",
            port: service.address().port,
            path: new URL(req.url()).pathname + new URL(req.url()).search,
            headers,
            method: req.method(),
          },
          (res) => {
            let body = "";
            res.on("data", (b) => (body += b));
            res.on("end", () =>
              resolve({ status: res.statusCode, headers: res.headers, body }),
            );
          },
        );
        request.on("error", reject);
        request.end();
      });
      const outHeaders = { ...result.headers };
      delete outHeaders["content-length"];
      delete outHeaders["transfer-encoding"];
      if (Array.isArray(outHeaders["set-cookie"]))
        outHeaders["set-cookie"] = outHeaders["set-cookie"].join("\n");
      return route.fulfill({ ...result, headers: outHeaders });
    },
    async close() {
      service.closeAllConnections();
      bridge.closeAllConnections();
      await Promise.all([
        new Promise((r) => service.close(r)),
        new Promise((r) => bridge.close(r)),
      ]);
    },
  };
}
export async function exercisePlugin(page, fixture, root) {
  const state = () =>
    page.evaluate(() => {
      const s = globalThis.__browserPluginFixture;
      return s
        ? {
            evaluations: s.evaluations,
            registers: s.registers,
            disposals: s.disposals,
            reactSame: s.reactSame,
            sdkSame: s.sdkSame,
            ticks: s.ticks,
            nativeResult: s.nativeResult,
            rest: s.rest,
            restError: s.restError,
          }
        : null;
    });
  const open = async () => {
    await page.evaluate(() => {
      location.hash = "#/capabilities?tab=plugins&plugin=browser-fixture";
    });
    await page
      .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
      .waitFor({ timeout: 15000 });
  };
  await open();
  assert.equal(
    await state(),
    null,
    "Unapproved disabled inventory must not evaluate",
  );
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForTimeout(300);
  assert.equal(
    await state(),
    null,
    "Unapproved explicit enable must not evaluate",
  );
  await fixture.approve();
  await page.waitForTimeout(2400);
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture?.registers === 1,
  );
  let s = await state();
  assert.equal(s.reactSame, true);
  assert.equal(s.sdkSame, true);
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture?.nativeResult,
  );
  s = await state();
  assert.deepEqual(s.nativeResult, [false, null, null]);
  await page.waitForFunction(
    () =>
      globalThis.__browserPluginFixture?.rest ||
      globalThis.__browserPluginFixture?.restError,
  );
  console.log("PLUGIN REST DIAGNOSTIC", JSON.stringify(await state()));
  assert.deepEqual((await state()).rest, { profile: "default", fixture: true });
  await page.evaluate(() => {
    location.hash = "#/settings?tab=plugins&plugin=browser-fixture%3Asettings";
  });
  await page.locator("#plugin-hook-button").waitFor({ timeout: 15000 });
  await page.locator("#plugin-hook-button").click();
  assert.equal(
    await page.locator("#plugin-hook-button").innerText(),
    "Plugin hook 1",
  );
  await page.screenshot({
    path: path.join(root, ".scratch/plugin-react-settings.png"),
    fullPage: true,
  });
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.disposals === 1,
  );
  const tick = (await state()).ticks;
  await page.waitForTimeout(150);
  assert.equal((await state()).ticks, tick);
  assert.match(
    await page.evaluate(() => {
      try {
        globalThis.__browserPluginFixture.ctx.registerSettingsPage({
          id: "stale",
          title: "Stale",
          render: () => null,
        });
        return "unexpected";
      } catch (e) {
        return e.message;
      }
    }),
    /disposed/,
  );
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.registers === 2,
  );
  await fs.appendFile(
    path.join(fixture.pkg, "plugin.js"),
    "\n// code change requires renewed owner approval\n",
  );
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.disposals === 2,
    { timeout: 10000 },
  );
  const before = (await state()).evaluations;
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForTimeout(300);
  assert.equal((await state()).evaluations, before);
  await fixture.approve();
  await page.waitForTimeout(2200);
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.registers === 3,
  );
  await fixture.revoke();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.disposals === 3,
  );
  await fixture.approve();
  await page.waitForTimeout(2200);
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.registers === 4,
  );
  await fs.rename(
    path.join(fixture.pkg, "browser-plugin.json"),
    path.join(fixture.pkg, "metadata.removed"),
  );
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.disposals === 4,
  );
  assert.equal(
    (await fs.stat(path.join(fixture.pkg, "plugin.js"))).isFile(),
    true,
  );
  // Restore metadata, approve and explicitly enable again before profile change.
  await fs.rename(
    path.join(fixture.pkg, "metadata.removed"),
    path.join(fixture.pkg, "browser-plugin.json"),
  );
  await fixture.approve();
  await page.waitForTimeout(2200);
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.registers === 5,
  );
  await page.evaluate(() =>
    globalThis.__HERMES_PLUGIN_SDK__.host.newChat("work"),
  );
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.disposals === 5,
  );
  await page.waitForTimeout(2400);
  const prior = (await state()).evaluations;
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForTimeout(300);
  assert.equal(
    (await state()).evaluations,
    prior,
    "Default profile approval must not authorize work",
  );
  const workSnapshot = await snapshot(
    fixture.config,
    "work",
    "browser-fixture",
  );
  await approve(fixture.config, "work", "browser-fixture", workSnapshot.digest);
  await page.waitForTimeout(2200);
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.registers === 6,
  );
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.rest?.profile === "work",
  );
  assert.equal((await state()).rest.profile, "work");
  // A registration error must retire partial contributions and report in inventory.
  const failing = fixtureSource
    .replace("state.registers++;", "state.registers++;")
    .replace(
      "state.native=Promise.all",
      'throw Error("fixture register failure");state.native=Promise.all',
    );
  await fs.writeFile(path.join(fixture.pkg, "plugin.js"), failing);
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.disposals === 6,
  );
  const failureSnapshot = await snapshot(
    fixture.config,
    "work",
    "browser-fixture",
  );
  await approve(
    fixture.config,
    "work",
    "browser-fixture",
    failureSnapshot.digest,
  );
  await page.waitForTimeout(2200);
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.getByText("fixture register failure", { exact: true }).waitFor();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.disposals === 7,
  );
  await page.screenshot({
    path: path.join(root, ".scratch/plugin-error-inventory.png"),
    fullPage: true,
  });
  await fs.writeFile(path.join(fixture.pkg, "plugin.js"), fixtureSource);
  const restored = await snapshot(fixture.config, "work", "browser-fixture");
  await approve(fixture.config, "work", "browser-fixture", restored.digest);
  await page.waitForTimeout(2200);
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.registers === 8,
  );
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox").fill("Reload desktop plugins");
  await page
    .getByRole("option", { name: "Reload desktop plugins", exact: true })
    .waitFor();
  await page.keyboard.press("Enter");
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.disposals === 8,
  );
  await page.waitForTimeout(400);
  assert.equal(
    (await state()).registers,
    8,
    "Manual reload resets enablement without evaluation",
  );
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.registers === 9,
  );
  await page.evaluate(() =>
    globalThis.__HERMES_PLUGIN_SDK__.host.newChat("default"),
  );
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.disposals === 9,
  );
  await page.waitForTimeout(2200);
  await fixture.approve();
  await page.waitForTimeout(2200);
  await open();
  await page
    .getByRole("switch", { name: "Desktop: Browser fixture", exact: true })
    .click();
  await page.waitForFunction(
    () => globalThis.__browserPluginFixture.registers === 10,
  );
  console.log(
    "PLUGIN BROWSER: disabled and unapproved no evaluation; actual SDK/React hook mounted; native refusals; enable/disable timer disposal; stale ctx guard; changed hash invalidation; renewed approval; revoke; removal; actual profile switch; profile-scoped fixture REST; partial-register cleanup/error inventory all passed",
  );
}
