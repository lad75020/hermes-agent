"""Merged local routes must survive the real API adapter startup path."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import ClientSession, web
from aiohttp.test_utils import make_mocked_request

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


@pytest_asyncio.fixture
async def isolated_api(tmp_path, monkeypatch):
    # Profile discovery is HOME-anchored as well as HERMES_HOME-aware.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text("model:\n  default: test-model\n")
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={
        "host": "127.0.0.1", "port": 0,
        "key": "startup-regression-key-0123456789", "model_name": "test-model",
    }))
    no_llm = AsyncMock(side_effect=AssertionError("Startup routes must not run an agent"))
    monkeypatch.setattr(adapter, "_run_agent", no_llm)
    try:
        yield adapter, home
        no_llm.assert_not_called()
    finally:
        await adapter.cancel_background_tasks()
        await adapter.disconnect()
    assert adapter._site is None and adapter._runner is None
    assert not adapter._background_tasks


@pytest_asyncio.fixture
async def running_api(isolated_api):
    adapter, home = isolated_api
    assert await adapter.connect() is True
    host, port = adapter._site._server.sockets[0].getsockname()[:2]
    assert host == "127.0.0.1" and port > 0
    print(f"Live API listener: http://{host}:{port}; home={home}")
    async with ClientSession(base_url=f"http://{host}:{port}") as client:
        yield client, {"Authorization": f"Bearer {adapter._api_key}"}


@pytest.mark.asyncio
async def test_registered_routes_dispatch_without_an_agent(isolated_api):
    """Exercise the complete route table and real middleware without needing a TCP socket."""
    import json

    adapter, _home = isolated_api
    app = web.Application(middlewares=[adapter._make_profile_prefix_middleware()])
    for method, path, handler in adapter._http_route_table():
        app.router.add_route(method, path, handler)
        app.router.add_route(method, f"/p/{{profile}}{path}", handler)
    app.freeze()
    headers = {"Authorization": f"Bearer {adapter._api_key}"}
    request = make_mocked_request("GET", "/v1/profiles", app=app)
    assert (await app._handle(request)).status == 401
    for path in ("/v1/profiles", "/p/default/v1/profiles"):
        request = make_mocked_request("GET", path, app=app, headers={
            **headers, "X-Hermes-Profile": "default",
        })
        response = await app._handle(request)
        assert response.status == 200
        profile = next(row for row in json.loads(response.text)["data"] if row["id"] == "default")
        assert profile["model"] == "test-model"
    request = make_mocked_request("GET", "/v1/profiles", app=app, headers={
        **headers, "X-Hermes-Profile": "missing",
    })
    assert (await app._handle(request)).status == 404
    request = make_mocked_request("GET", "/v1/approvals", app=app, headers=headers)
    response = await app._handle(request)
    assert response.status == 200
    assert json.loads(response.text)["approvals"] == []
    for path in ("/v1/approvals/resolve", "/v1/approvals/test-session/resolve"):
        request = make_mocked_request("POST", path, app=app, headers=headers)
        request.json = AsyncMock(return_value={"session_key": "test-session", "choice": "invalid"})
        response = await app._handle(request)
        assert response.status == 400
        assert json.loads(response.text)["error"]["code"] == "invalid_approval_choice"
    request = make_mocked_request("POST", "/v1/requests/not-running/cancel", app=app, headers=headers)
    response = await app._handle(request)
    assert response.status == 404
    assert json.loads(response.text)["error"]["code"] == "request_not_found"


@pytest.mark.asyncio
async def test_connect_serves_profiles_and_profile_headers(running_api):
    client, headers = running_api
    async with client.get("/health") as response:
        assert response.status == 200
        assert (await response.json())["status"] == "ok"
    async with client.get("/v1/profiles") as response:
        assert response.status == 401
    async with client.get("/v1/profiles", headers=headers) as response:
        assert response.status == 200
        payload = await response.json()
        profile = next(row for row in payload["data"] if row["id"] == "default")
        assert profile["is_default"] is True
        assert profile["model"] == "test-model"
        assert profile["reasoning"]["supported"] is False
        print(f"GET /v1/profiles -> {response.status}; default model={profile['model']}")
    async with client.get("/p/default/v1/profiles", headers={
        **headers, "X-Hermes-Profile": "default",
    }) as response:
        assert response.status == 200
        assert await response.json() == payload
    async with client.get("/v1/profiles", headers={
        **headers, "X-Hermes-Profile": "missing",
    }) as response:
        assert response.status == 404


@pytest.mark.asyncio
async def test_connect_serves_approval_and_cancellation_routes(running_api):
    client, headers = running_api
    async with client.get("/v1/approvals", headers=headers) as response:
        assert response.status == 200
        assert (await response.json())["approvals"] == []
    for path in ("/v1/approvals/resolve", "/v1/approvals/test-session/resolve"):
        async with client.post(path, headers=headers, json={"choice": "invalid"}) as response:
            assert response.status == 400
            assert "error" in await response.json()
    async with client.post("/v1/requests/not-running/cancel", headers=headers) as response:
        assert response.status == 404
        assert (await response.json())["error"]["code"] == "request_not_found"
        print(f"POST /v1/requests/not-running/cancel -> {response.status} request_not_found")
