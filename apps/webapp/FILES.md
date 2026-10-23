# Browser app source inventory

Current tracked and new source/configuration/documentation files under `apps/webapp`:

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
- `apps/webapp/src/browser-scheduling.ts`
- `apps/webapp/src/gateway-settings.tsx`
- `apps/webapp/src/keep-awake.ts`
- `apps/webapp/src/main.ts`
- `apps/webapp/src/noop.ts`
- `apps/webapp/src/power-save.ts`
- `apps/webapp/src/preview-pane.tsx`
- `apps/webapp/src/runtime-loader.ts`
- `apps/webapp/src/transport.ts`
- `apps/webapp/src/voice-client-direct.ts`
- `apps/webapp/src/webapp.css`
- `apps/webapp/tests/adapter.test.ts`
- `apps/webapp/tests/asgi-client.mjs`
- `apps/webapp/tests/backend.test.mjs`
- `apps/webapp/tests/browser-scheduling.test.ts`
- `apps/webapp/tests/compatibility.test.ts`
- `apps/webapp/tests/flows.test.ts`
- `apps/webapp/tests/previews.test.ts`
- `apps/webapp/tests/proxy.test.mjs`
- `apps/webapp/tests/renderer.test.ts`
- `apps/webapp/tests/setup.ts`
- `apps/webapp/tsconfig.json`
- `apps/webapp/vite.config.ts`
- `apps/webapp/vitest.config.ts`

The browser imports the actual `../desktop/src` and `../shared/src` trees. Browser-only overlays remain here; the obsolete browser gateway resolver was removed in favor of the current Desktop resolver. No renderer copy is maintained.

Generated `dist/` and `.scratch/` files are ignored. Existing root dependencies are reused; no package or lockfile update is required. See [VERIFICATION.md](./VERIFICATION.md) for source revision, observed checks and working-tree boundaries.
