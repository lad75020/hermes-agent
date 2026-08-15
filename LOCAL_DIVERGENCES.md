# Local Divergences from Upstream

Intentional deviations from upstream `hermes-agent` maintained in this local
checkout. **Check this file when resolving `upstream-latest` merge conflicts** —
if a merge re-introduces upstream behavior listed here, keep the local side.

---

## API server: X-Hermes-Session-Key accepted in no-key mode

- **File:** `gateway/platforms/api_server.py` (`_parse_session_key_header`)
- **Test:** `tests/gateway/test_api_server.py::TestSessionKeyHeader::test_session_key_accepted_without_api_key`
- **Upstream behavior:** rejects a caller-supplied `X-Hermes-Session-Key` with
  **403** when `API_SERVER_KEY` is unset (test named
  `test_session_key_rejected_without_api_key`, asserting `status == 403`).
- **Local behavior:** **accepts** the session key in no-key mode (asserts
  `status != 403`), so VPN-local/browser clients keep the same
  session/memory-scoping contract as the built-in gateway adapters.
- **Rationale:** `connect()` already refuses to start the API server without
  `API_SERVER_KEY` in production, so the no-key path is local/manual-wiring
  only. Laurent's local workflow relies on no-key session headers. See the
  `hermes-agent` skill note *"no-key local session headers"*.
- **On merge:** if upstream restores the 403 assertion or the reject-in-no-key
  code path, keep the local permissive version. Do not re-add the 403.
