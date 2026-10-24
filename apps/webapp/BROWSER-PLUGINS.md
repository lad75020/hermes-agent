# Browser Desktop-plugin host — isolated candidate

**Not deployed. Not a sandbox.** Enabling a reviewed plugin gives it the full authority of the signed-in application, including the SDK's existing backend actions. Approval is a local owner's hash decision, not a publisher signature or permission sandbox. Never approve code you do not trust with that account.

## Two independent gates

1. The local owner reviews exact source/asset bytes and approves the printed SHA-256 digest using the CLI. Backend plugin enablement is separate and untouched.
2. The signed-in browser user explicitly turns the plugin on in **Capabilities → Plugins → Desktop**. Inventory reads only JSON metadata; disabled/unapproved inventory never imports the module. Persisted native `pluginDecisions` cannot cause automatic evaluation. Browser records deliberately omit `packageName`, so backend `enablePackageDesktopHalf` cannot implicitly opt them in. Any actual handle activation still performs all approval/hash/principal/profile checks.

Enablement lasts only for the current page/profile incarnation. Page reload, manual **Reload desktop plugins** in the command palette, profile/connection change, logout, owner removal/revocation, source/asset changes or a failed scan dispose scoped contributions and require another explicit enable. New code needs renewed owner approval first. Bundled renderer plugins keep their original native initialization path.

## Operator configuration (instructions only; not installed by this work)

Both production (`node server.mjs`) and development (`npm run dev`) load the same validated opt-in configuration before listening. Opt-in uses `WEBAPP_PLUGIN_CONFIG=/absolute/path/browser-plugins.json`. With no variable, the plugin door returns 404 and does no discovery. Config must be a regular mode-0600 file owned by the service UID; the approval store must already exist as mode-0700 directory owned by that UID. All path components must be free of symlinks. This hardened candidate requires Linux `/proc/self/fd` for pinned-directory, no-follow reads; it is not certified for macOS/Windows servers.

```json
{
  "store": "/absolute/owner-controlled/browser-plugin-approvals",
  "profiles": {
    "default": [
      {"path": "/absolute/controlled/desktop-plugins", "layout": "standalone"},
      {"path": "/absolute/controlled/plugins", "layout": "unified"}
    ],
    "work": [{"path": "/absolute/controlled/work/plugins", "layout": "unified"}]
  }
}
```

Roots are explicit, fixed server-start configuration, never request-selected filesystem roots or profile paths. Standalone uses `<root>/<id>/browser-plugin.json` + `plugin.js`; unified uses `<root>/<id>/desktop/browser-plugin.json` + `plugin.js`. No browser manifest means no discovery (ordinary backend packages are ignored). Duplicate folder IDs across configured roots are rejected. IDs/profile keys are lowercase slugs `[a-z][a-z0-9-]{0,79}`; reserved/bundled IDs and prototype-dangerous names cannot become runtime registrations. Other profile naming conventions are unsupported by this candidate; requests fail closed, never normalize to another profile.

Each browser manifest is opt-in metadata, for example:

```json
{"id":"my-plugin","name":"My plugin","description":"What it adds","entry":"plugin.js","assets":["icon.png","styles/theme.css"]}
```

Use one **pre-bundled ESM entry**, externalizing only `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`, `react/jsx-dev-runtime`. Relative/absolute/remote imports, other bare imports, dynamic imports and `import.meta` are rejected by an actual ESM parser before evaluation, including imports hidden behind comments. No native disk loader is imported. SDK and React shims come from the original renderer's `installPluginSdk`/`sdkImportMap` singleton provider. A valid default export must match the manifest ID and expose `register(ctx)`.

Assets are explicitly listed and delivered only as part of the authenticated JSON byte snapshot; no directory browsing or arbitrary asset path endpoint is provided. Allowed non-entry asset extensions: png, jpg, jpeg, webp, gif, woff2, css, json, txt. ASCII paths only; no dot segments, encoded names, backslashes, URL schemes, duplicate paths or symlinks. Pinned final-file opens use `O_NOFOLLOW | O_NONBLOCK`, then verify a regular file before reading: FIFOs, sockets, directories and devices are not admitted. This avoids FIFO-open worker starvation; it is not a hard timeout/cancellation guarantee for arbitrary slow or stalled filesystems. Maximum 64 total files, 8 MiB/file, 16 MiB total decoded bytes. The sorted digest input is UTF-8 `JSON.stringify([{name,sha256},...])` for every deliverable file, **including the exact manifest, entry and all assets**. Each SHA is over exact file bytes. The JSON snapshot carries base64 bytes and per-file hashes. A plugin needing an asset can use its own authenticated inventory/snapshot fetch and convert its verified bytes to a Blob; there is no native filesystem/`import.meta.url` asset resolution compatibility promise.

## Review, approve, revoke, remove

Run from the webapp/payload folder, as the same local owner UID:

```sh
node scripts/browser-plugin-owner.mjs inspect /absolute/config.json default my-plugin
# Review plugin.js AND every manifest-listed asset. Copy the exact printed digest.
node scripts/browser-plugin-owner.mjs approve /absolute/config.json default my-plugin REVIEWED_SHA256
node scripts/browser-plugin-owner.mjs revoke /absolute/config.json default my-plugin
node scripts/browser-plugin-owner.mjs remove /absolute/config.json default my-plugin
```

`inspect` parses/hashes but never evaluates JS. `approve` re-reads the exact bundle, rejects a stale/mismatched digest, saves atomically, then reads back. CLI writes are serialized by an exclusive owner lock; a crash-left lock needs an owner investigation, not automatic lock bypass. `revoke` removes approval and leaves a disabled inventory row. `remove` writes a browser-only tombstone, hides the row and revokes delivery; it never deletes a backend package. A subsequent exact-hash `approve` restores discoverability but not browser enablement. There is no remote approval mutation route and the browser uninstall helper explicitly explains the owner-only operation.

This work did **not** approve, configure, load or remove any production plugin.

## Authentication, scope and lifecycle

Plugin routes run before the generic `/api/` proxy and development-source proxy. Only GET is supported. Host/Origin checks apply first; plugin WebSocket upgrades are rejected. Inventory and delivery use cookie-only GET `/api/auth/me` to the fixed configured backend, with no incoming Authorization header, native token, credential query or client-selected target. Redirects, wrong HTTP status/content type, malformed/missing `user_id`/`provider`, `provider: loopback`, expired identities, excessive responses, socket timeout and an absolute 5-second deadline all fail closed. Successful session-refresh `Set-Cookie` headers are preserved. There is no identity response cache; all plugin responses use `Cache-Control: no-store` and `Vary: Cookie`.

The server identifies the browser principal by a hash of provider/user ID. Owner approval is profile-scoped, applying to authenticated app users in that configured profile (not a separate per-user grant system). Browser activation/context storage are scoped to principal **and** current renderer API profile. `ctx.rest` uses the original plugin namespace/current-profile API path, not a newly invented backend bridge. Sockets retain the browser adapter's existing refusal/polling behavior.

Every enable does a fresh inventory check, fetches the exact approved immutable byte snapshot, validates **every hash in the browser before import**, then rechecks current inventory/principal/profile before starting evaluation. Generation/record tickets stop old scans/fetches from republishing or activating after disable, deletion, reload, profile change or logout. The original registry/createPluginContext owns actual contribution cleanup. A guarded context recursively refuses methods after disposal or scope change, including retained async registration attempts. Storage adds principal/profile prefixes to the native plugin namespace. Native notifications report an explicit limitation; native reveal and open/save pickers return false/null. Browser-safe SDK/UI contributions and backend APIs remain the original renderer implementations.

A visible inventory record contains the profile, trust/approval state and digest prefix. Load/registration errors go to the inventory and browser controls. Partial registration is disposed on error. Entry evaluation and async registration have a 10-second reporting deadline; the pending host continuation cannot later register after that error.

### Honest revocation limits

This is trusted same-realm JavaScript. A timeout/Promise.race, blob URL revocation, contribution disposal or hash revocation **cannot cancel JS already evaluating**, top-level await, arbitrary globals, captured SDK singleton methods, direct fetches, bare timers or other untracked side effects. Polling observes owner/source changes approximately every 2 seconds while the page runs; same-profile/generation polls share one in-flight scan, so responses slower than that interval still reconcile revocation, removal and errors. Reset/profile changes invalidate older scans; a stale failure cannot clear fresh inventory. Network latency or browser throttling can extend observation time. Approval has a point-in-time snapshot/check, not an atomic cross-network revocation guarantee. Concurrent owner changes after the last check cannot instantaneously retract code already admitted. **Use full page reload/close after revoke/removal to reset the realm; terminate/revoke the backend browser session when appropriate.** Code that can block the JS main thread is not sandboxed or forcibly terminable. Parser restrictions are an import-compatibility/admission policy, not containment against intentionally malicious approved code.

## Verification

From the candidate `source/` root, with isolated sibling tooling and the existing Hermes Python environment:

```sh
npm --prefix apps/webapp run typecheck
npm --prefix apps/webapp run build
npm --prefix apps/webapp test
WEBAPP_CHROMIUM=/usr/bin/chromium npm --prefix apps/webapp run smoke
node apps/webapp/scripts/plugin-smoke.mjs
```

`plugin-smoke` uses only headless system Chromium, actual production renderer bytes, actual SDK/React hooks and real plugin delivery server TCP calls. The browser requests are routed to an isolated ASGI harness using the genuine BasicAuthProvider/cookie gate/ticket and RPC implementations, not a production login. The optional synthetic plugin echo endpoint is **test-only**, with fixture-only backend enablement, and verifies actual `ctx.rest` namespace/profile transport. It does not certify backend plugin package installation or a production plugin API. No model prompt is submitted.

Tests exercise disabled/unapproved no-evaluation, reviewed UI enable, React singleton hooks in an actual settings contribution, native refusals, timers/disposal, retained context guard, changed-hash invalidation, renewed approval, revoke, removed manifest, actual SDK-driven profile switch, scoped fixture REST, partial-register failure/error inventory, keyboard command-palette reload, and stale scan/fetch cancellation at every activation network stage. Source security tests also exercise sustained slower-than-poll inventory success/failure, late reset/profile scan completion, killable-child FIFO manifest/entry/asset refusal, socket/directory refusal and a launched development config/auth route, alongside owner CLI/readback, removal tombstones, unified packages, duplicate/reserved IDs, import rejection, cookie-only auth/redirect/timeout/cache behavior, pinned directory-swap rejection and unchanged backend packages.

See the artifact `evidence/` logs and `verification-results.json` for actual command exits. The existing compact composer is tested at its current >=32px height, not an obsolete 60px multiline assumption. A command-palette pointer interception was observed; the verified reload path uses its normal keyboard selection/Enter. Synthetic fixtures, caches, node_modules, approval stores, cookies and generated homes are excluded from the archive. No service/template installation, production restart, configuration update or deployment is performed.
