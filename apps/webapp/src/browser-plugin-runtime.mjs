import { validateModule } from "./plugin-module.mjs";
export const validId = (id) =>
  typeof id === "string" &&
  /^[a-z][a-z0-9-]{0,79}$/.test(id) &&
  ![
    "constructor",
    "prototype",
    "hermes",
    "hermes-bots",
    "runtime-example",
  ].includes(id);
export async function sha256(bytes) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("");
}
export async function verifySnapshot(snapshot, expected) {
  if (
    snapshot.id !== expected.id ||
    snapshot.digest !== expected.digest ||
    !snapshot.approved ||
    !Array.isArray(snapshot.files) ||
    snapshot.files.length > 64
  )
    throw Error("Exact approved bundle required");
  const names = new Set();
  let total = 0;
  let source;
  for (const file of snapshot.files) {
    if (
      typeof file.name !== "string" ||
      names.has(file.name) ||
      !/^[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*\.[a-z0-9]+$/.test(file.name) ||
      typeof file.bytes !== "string"
    )
      throw Error("Invalid bundle asset");
    names.add(file.name);
    const bytes = Uint8Array.from(atob(file.bytes), (c) => c.charCodeAt(0));
    total += bytes.length;
    if (total > 16 * 1024 * 1024 || (await sha256(bytes)) !== file.sha256)
      throw Error("Bundle asset hash mismatch");
    if (file.name === "plugin.js")
      source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  }
  if (
    !source ||
    !names.has("browser-plugin.json") ||
    (await sha256(
      new TextEncoder().encode(
        JSON.stringify(
          snapshot.files.map(({ name, sha256 }) => ({ name, sha256 })),
        ),
      ),
    )) !== snapshot.digest
  )
    throw Error("Bundle digest mismatch");
  validateModule(source);
  return source;
}
/** Inventory never evaluates JS. Every activation is explicit, approval/hash checked,
 * scoped to principal+profile and guarded through every asynchronous continuation. */
async function deadline(promise, milliseconds, label) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(
          () =>
            reject(
              Error(
                `${label} timed out; JavaScript already evaluating cannot be cancelled. Reload the page for realm reset.`,
              ),
            ),
          milliseconds,
        );
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}
export class BrowserPluginRuntime {
  constructor(options) {
    this.options = options;
    this.records = new Map();
    this.generation = 0;
    this.scanId = 0;
    this.pendingScan = null;
    this.principal = null;
    this.profile = null;
  }
  reset() {
    this.generation++;
    this.scanId++;
    this.pendingScan = null;
    for (const record of this.records.values()) this.retire(record);
    this.records.clear();
    this.principal = null;
    this.profile = null;
  }
  retire(record) {
    record.ticket++;
    record.live = false;
    try {
      record.dispose?.();
    } catch (e) {
      console.error("Browser plugin cleanup failed", e);
    }
    record.dispose = null;
    this.options.drop(record.id);
  }
  alive(record, ticket) {
    return (
      this.records.get(record.id) === record &&
      record.ticket === ticket &&
      this.options.scope() === record.profile &&
      record.principal === this.principal
    );
  }
  publish(record, status, error) {
    this.options.publish({ ...record, status, error });
  }
  async list(profile) {
    const data = await this.options.request(
      "/api/browser-plugins?profile=" + encodeURIComponent(profile),
    );
    if (
      !data ||
      typeof data.principal !== "string" ||
      !data.principal ||
      data.profile !== profile ||
      !Array.isArray(data.plugins)
    )
      throw Error("Invalid plugin inventory");
    return data;
  }
  scan() {
    const profile = this.options.scope(), generation = this.generation;
    // Polls share in-flight work instead of continuously superseding slow
    // responses. Reset/profile changes can start a fresh, isolated scan.
    if (this.pendingScan?.profile === profile &&
        this.pendingScan.generation === generation)
      return this.pendingScan.promise;
    const pending = { profile, generation, promise: null };
    this.pendingScan = pending;
    pending.promise = this.scanOnce().finally(() => {
      if (this.pendingScan === pending) this.pendingScan = null;
    });
    return pending.promise;
  }
  async scanOnce() {
    const profile = this.options.scope(),
      generation = this.generation,
      scanId = ++this.scanId;
    try {
      const data = await this.list(profile);
      if (
        generation !== this.generation ||
        scanId !== this.scanId ||
        profile !== this.options.scope()
      )
        return;
      if (this.profile !== profile || this.principal !== data.principal) {
        this.reset();
        this.profile = profile;
        this.principal = data.principal;
      }
      const seen = new Set(),
        counts = new Map();
      for (const row of data.plugins)
        counts.set(row.id, (counts.get(row.id) || 0) + 1);
      for (const row of data.plugins) {
        if (
          !validId(row.id) ||
          counts.get(row.id) !== 1 ||
          (this.options.reserved(row.id) && !this.records.has(row.id))
        )
          continue;
        seen.add(row.id);
        const old = this.records.get(row.id);
        if (
          old &&
          old.digest === row.digest &&
          old.approved === row.approved &&
          !row.error
        )
          continue;
        if (old) this.retire(old);
        const record = {
          ...row,
          profile,
          principal: data.principal,
          ticket: 0,
          live: false,
          dispose: null,
        };
        this.records.set(row.id, record);
        this.publish(
          record,
          row.error ? "error" : "disabled",
          row.error ||
            (!row.approved
              ? "Owner approval required for this exact bundle"
              : undefined),
        );
      }
      for (const [id, record] of this.records) {
        if (!seen.has(id)) {
          this.retire(record);
          this.records.delete(id);
        }
      }
    } catch (error) {
      if (generation === this.generation && scanId === this.scanId &&
          profile === this.options.scope()) {
        this.reset();
        if (error?.status !== 404) this.options.report?.(error);
      }
    }
  }
  disable(id) {
    const record = this.records.get(id);
    if (!record) return;
    record.ticket++;
    record.live = false;
    try {
      record.dispose?.();
    } catch (e) {
      this.options.report?.(e);
    }
    record.dispose = null;
    this.publish(record, "disabled");
  }
  async enable(id) {
    const record = this.records.get(id);
    if (!record) return;
    this.disable(id);
    const ticket = ++record.ticket;
    const alive = () => this.alive(record, ticket);
    try {
      const check = async () => {
        const inventory = await this.list(record.profile);
        if (!alive()) throw Error("Plugin activation scope expired");
        if (inventory.principal !== record.principal) {
          this.reset();
          throw Error("Browser plugin principal changed");
        }
        const row = inventory.plugins.find((r) => r.id === id);
        if (!row?.approved || row.digest !== record.digest || row.error)
          throw Error("Owner approval required for current exact bundle");
      };
      await check();
      if (!alive()) return;
      const snapshot = await this.options.request(
        `/api/browser-plugins/${id}/${record.digest}?profile=${encodeURIComponent(record.profile)}`,
      );
      if (!alive()) return;
      if (
        snapshot.principal !== record.principal ||
        snapshot.profile !== record.profile
      ) {
        this.reset();
        throw Error("Plugin principal/profile changed");
      }
      const source = await verifySnapshot(snapshot, record);
      if (!alive()) return;
      await check();
      if (!alive()) return;
      // Cancellation can prevent an import from STARTING, never cancel JS already
      // evaluating (including top-level await). This is trusted code, not a sandbox.
      const module = await deadline(
        this.options.evaluate(source, record, alive),
        this.options.evaluationTimeoutMs || 10000,
        "Plugin module evaluation",
      );
      if (!alive()) return;
      if (
        module?.default?.id !== id ||
        typeof module.default.register !== "function"
      )
        throw Error("Plugin default export id/register mismatch");
      record.live = true;
      const dispose = await deadline(
        this.options.activate(record, module, () => alive() && record.live),
        this.options.evaluationTimeoutMs || 10000,
        "Plugin registration",
      );
      if (!alive() || !record.live) {
        dispose?.();
        return;
      }
      record.dispose = dispose;
      this.publish(record, "loaded");
    } catch (error) {
      if (alive()) {
        record.live = false;
        try {
          record.dispose?.();
        } catch {}
        record.dispose = null;
        this.publish(
          record,
          "error",
          error instanceof Error ? error.message : String(error),
        );
        this.options.report?.(error);
      }
    }
  }
}
