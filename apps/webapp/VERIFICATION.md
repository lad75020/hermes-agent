# Browser compatibility verification — 2026-10-23

Source audited: `cfbba1a2eb86ab14d6d3ce7eebd7fe24bab4b225` (`Merge branch upstream-latest`). Webapp creation baseline: `47a703cb8f`. Desktop/shared diff: 634 changed files, including renderer changes, native Electron infrastructure, generated gateway contracts, locales and tests. The app still aliases the actual Desktop/shared source trees; renderer files were not copied or edited.

## Baseline and regression evidence

Commands ran from `/Volumes/WDBlack4TB/.hermes/hermes-agent` with existing root npm dependencies and `TMPDIR=/Volumes/WDBlack4TB/.hermes/cache/scratch`. No install/update, production service lifecycle action, commit, push, deployment or model prompt was performed. Tests use isolated homes under `apps/webapp/.scratch`, ephemeral BasicAuthProvider fixtures and the existing `venv/bin/python`; no production secrets/auth files were inspected or edited.

- Initial `npm --prefix apps/webapp run typecheck`: exit 0.
- Initial `npm --prefix apps/webapp run build`: exit 0; 17,758 modules transformed, built in 4.58s.
- Initial `npm --prefix apps/webapp test`: eight Node/ASGI tests passed, then both Vitest suites failed before collection with `EPERM` creating a fork-cache directory under the requested `TMPDIR`. Running with `--pool=threads` passed all eight original Vitest tests. The config now selects threads without changing `TMPDIR` or dependencies.
- Six new behavioral regressions were run before adapter/preview fixes: all six failed. Evidence: `.scratch/regression-red.log`. They cover foreign registry dials, explicit primary profile versus remembered selection, mutable registry results, clipboard boolean result, file/artifact preview dispatch and native-only attachment/export errors.
- The real renderer filesystem helper regression additionally failed on encoded absolute paths in query values (`.scratch/flows-red.log`). Endpoint traversal checks now apply to the pathname, while encoded query values pass through to authenticated backend policy.
- Checking every implemented adapter member with `Partial<Window['hermesDesktop']>` exposed incomplete diagnostics, OAuth and quick-entry return values. Mapping overlays in TypeScript also exposed the runtime-plugin uninstall signature mismatch. All are corrected.

## Migrated boundaries

- Removed the stale browser gateway resolver override; the actual Desktop resolver now enforces registry-scoped ticket routing. Public cookie authentication, one fresh public ticket per dial, credential-free descriptors and the fixed operator backend remain in force. Foreign source IDs fail before network traffic. Registry snapshots cannot mutate service selection.
- Descriptors and ticket requests consistently distinguish omitted profiles from explicit primary requests. Default-workspace reads carry the current API profile. Real ASGI config reads/writes prove primary and secondary profile isolation in one backend.
- The preview overlay delegates files and artifacts to the actual components, preserving backend reads/edits, image/PDF handling and the artifact sandbox. Backend HTML uses source view. Only the Electron web guest remains replaced with an unavailable panel and a user-initiated HTTP(S) external link.
- Native clipboard text writes return the boolean bridge result. Native filesystem/staging, clipboard-image staging, pasted-text staging, SSH/credential management and the new text-export dialog fail with explicit capability errors. Microphone capture reports unavailability and returns false; native power remains off.
- Cookie-auth bundled-plugin REST stays profile-scoped; plugin sockets keep the current Desktop polling fallback. The new private plugin-grant bridge remains absent. Disk plugin discovery remains disabled and uninstall reports unsupported with the current call signature.
- Direct voice-provider config/STT/TTS is overlaid with relay selection. Browser callers do not fetch provider keys. Existing speech and sibling-stream resolvers mint fresh public tickets and preserve the explicit session owner route; native tickets are never requested.
- Browser startup installs a feature-detected idle-callback fallback for browsers without the API pair. Unit tests cover execution, cancellation and preservation of native implementations. The production browser smoke removes Chromium's native pair before startup and opens Capabilities to exercise the fallback.
- The smoke harness now inherits the requested `TMPDIR` and writes child stderr through an open descriptor until child exit; cleanup no longer masks browser launch failures with `EBADF`.

## Final commands and actual outputs

| Command | Result |
| --- | --- |
| `npm --prefix apps/webapp run typecheck` | Exit 0; `tsc -p tsconfig.json --noEmit`, no diagnostics. |
| `npm --prefix apps/webapp test` | Exit 0; Node: 9 passed, 0 failed; Vitest: 6 files passed, 23 tests passed. 32 tests total. |
| `npm --prefix apps/webapp run build` | Exit 0; `✓ built in 2.79s`. |
| `npm --prefix apps/webapp run smoke` | Parent rerun outside the Codex sandbox: exit 0. Real ASGI authentication/tickets/RPC, history, computed layout, Appearance, Capabilities without native idle callbacks, and fully loaded delegation routing controls pass; no page exceptions. |
| `git diff --check` | Pass. |
| `git diff --name-only -- apps/desktop apps/shared` | Empty; parent SHA-256 comparison also confirms all 4,313 tracked Desktop/shared files match the pre-port baseline. |

Ignored evidence: `.scratch/typecheck.log`, `.scratch/test.log`, `.scratch/build.log`, `.scratch/smoke.log`, `.scratch/regression-red.log`, `.scratch/regression-green.log`, `.scratch/flows-red.log`, `.scratch/desktop-boundary-delta.txt`. DOM integration also records renderer output in `.scratch/renderer-connected.txt`.

Non-fatal output: build warns about the inherited `advancedChunks` option and a Desktop `profile-ops.ts` dynamic/static import overlap. JSDOM reports three canvas `getContext` limitations; the renderer and component assertions pass without adding canvas dependencies.

## Coverage and limitations

Node tests exercise proxy Host/Origin rejection, traversal/static-file boundaries, public auth rejection, cookies, ticket single-use/replay rejection, real JSON-RPC and primary/secondary settings. They do not prove a live TCP proxy deployment. Vitest exercises the actual shared renderer mount and open gateway state, actual backend-image and artifact components, filesystem query encoding, registry/profile routing, plugin polling, voice ticket routes, direct-provider relay selection, native unavailability and scheduling fallback. Preview dispatch tests use component doubles; separate tests mount the real image and artifact components.

The Codex sandbox could not launch Playwright because its requested scratch directory was not writable there. The parent reran the production build and expanded Chrome smoke successfully outside that sandbox with the requested `TMPDIR`. Fresh screenshots were inspected: `.scratch/browser-smoke.png`, `.scratch/browser-settings.png`, `.scratch/browser-capabilities.png` and `.scratch/browser-delegation.png`. The themed shell fills the 1440×1000 viewport, its composer fits, and delegation mode choices finish loading. Capabilities renders its recoverable catalog-fetch warning because the isolated smoke deliberately blocks external network requests; live marketplace availability is not certified. Chrome exercised the missing-idle-API path; Safari itself was not launched. Parent command logs are in `/Volumes/WDBlack4TB/.hermes/cache/scratch/webapp-port-{build,tests,smoke}.log`.

The browser test intercepts requests and bridges them to the real in-process ASGI harness; it is not a deployed two-service acceptance test. At the actual deployed origin, login, history, profile switching, a reversible setting and reconnect still need operator acceptance. No production service was started or restarted.

Microphone capture, browser-host attachment staging, native `/save` dialog, Electron guest navigation/automation, disk Desktop plugins, native windows/OS controls and credential storage remain unavailable by design. Backend-owned file references and browser text clipboard access are distinct from browser-host uploads. Actual audio/provider playback, provider OAuth callbacks, full PDF/editor interactions and multi-tab ambient-cue deduplication were not exercised. Partial-clone history search (`git log -S`) encountered missing historical objects and an unavailable promisor remote; the complete checked-out baseline-to-HEAD diff and current definitions/usages were available. The Desktop graph returned discovery results but an empty caller trace; exact usages were used for that portion of impact analysis.

All changes made for this port are under `apps/webapp`. The archive deletion `apps/webapp.zip` was present initially and left alone. A root `.gitignore` edit appeared concurrently and was also left alone. No Desktop/shared tracked diff exists.
