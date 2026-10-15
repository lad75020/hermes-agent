# Hermes browser application

A standalone browser build of the **actual Hermes Desktop renderer**. Build-time aliases read `../desktop/src` and `../shared/src`; nothing is copied into, generated in, or changed under `apps/desktop`. The deployed service needs Node and this app's `dist/` and `server.mjs`; it does not run Electron. It requires an existing Hermes backend with **dashboard session authentication enabled**.

## Run

Use the existing repository-root npm dependencies. Do not run `npm install` in this folder. Commands below run from the repository root:

```sh
mkdir -p apps/webapp/.scratch
export TMPDIR="$PWD/apps/webapp/.scratch"
npm --prefix apps/webapp run build
WEBAPP_BACKEND=http://127.0.0.1:9119 \
WEBAPP_PUBLIC_ORIGIN=http://hermes-webapp.localhost:8080 \
npm --prefix apps/webapp start
```

Open **http://hermes-webapp.localhost:8080/** (modern browsers resolve `.localhost` to loopback). Sign in using the backend's existing login form/provider. The service binds **127.0.0.1** by default. If the backend has already been configured for another public origin, use that origin consistently instead.

For development, use the same variables with:

```sh
WEBAPP_BACKEND=http://127.0.0.1:9119 \
WEBAPP_PUBLIC_ORIGIN=http://hermes-webapp.localhost:8080 \
npm --prefix apps/webapp run dev
```

The browser still opens port 8080. Vite runs internally on 127.0.0.1:5175 and API/auth traffic goes through the same production proxy. HMR is disabled; reload after edits. The development Vite listener exposes source code locally; use only `start` for deployment.

### Backend setup

If opening the app reports HTTP 404, check `WEBAPP_BACKEND`: it must point to `hermes dashboard` or `hermes serve`, normally port **9119**, not the OpenAI-compatible API on **8642**. Probe `/api/auth/me`: an unauthenticated authenticated-backend response is **401**, not 404. Restart the webapp after changing its environment; rebuilding alone does not update a running process.

Use a dedicated Hermes home if the existing native gateway is private/token-only. For a separate root, place it outside the default Hermes root: Hermes intentionally treats nested homes as part of that root. Configure the selected home through the CLI (replace the path and login):

```sh
export HERMES_HOME=/absolute/path/to/your/webapp-home
hermes config set dashboard.public_url http://hermes-webapp.localhost:8080
hermes config set dashboard.basic_auth.username your-login
webapp_password_hash="$(venv/bin/python -c 'from getpass import getpass; from plugins.dashboard_auth.basic import hash_password; print(hash_password(getpass("Password: ")))')"
hermes config set dashboard.basic_auth.password_hash "$webapp_password_hash"
unset webapp_password_hash
```

The password prompt keeps the plaintext password out of shell history. For an existing OAuth provider, retain its configuration and set `dashboard.public_url` to the browser origin. If sessions should survive backend restarts, set `dashboard.basic_auth.secret` through `hermes config set` with a persistent secret from your usual secret management. Keep authentication secrets on the backend.

Launch the existing backend with the chosen home (replace the path):

```sh
HERMES_HOME=/absolute/path/to/your/webapp-home \
hermes serve --host 127.0.0.1 --port 9119
```

`dashboard.public_url` with the `.localhost` hostname engages Hermes' existing auth gate even with a loopback listener. Confirm `/api/auth/me` returns HTTP 401 before login. No provider means startup must fail closed. The app rejects a legacy loopback-token identity: it never reads `.env`, scrapes injected tokens, requests private control tickets, provisions a gateway, or injects an operator credential into proxied requests.

An active Hermes update/install lock must be resolved by its owner before normal backend launch. This app does not modify the package manager environment or repair/update the runtime.

## Configuration and deployment

| Variable | Default | Meaning |
| --- | --- | --- |
| `WEBAPP_HOST` | `127.0.0.1` | Web service listen address. |
| `WEBAPP_PORT` | `8080` | Listen port. |
| `WEBAPP_BACKEND` | `http://127.0.0.1:9119` | Hermes dashboard/serve HTTP(S) origin, not the OpenAI-compatible API server (normally port 8642). Credentials, paths, fragments and query strings are refused. |
| `WEBAPP_PUBLIC_ORIGIN` | HTTP origin derived from host/port | Exact browser origin, required for non-loopback binding. Host and Origin validation uses this value. |

The production service uses only Node standard-library HTTP(S), streams and filesystem APIs. Copy `server.mjs` and `dist/` together to run independently of the source checkout. Rebuild to pick up renderer changes. Keep the deployed frontend and backend compatible; source reuse follows the checked-out Desktop revision rather than maintaining a fork.

`services/dev.hermes.webapp.plist` is a macOS LaunchAgent template for this workspace. Check the absolute Node executable (`command -v node`), paths and environment first; build and create `.scratch` before installing. To install deliberately:

```sh
cp apps/webapp/services/dev.hermes.webapp.plist "$HOME/Library/LaunchAgents/dev.hermes.webapp.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/dev.hermes.webapp.plist"
# Stop/remove the running agent:
launchctl bootout "gui/$(id -u)/dev.hermes.webapp"
```

`services/hermes-webapp.service` is a Linux systemd user-service template. Change the macOS checkout path and `/usr/bin/node` to the deployment paths, copy into `~/.config/systemd/user/`, then run `systemctl --user daemon-reload` and `systemctl --user enable --now hermes-webapp`. Manage the Hermes backend as a separate authenticated service. Neither service template is installed by the build or tests.

For remote access, put an HTTPS reverse proxy in front of the loopback web service. Set **both** `WEBAPP_PUBLIC_ORIGIN` and backend `dashboard.public_url` to the exact HTTPS origin. Configure the Hermes auth provider's callback to that origin's `/auth/callback`. Preserve browser Host and Origin and enable WebSocket upgrades for `/api/`; do not expose the backend's private/native listener. Backend Host/Origin checks must accept the declared public hostname. The app strips incoming forwarded headers and supplies only its operator-configured public host/protocol. The backend must trust only its actual proxy peer. This app supports deployment at the origin root, not a URL subpath. Use one backend process or proper session affinity because public WebSocket tickets are process-local and single-use.

## Transport and security boundaries

1. Browser bootstrap calls `GET /api/auth/me` using same-origin cookies. Unauthenticated users receive a sign-in link to `/login?next=/`.
2. `/login`, `/auth/login`, `/auth/callback`, `/auth/password-login`, `/auth/logout` pass to the existing Hermes routes. HttpOnly session-cookie issuance and refresh remain backend responsibilities.
3. Each WebSocket dial/reconnect calls authenticated `POST /api/auth/ws-ticket`, then opens same-origin `/api/ws?ticket=…`. This uses the existing public JSON-RPC transport, shared `HermesGateway`, prompt lifecycle, event handling and profile routing. There is no `native_dial`, private IPC ticket, protocol fabrication or relabeling of Desktop GUI sessions as CLI sessions.
4. The adapter forwards REST profile scope as `?profile=`. The registry contains one immutable operator-configured source; profiles share that source's backend. Changing the backend requires service configuration.
5. The proxy forwards browser cookies/authorization as presented and preserves upstream errors. It never adds credentials or changes an authentication rejection into success. A fixed origin prevents a client-selected open proxy. Host and Origin mismatches are refused, including WebSocket upgrades; WebSocket upgrades without Origin are refused too. Auth callback navigations remain possible.
6. Only files whose real paths remain inside `dist/` are served. Dot-segment, encoded traversal and symlink escapes are refused. No SPA fallback returns source files. `/auth/native`, native API doors, `native_dial` and internal-credential query parameters are rejected. Existing authenticated backend filesystem APIs retain their backend policy; no unauthenticated filesystem route is added.

The renderer's `window.hermesDesktop` name remains a compatibility seam, populated by `src/adapter.ts` with explicit browser implementations. There is no generic IPC emulation or catch-all capability proxy. Browser-only shell copy is currently English; the reused renderer retains all its existing locale catalogs.

## Capability matrix

| Capability | Browser behavior |
| --- | --- |
| Chat transcript, composer, streaming, approvals and slash commands | Original renderer and shared RPC client, public authenticated backend transport. No model turn is needed for verification. |
| Session history, search, existing session controls | Original UI and authenticated Hermes REST/RPC. |
| Profiles and backend model/config/settings | Original UI with explicit profile routing; profile/default choice stored per browser origin. |
| Themes, layout, keyboard shortcuts within the page | Original browser-compatible renderer behavior/local storage. Browser/OS-reserved shortcuts remain owned by the browser. |
| Backend files/git | Existing authenticated remote-mode APIs and their backend filesystem rules. No local browser disk paths or native IPC. |
| Attachments | Existing remote upload flow where supported by the renderer; native path-based picking/paste-saving is unavailable. Browser clipboard requires the browser's normal permissions and a secure context. |
| Artifact iframes | Original sandboxed iframe primitive; no Electron guest privileges. |
| Embedded Electron browser/annotation/guest automation | Replaced with an explicit unavailable panel and user-initiated safe HTTP(S) external-tab link. |
| Gateway configuration, SSH tunnels, Cloud discovery, native token/keychain storage | Gateway settings replaced with a browser explanation; source fixed by operator. |
| Native terminal processes, OS file dialogs/reveal, app/session popout windows | Unavailable. Backend agent tools may still execute according to backend policy. |
| Native notifications, microphone/voice capture, global hotkeys, HUD, pet overlays, screenshots, transparency, power controls | Unavailable or absent; browser controls show the limitation. No permission is silently granted. |
| Runtime Desktop plugins loaded from disk | Disabled by browser loader overlay; bundled renderer plugins still use their existing registration path. |
| Electron install/update/uninstall, tray, OS process lifecycle | Unavailable; update/restart the independently deployed services through their operator. |

## Verification

```sh
export TMPDIR="$PWD/apps/webapp/.scratch"
npm --prefix apps/webapp run typecheck
npm --prefix apps/webapp run build
npm --prefix apps/webapp test
npm --prefix apps/webapp run smoke
```

`test` runs Node boundary/proxy tests, real Hermes ASGI integration, browser adapter tests and a DOM runtime mount of the actual renderer. Node proxy tests use mocked network streams and **do not prove a live TCP proxy deployment**. ASGI integration uses Hermes' bundled BasicAuthProvider, cookie gate, ticket routes, real dispatcher and isolated SQLite session data. The test harness substitutes only the platform-default home (to keep profile roots isolated) and package provisioning/bootstrap (to avoid touching a live install/update lock). No auth/REST/RPC handlers are mocked and no model prompt is sent. DOM tests emulate browser geometry/canvas limitations; they do not prove browser rendering.

`smoke` requires installed Playwright and Chrome (`WEBAPP_BROWSER=msedge` chooses Edge; `WEBAPP_PYTHON` selects an existing Python interpreter with the Hermes dependencies). It loads the actual production bundle through intercepted browser requests and bridges HTTP/WebSocket traffic to the real in-process ASGI test harness, with the same limited bootstrap/home substitutions. It needs no TCP listener, production credentials or paid model turn. It requires an open renderer WebSocket, `gateway.ready`, a successful RPC reply, and disappearance of `CONNECTING`; a sidebar title alone is insufficient. It asserts computed flex layout, viewport coverage, theme variables, and composer geometry. It writes `.scratch/browser-smoke.png`, `.scratch/browser-settings.png`, `.scratch/browser-smoke.txt`, `.scratch/browser-diagnostics.json` (loaded stylesheets, computed styles, and RPC diagnostics) and `.scratch/smoke-backend.log`. Inspect the screenshots before accepting the visual result. It is distinct from a live two-service smoke. For deployment acceptance also run the two services, sign in at the actual URL, inspect history, switch profile, edit a reversible setting, and confirm a WebSocket reconnect.

The implementation-session results and environment blockers are recorded in `VERIFICATION.md`.
