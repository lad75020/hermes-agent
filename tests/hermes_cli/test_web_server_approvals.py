"""Dashboard approvals API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

import hermes_cli.web_server as ws
import tools.approval as approval_module


def _headers() -> dict[str, str]:
    return {ws._SESSION_HEADER_NAME: ws._SESSION_TOKEN}


def _clear_session(key: str) -> None:
    approval_module.clear_session(key)
    with approval_module._lock:
        approval_module._gateway_queues.pop(key, None)


def _queue_approval(key: str, command: str = "rm -rf /tmp/demo") -> approval_module._ApprovalEntry:
    entry = approval_module._ApprovalEntry({
        "command": command,
        "pattern_key": "recursive delete",
        "pattern_keys": ["recursive delete"],
        "description": "recursive delete",
    })
    with approval_module._lock:
        approval_module._gateway_queues[key] = [entry]
    return entry


def test_approvals_api_requires_dashboard_session_token():
    client = TestClient(ws.app)

    response = client.get("/api/approvals")

    assert response.status_code == 401


def test_approvals_api_lists_pending_approval_json():
    key = "dashboard-api-list"
    _clear_session(key)
    try:
        _queue_approval(key)
        client = TestClient(ws.app)

        response = client.get("/api/approvals", headers=_headers())

        assert response.status_code == 200
        payload = response.json()
        rows = [row for row in payload["approvals"] if row["session_key"] == key]
        assert payload["count"] >= 1
        assert rows[0]["queue_position"] == 1
        assert rows[0]["command"] == "rm -rf /tmp/demo"
        assert rows[0]["scope_options"] == ["once", "session", "always", "deny"]
    finally:
        _clear_session(key)


def test_approvals_api_resolves_oldest_pending_approval():
    key = "dashboard-api-resolve"
    _clear_session(key)
    try:
        entry = _queue_approval(key)
        client = TestClient(ws.app)

        response = client.post(
            "/api/approvals/resolve",
            headers=_headers(),
            json={"session_key": key, "choice": "session", "resolve_all": False},
        )

        assert response.status_code == 200
        assert response.json()["resolved"] == 1
        assert entry.result == "session"
        assert entry.event.is_set()
        assert not approval_module.has_blocking_approval(key)
    finally:
        _clear_session(key)


def test_approvals_api_rejects_invalid_choice():
    key = "dashboard-api-invalid-choice"
    _clear_session(key)
    try:
        _queue_approval(key)
        client = TestClient(ws.app)

        response = client.post(
            f"/api/approvals/{key}/resolve",
            headers=_headers(),
            json={"choice": "maybe"},
        )

        assert response.status_code == 400
        assert approval_module.has_blocking_approval(key)
    finally:
        _clear_session(key)
