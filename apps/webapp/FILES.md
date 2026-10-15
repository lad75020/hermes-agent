# Exact source-file inventory

New files under `apps/webapp`:

- `apps/webapp/.gitignore`
- `apps/webapp/FILES.md`
- `apps/webapp/README.md`
- `apps/webapp/VERIFICATION.md`
- `apps/webapp/index.html`
- `apps/webapp/package.json`
- `apps/webapp/scripts/backend-harness.py`
- `apps/webapp/scripts/dev.mjs`
- `apps/webapp/scripts/smoke.mjs`
- `apps/webapp/scripts/verify-desktop.mjs`
- `apps/webapp/server.mjs`
- `apps/webapp/services/dev.hermes.webapp.plist`
- `apps/webapp/services/hermes-webapp.service`
- `apps/webapp/src/adapter.ts`
- `apps/webapp/src/gateway-settings.tsx`
- `apps/webapp/src/gateway-ws-url.ts`
- `apps/webapp/src/keep-awake.ts`
- `apps/webapp/src/main.ts`
- `apps/webapp/src/noop.ts`
- `apps/webapp/src/power-save.ts`
- `apps/webapp/src/preview-pane.tsx`
- `apps/webapp/src/runtime-loader.ts`
- `apps/webapp/src/transport.ts`
- `apps/webapp/src/webapp.css`
- `apps/webapp/tests/adapter.test.ts`
- `apps/webapp/tests/asgi-client.mjs`
- `apps/webapp/tests/backend.test.mjs`
- `apps/webapp/tests/proxy.test.mjs`
- `apps/webapp/tests/renderer.test.ts`
- `apps/webapp/tests/setup.ts`
- `apps/webapp/tsconfig.json`
- `apps/webapp/vite.config.ts`
- `apps/webapp/vitest.config.ts`

Existing file modified outside this app:

- `tui_gateway/methods_onboarding.py` — one missing `Path` import required to load the existing dispatcher.

Generated files are confined to `apps/webapp/dist/` and `apps/webapp/.scratch/` and ignored by this app's `.gitignore`. Root package files and `apps/desktop` have no changes.
