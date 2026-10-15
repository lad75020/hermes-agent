# Implementation-session verification

Performed on 2026-10-15 in `/Volumes/WDBlack4TB/.hermes/hermes-agent` using existing root npm dependencies and the existing `venv/bin/python`. No npm install, root dependency/lockfile edit, commit, push, service installation, or model prompt was performed.

## CSS follow-up (2026-10-15)

The parent verified typecheck, all 16 tests, production build and the previous Chrome smoke outside the sandbox after adding test storage globals and adapter `getRecentLogs`. However, `.scratch/browser-smoke.png` showed a broken white layout, so that smoke result did not certify visual rendering.

The CSS cause was plugin order: the `browser-boundaries` pre-transform appended `@source` after Tailwind's pre-transform had already run. The built renderer CSS contained a literal `@source` and lacked the full renderer utility set. Moving `browser-boundaries` before `tailwindcss()` processes the Desktop source directive without editing Desktop. The resulting renderer CSS is 388,467 bytes (previously about 146 KB). Static parsing of the built CSS confirms `.flex { display: flex }`, `.flex-col { flex-direction: column }`, `.w-screen { width: 100vw }`, `.h-screen { height: 100vh }`, and no unprocessed `@source`.

This follow-up reran build, typecheck and all 16 tests successfully. The renderer integration now additionally waits for the shared `$gatewayState` to be `open` and for `CONNECTING` to disappear; both pass. The old screenshot could capture REST history before connection/overlay completion. No browser runtime connection fix was inferred or added from that snapshot alone.

The smoke script now observes the renderer's real socket for `gateway.ready` and a successful RPC reply, waits for the connecting overlay to unmount, and records loaded stylesheet URLs/rule counts, theme variables, shell/composer computed geometry and RPC diagnostics in `.scratch/browser-diagnostics.json`. It asserts flex layout, viewport coverage, resolved theme values/background and usable composer size/position. Reduced motion makes the screenshot deterministic. It saves diagnostics and the chat screenshot even when connection waiting fails.

**Parent acceptance: strengthened Chrome smoke passes outside the Codex sandbox.** The parent inspected the corrected screenshot: sidebar, tabs, full-width composer and themed shell render without the previous overlapping layout. Computed shell is 1440×1000 with flex-column layout; composer width is 1158 pixels. Authentication, real ASGI RPC replies, removal of CONNECTING, and Appearance navigation pass with no page exceptions. Playwright replaces WebSocket construction, so RPC observations are collected at the intercepted socket bridge rather than by subclassing the browser constructor. External fonts are deliberately blocked by the isolated smoke; fallback fonts render.

Desktop preservation rechecked: 4,081 SHA-256 fingerprints match the existing baseline, tracked Desktop diff is empty, and its non-ignored untracked inventory is unchanged. All follow-up edits are under `apps/webapp`; no dependency install or root lockfile change.

## Passing checks

- `npm --prefix apps/webapp run build`: production Vite build of the actual Desktop renderer. Outputs are confined to `apps/webapp/dist` (about 46 MB, 1,060 files). Existing Desktop plugin chunking warnings remain; no build error.
- `npm --prefix apps/webapp run typecheck`: passes for browser TypeScript and its imported renderer/shared source graph. Supported core bridge methods additionally satisfy their Desktop types before the compatibility cast.
- `npm --prefix apps/webapp test`: 8 Node tests plus 8 Vitest tests, all passing. Node includes 7 proxy/path/configuration tests with mocked HTTP/socket streams and one multi-step integration against the actual Hermes ASGI app.
- Real ASGI integration: rejects unauthenticated config/session/filesystem/identity/ticket calls; rejects incorrect password; verifies bundled BasicAuthProvider login and HttpOnly cookies; reads profiles, config and stored sessions; round-trips a reversible setting; mints a public ticket; receives `gateway.ready`; runs `session.list`; rejects replay of the consumed ticket; logs out and verifies loss of access. No inference request.
- Actual renderer DOM integration: mounts `apps/desktop/src/main.tsx` through the browser adapter and browser overlays, connects its shared gateway client to real in-process ASGI WebSocket handlers, and requires the saved **Browser smoke history** title, an open shared gateway state, and disappearance of `CONNECTING`. Test emulates browser geometry APIs; jsdom reports missing canvas rendering. This is not a visual browser test.
- `node --check` for the service and runnable JavaScript scripts; `git diff --check`.
- `node apps/webapp/scripts/verify-desktop.mjs`: 4,081 SHA-256 fingerprints match the pre-implementation tracked/non-ignored Desktop inventory. Desktop tracked diff is empty and its untracked inventory is unchanged. The app does not run Desktop's build scripts or write ignored Desktop outputs.

The ASGI fixture substitutes package provisioning/bootstrap and the platform-default Hermes home only. The former avoids mutating the operator's install/update state; the latter is necessary because a fixture nested inside the normal Hermes root would otherwise share its profile roots. Authentication, routes, ticket consumption, JSON-RPC dispatcher and SQLite persistence remain real. Test homes and logs live under `.scratch`.

## Checks blocked by this session's environment

- Parent live TCP check passes outside the Codex sandbox: real loopback service serves the production index, preserves an upstream 401, forwards cookies and profile query, and rejects a hostile Origin. This used a synthetic upstream and does not certify a complete authenticated production deployment. No service is left running or installed.
- Backend CLI: isolated `hermes serve --host 127.0.0.1 --port 8642` is blocked by the operator installation's active source update/install lock and unwritable installation state. The update was not altered.
- Browser smoke: completed by the parent outside the Codex sandbox with layout assertions and screenshot inspection, as recorded above.
- Canonical Python runner: `scripts/run_tests.sh tests/tui_gateway/test_onboarding_run_rpc.py` attempted to select its required test environment, then failed initializing the protected `/Users/laurent/.cache/uv` cache with `Operation not permitted`. No bare pytest fallback or package installation was used.
- Requested scratch location `/Volumes/WDBlack4TB/.hermes/cache/scratch` is outside this sandbox's writable roots. Creation was denied; task scratch/TMPDIR instead uses `apps/webapp/.scratch`.

## Pre-existing parent change outside this app

`tui_gateway/methods_onboarding.py`: adds `from pathlib import Path`. Before this fix, importing the real dispatcher crashed at the existing evaluated annotation `tuple[Path, ...]`; `git log -S` traces that annotation to the onboarding due-stamp change. The import crash was observed before the fix, and the real dispatcher/WebSocket integration succeeds after it. This parent change was already present before the CSS follow-up and was left untouched. No Desktop file was changed.

## Remaining deployment acceptance

Configure the operator's authenticated backend using the README, then verify the deployed two-service URL: login, history, profile switching, a reversible settings write, and WebSocket reconnection. The fixture/browser and separate TCP checks have passed; production credentials, service installation and remote HTTPS deployment were not changed. Model-backed chat streaming uses the original renderer/transport but was not exercised with a paid model turn. Native capabilities and browser-only limitations are documented in the README capability matrix.
