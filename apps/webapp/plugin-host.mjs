// Trusted in-app code admission, NOT a JavaScript sandbox.
import fs from "node:fs/promises";
import { constants } from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import http from "node:http";
import https from "node:https";
import { validateModule } from "./src/plugin-module.mjs";
const hash = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
export function validId(id) {
  return (
    typeof id === "string" &&
    /^[a-z][a-z0-9-]{0,79}$/.test(id) &&
    ![
      "constructor",
      "prototype",
      "hermes",
      "hermes-bots",
      "runtime-example",
    ].includes(id)
  );
}
function requireId(id) {
  if (!validId(id)) throw Error("Invalid or reserved plugin/profile id");
}
async function noLinks(file) {
  const absolute = path.resolve(file);
  let current = path.parse(absolute).root;
  for (const part of absolute.slice(current.length).split(path.sep)) {
    current = path.join(current, part);
    if ((await fs.lstat(current)).isSymbolicLink())
      throw Error("Symlink forbidden");
  }
  return absolute;
}
async function owner(file, directory = false) {
  await noLinks(file);
  const s = await fs.stat(file);
  if (
    s.uid !== process.getuid() ||
    (s.mode & 0o077) !== 0 ||
    (directory ? !s.isDirectory() : !s.isFile())
  )
    throw Error("Owner-only file/directory required");
}
export async function loadConfig(file) {
  await owner(file);
  const cfg = JSON.parse(await fs.readFile(file, "utf8"));
  if (
    !path.isAbsolute(cfg.store) ||
    !cfg.profiles ||
    typeof cfg.profiles !== "object"
  )
    throw Error("Invalid plugin config");
  await owner(cfg.store, true);
  for (const [profile, roots] of Object.entries(cfg.profiles)) {
    requireId(profile);
    if (!Array.isArray(roots)) throw Error("Invalid roots");
    for (const root of roots) {
      if (
        !path.isAbsolute(root.path) ||
        !["standalone", "unified"].includes(root.layout)
      )
        throw Error("Explicit absolute roots required");
      await noLinks(root.path);
    }
  }
  return cfg;
}
async function approvals(cfg) {
  await owner(cfg.store, true);
  try {
    const p = path.join(cfg.store, "approvals.json");
    await owner(p);
    return JSON.parse(await fs.readFile(p, "utf8"));
  } catch (e) {
    if (e.code === "ENOENT") return {};
    throw e;
  }
}
async function writeApprovals(cfg, value) {
  await owner(cfg.store, true);
  const tmp = path.join(cfg.store, `approval-${crypto.randomUUID()}.json`);
  await fs.writeFile(tmp, JSON.stringify(value, null, 2) + "\n", {
    flag: "wx",
    mode: 0o600,
  });
  await fs.rename(tmp, path.join(cfg.store, "approvals.json"));
}
// Pin each directory before opening its child. O_NOFOLLOW on only the final
// path component is insufficient against a directory-swap/symlink race.
// This isolated candidate intentionally requires Linux /proc/self/fd.
async function openPinned(file, flags = constants.O_RDONLY) {
  const absolute = path.resolve(file),
    parts = absolute.split(path.sep).filter(Boolean);
  let handle = await fs.open("/", constants.O_RDONLY | constants.O_DIRECTORY);
  try {
    for (let index = 0; index < parts.length; index++) {
      const next = await fs.open(
        `/proc/self/fd/${handle.fd}/${parts[index]}`,
        constants.O_NOFOLLOW |
          (index === parts.length - 1
            ? flags
            : constants.O_RDONLY | constants.O_DIRECTORY),
      );
      await handle.close();
      handle = next;
    }
    return handle;
  } catch (error) {
    await handle.close();
    throw error;
  }
}
async function readExact(file) {
  await noLinks(file);
  // Do not block a libuv worker opening a FIFO before fstat can reject it.
  // Pin/no-follow protects swaps; nonblocking has no effect on regular files.
  const handle = await openPinned(file, constants.O_RDONLY | constants.O_NONBLOCK);
  try {
    const before = await handle.stat();
    if (!before.isFile() || before.size > 8 * 1024 * 1024)
      throw Error("Plugin file size/type rejected");
    const bytes = await handle.readFile();
    const after = await handle.stat();
    await noLinks(file);
    const current = await fs.stat(file);
    if (
      before.ino !== current.ino ||
      before.dev !== current.dev ||
      before.size !== after.size ||
      before.mtimeMs !== after.mtimeMs ||
      before.ctimeMs !== after.ctimeMs ||
      before.mtimeMs !== current.mtimeMs ||
      before.ctimeMs !== current.ctimeMs ||
      before.size !== current.size
    )
      throw Error("Plugin changed during snapshot");
    return bytes;
  } finally {
    await handle.close();
  }
}
function rootsFor(cfg, profile) {
  requireId(profile);
  if (!Object.hasOwn(cfg.profiles, profile))
    throw Object.assign(Error("Profile not configured"), { status: 404 });
  return cfg.profiles[profile];
}
async function locate(cfg, profile, id) {
  requireId(id);
  const found = [];
  for (const root of rootsFor(cfg, profile)) {
    const base = path.join(
      root.path,
      id,
      root.layout === "unified" ? "desktop" : "",
    );
    try {
      await noLinks(base);
      await fs.stat(path.join(base, "browser-plugin.json"));
      found.push(base);
    } catch (e) {
      if (e.code !== "ENOENT") throw e;
    }
  }
  if (found.length !== 1)
    throw Error(found.length ? "Duplicate plugin id" : "Plugin not found");
  return found[0];
}
export async function snapshot(cfg, profile, id) {
  const base = await locate(cfg, profile, id),
    metaBytes = await readExact(path.join(base, "browser-plugin.json"));
  const meta = JSON.parse(metaBytes.toString("utf8"));
  if (
    meta.id !== id ||
    typeof meta.name !== "string" ||
    !meta.name.trim() ||
    meta.name.length > 120 ||
    meta.entry !== "plugin.js" ||
    !Array.isArray(meta.assets) ||
    meta.assets.length > 62
  )
    throw Error("Invalid browser-plugin metadata");
  const names = ["browser-plugin.json", "plugin.js", ...meta.assets];
  if (new Set(names).size !== names.length) throw Error("Duplicate asset");
  for (const name of names) {
    if (
      typeof name !== "string" ||
      !/^[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*\.[a-z0-9]+$/.test(name) ||
      (!["plugin.js", "browser-plugin.json"].includes(name) &&
        !/\.(png|jpg|jpeg|webp|gif|woff2|css|json|txt)$/.test(name))
    )
      throw Error("Unsafe asset path/type");
  }
  const files = [];
  let total = 0;
  for (const name of names.sort()) {
    const bytes =
      name === "browser-plugin.json"
        ? metaBytes
        : await readExact(path.join(base, name));
    total += bytes.length;
    if (total > 16 * 1024 * 1024) throw Error("Bundle too large");
    files.push({ name, sha256: hash(bytes), bytes: bytes.toString("base64") });
  }
  validateModule(
    Buffer.from(
      files.find((f) => f.name === "plugin.js").bytes,
      "base64",
    ).toString("utf8"),
  );
  const digest = hash(
    JSON.stringify(files.map(({ name, sha256 }) => ({ name, sha256 }))),
  );
  const decision = (await approvals(cfg))[`${profile}:${id}`];
  const approved = decision === digest;
  return {
    id,
    name: meta.name,
    description:
      typeof meta.description === "string"
        ? meta.description.slice(0, 500)
        : "",
    digest,
    approved,
    removed: decision === "removed",
    files,
  };
}
export async function inventory(cfg, profile) {
  const ids = new Set();
  for (const root of rootsFor(cfg, profile)) {
    await noLinks(root.path);
    for (const dir of await fs.readdir(root.path, { withFileTypes: true })) {
      if (!validId(dir.name) || (!dir.isDirectory() && !dir.isSymbolicLink()))
        continue;
      if (dir.isSymbolicLink()) {
        ids.add(dir.name);
        continue;
      }
      try {
        await fs.lstat(
          path.join(
            root.path,
            dir.name,
            root.layout === "unified" ? "desktop" : "",
            "browser-plugin.json",
          ),
        );
        ids.add(dir.name);
      } catch (error) {
        if (error.code !== "ENOENT") ids.add(dir.name);
      }
    }
  }
  const result = [],
    decisions = await approvals(cfg);
  for (const id of [...ids].sort()) {
    if (decisions[`${profile}:${id}`] === "removed") continue;
    try {
      const { files, removed, ...record } = await snapshot(cfg, profile, id);
      if (!removed) result.push(record);
    } catch (e) {
      result.push({ id, name: id, approved: false, error: e.message });
    }
  }
  return result;
}
export async function approve(cfg, profile, id, digest) {
  const snap = await snapshot(cfg, profile, id);
  if (!/^[a-f0-9]{64}$/.test(digest) || snap.digest !== digest)
    throw Error("Reviewed digest mismatch");
  const a = await approvals(cfg);
  a[`${profile}:${id}`] = digest;
  await writeApprovals(cfg, a);
  if (!(await snapshot(cfg, profile, id)).approved)
    throw Error("Approval readback mismatch");
}
export async function revoke(cfg, profile, id) {
  rootsFor(cfg, profile);
  requireId(id);
  const a = await approvals(cfg);
  delete a[`${profile}:${id}`];
  await writeApprovals(cfg, a);
  if (Object.hasOwn(await approvals(cfg), `${profile}:${id}`))
    throw Error("Revocation readback mismatch");
}
export async function remove(cfg, profile, id) {
  rootsFor(cfg, profile);
  requireId(id);
  const a = await approvals(cfg);
  a[`${profile}:${id}`] = "removed";
  await writeApprovals(cfg, a);
  if ((await approvals(cfg))[`${profile}:${id}`] !== "removed")
    throw Error("Removal readback mismatch");
}
export async function cookieIdentity(req, res, config) {
  if (!req.headers.cookie) throw Error("A browser session cookie is required");
  const client = config.backend.protocol === "https:" ? https : http;
  const identity = await new Promise((resolve, reject) => {
    const upstream = client.request(
      new URL("/api/auth/me", config.backend),
      {
        method: "GET",
        headers: {
          host: config.backend.host,
          cookie: req.headers.cookie,
          accept: "application/json",
          "cache-control": "no-cache",
          "x-forwarded-host": config.publicOrigin.host,
          "x-forwarded-proto": config.publicOrigin.protocol.slice(0, -1),
        },
        timeout: config.pluginAuthTimeout || 5000,
      },
      (incoming) => {
        let text = "";
        incoming.on("data", (b) => {
          text += b;
          if (text.length > 16384)
            upstream.destroy(Error("Identity too large"));
        });
        incoming.on("error", reject);
        incoming.on("end", () => {
          try {
            if (
              incoming.statusCode !== 200 ||
              !String(incoming.headers["content-type"]).includes(
                "application/json",
              )
            )
              throw Error("Browser session rejected");
            const data = JSON.parse(text);
            if (
              typeof data.user_id !== "string" ||
              !data.user_id.trim() ||
              typeof data.provider !== "string" ||
              !data.provider.trim() ||
              data.provider === "loopback"
            )
              throw Error("Invalid browser principal");
            if (
              data.expires_at != null &&
              (!Number.isFinite(data.expires_at) ||
                data.expires_at <= Date.now() / 1000)
            )
              throw Error("Expired browser principal");
            if (incoming.headers["set-cookie"])
              res.setHeader("Set-Cookie", incoming.headers["set-cookie"]);
            resolve(hash(JSON.stringify([data.provider, data.user_id])));
          } catch (e) {
            reject(e);
          }
        });
      },
    );
    const deadline = setTimeout(
      () => upstream.destroy(Error("Identity deadline exceeded")),
      config.pluginAuthTimeout || 5000,
    );
    upstream.on("close", () => clearTimeout(deadline));
    upstream.on("error", reject);
    upstream.on("timeout", () => upstream.destroy(Error("Identity timeout")));
    upstream.end();
  });
  return identity;
}
export async function servePlugins(req, res, config, p) {
  const send = (status, value) => {
    res.writeHead(status, {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      Vary: "Cookie",
      "X-Content-Type-Options": "nosniff",
    });
    res.end(JSON.stringify(value));
  };
  if (!config.plugins)
    return send(404, { error: "Browser plugins not configured" });
  if (req.method !== "GET")
    return send(405, {
      error: "Only GET is supported; approval is owner CLI only",
    });
  // No request-selected roots, URLs, tokens or arbitrary query keys.
  const url = new URL(req.url, config.publicOrigin);
  if (
    [...url.searchParams.keys()].some((k) => k !== "profile") ||
    url.searchParams.getAll("profile").length > 1
  )
    return send(400, { error: "Invalid plugin query" });
  let principal;
  try {
    principal = await cookieIdentity(req, res, config);
  } catch {
    return send(401, { error: "Valid configured browser session required" });
  }
  const profile = url.searchParams.get("profile") || "default";
  try {
    if (p === "/api/browser-plugins")
      return send(200, {
        principal,
        profile,
        plugins: await inventory(config.plugins, profile),
      });
    const match =
      /^\/api\/browser-plugins\/([a-z][a-z0-9-]{0,79})\/([a-f0-9]{64})$/.exec(
        p,
      );
    if (!match) return send(404, { error: "Unknown browser plugin route" });
    const snap = await snapshot(config.plugins, profile, match[1]);
    if (!snap.approved || snap.digest !== match[2])
      return send(403, { error: "Exact bundle approval required" });
    return send(200, { principal, profile, ...snap });
  } catch (e) {
    return send(e.status || 403, { error: e.message });
  }
}
