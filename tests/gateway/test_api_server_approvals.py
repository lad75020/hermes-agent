"""Tests for the API-server approval inbox endpoints."""

from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import tools.approval as approval_module
from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


def _make_adapter(api_key: str = "") -> APIServerAdapter:
    extra = {}
    if api_key:
        extra["key"] = api_key
    return APIServerAdapter(PlatformConfig(enabled=True, extra=extra))


def _create_approvals_app(adapter: APIServerAdapter) -> web.Application:
    app = web.Application()
    app["api_server_adapter"] = adapter
    app.router.add_get("/v1/approvals", adapter._handle_approvals)
    app.router.add_post("/v1/approvals/resolve", adapter._handle_approval_resolve)
    app.router.add_post("/v1/approvals/{session_key}/resolve", adapter._handle_approval_resolve)
    return app


def _clear_session(key: str) -> None:
    approval_module.clear_session(key)
    with approval_module._lock:
        approval_module._gateway_queues.pop(key, None)


def _queue_approval(key: str) -> approval_module._ApprovalEntry:
    entry = approval_module._ApprovalEntry({
        "command": "rm -rf /tmp/demo",
        "pattern_key": "recursive delete",
        "pattern_keys": ["recursive delete"],
        "description": "recursive delete",
    })
    with approval_module._lock:
        approval_module._gateway_queues[key] = [entry]
    return entry


@pytest.mark.asyncio
async def test_api_server_approvals_requires_auth():
    adapter = _make_adapter(api_key="sk-secret")
    app = _create_approvals_app(adapter)

    async with TestClient(TestServer(app)) as cli:
        resp = await cli.get("/v1/approvals")

    assert resp.status == 401


@pytest.mark.asyncio
async def test_api_server_approvals_lists_pending_rows():
    key = "api-server-list"
    _clear_session(key)
    try:
        _queue_approval(key)
        adapter = _make_adapter()
        app = _create_approvals_app(adapter)

        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/v1/approvals")
            payload = await resp.json()

        assert resp.status == 200
        rows = [row for row in payload["approvals"] if row["session_key"] == key]
        assert rows[0]["command"] == "rm -rf /tmp/demo"
        assert rows[0]["scope_options"] == ["once", "session", "always", "deny"]
    finally:
        _clear_session(key)


@pytest.mark.asyncio
async def test_api_server_approvals_resolves_by_session_key():
    key = "api-server-resolve"
    _clear_session(key)
    try:
        entry = _queue_approval(key)
        adapter = _make_adapter()
        app = _create_approvals_app(adapter)

        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post(
                "/v1/approvals/resolve",
                json={"session_key": key, "choice": "always"},
            )
            payload = await resp.json()

        assert resp.status == 200
        assert payload["resolved"] == 1
        assert entry.result == "always"
        assert entry.event.is_set()
        assert not approval_module.has_blocking_approval(key)
    finally:
        _clear_session(key)


@pytest.mark.asyncio
async def test_api_server_approvals_path_resolve_rejects_invalid_choice():
    key = "api-server-invalid"
    _clear_session(key)
    try:
        _queue_approval(key)
        adapter = _make_adapter()
        app = _create_approvals_app(adapter)

        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post(f"/v1/approvals/{key}/resolve", json={"choice": "maybe"})

        assert resp.status == 400
        assert approval_module.has_blocking_approval(key)
    finally:
        _clear_session(key)
