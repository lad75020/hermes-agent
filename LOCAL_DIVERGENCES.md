# Local Divergences from Upstream

Intentional deviations from upstream `hermes-agent` maintained in this local
checkout. **Check this file when resolving `upstream-latest` merge conflicts** —
if a merge re-introduces upstream behavior listed here, keep the local side.

---

## API server: session headers accepted in no-key mode

- **File:** `gateway/platforms/api_server.py` (session-header parsing)
- **Tests:**
  - `tests/gateway/test_api_server.py::TestSessionIdHeader::test_provided_session_id_is_used_without_api_key`
  - `tests/gateway/test_api_server.py::TestSessionKeyHeader::test_session_key_accepted_without_api_key`
- **Upstream behavior:** rejects caller-supplied `X-Hermes-Session-Id` and
  `X-Hermes-Session-Key` headers with **403** when `API_SERVER_KEY` is unset.
- **Local behavior:** **accepts** both headers in no-key mode, so
  VPN-local/browser clients keep the same transcript-continuity and
  memory-scoping contracts as the built-in gateway adapters.
- **Rationale:** `connect()` already refuses to start the API server without
  `API_SERVER_KEY` in production, so the no-key path is local/manual-wiring
  only. Laurent's local workflow relies on no-key session headers. See the
  `hermes-agent` skill note *"no-key local session headers"*.
- **On merge:** if upstream restores either 403 assertion or a reject-in-no-key
  code path, keep the local permissive version. Do not re-add either 403.
