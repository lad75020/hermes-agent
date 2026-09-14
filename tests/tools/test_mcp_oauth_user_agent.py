"""Tests for User-Agent handling on MCP OAuth requests.

Some authorization servers and WAFs reject httpx's default User-Agent on the
token endpoint (#75576), while others reject SDK-generated discovery requests
that omit User-Agent entirely. ``oauth.user_agent`` remains an opt-in token
request override; other OAuth auxiliary requests receive a safe default without
changing MCP traffic.

The tests drive the REAL provider classes' request builders end to end: the
``httpx.Request`` the SDK would send is what gets inspected, not a mocked
constructor call.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip(
    "mcp.client.auth.oauth2",
    reason="MCP SDK required for OAuth support",
)

from tools.mcp_oauth import (  # noqa: E402 — after the SDK availability gate
    build_oauth_auth,
    token_request_user_agent,
)


def _set_interactive_stdin(monkeypatch, *, is_tty: bool = True) -> None:
    mock_stdin = MagicMock()
    mock_stdin.isatty.return_value = is_tty
    monkeypatch.setattr("tools.mcp_oauth.sys.stdin", mock_stdin)


@pytest.fixture(autouse=True)
def clean_port_state():
    import tools.mcp_oauth as mod

    mod._assigned_cimd_ports.clear()
    yield
    mod._assigned_cimd_ports.clear()
    for port in list(mod._reserved_sockets):
        sock = mod._reserved_sockets.pop(port, None)
        if sock is not None:
            sock.close()


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def test_configured_user_agent_is_returned():
    assert token_request_user_agent({"user_agent": "My-MCP-Client/1.0"}) == "My-MCP-Client/1.0"


@pytest.mark.parametrize("cfg", [
    pytest.param({}, id="absent"),
    pytest.param({"user_agent": None}, id="null"),
    pytest.param({"user_agent": ""}, id="empty"),
    pytest.param({"user_agent": "   "}, id="whitespace-only"),
    pytest.param({"user_agent": 7}, id="non-string"),
])
def test_unset_user_agent_values_are_treated_as_absent(cfg):
    assert token_request_user_agent(cfg) is None


def test_user_agent_is_stripped():
    assert token_request_user_agent({"user_agent": "  UA/2 "}) == "UA/2"


# ---------------------------------------------------------------------------
# The requests the SDK actually sends
# ---------------------------------------------------------------------------


def _ready_for_token_requests(provider):
    """Give the provider the minimum context both builders require."""
    from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

    provider.context.oauth_metadata = SimpleNamespace(
        token_endpoint="https://idp.example.com/oauth/token"
    )
    provider.context.client_info = OAuthClientInformationFull.model_validate({
        "client_id": "client-1",
        "redirect_uris": ["http://127.0.0.1:33333/callback"],
    })
    provider.context.current_tokens = OAuthToken.model_validate({
        "access_token": "at",
        "token_type": "Bearer",
        "refresh_token": "rt",
    })


def _build_provider_via(builder, monkeypatch, tmp_path, cfg):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _set_interactive_stdin(monkeypatch)
    return builder(
        "srv", "https://mcp.example.com/mcp", {"redirect_port": 33333, **cfg}
    )


def _manager_builder(server_name, server_url, cfg):
    from tools.mcp_oauth_manager import MCPOAuthManager, reset_manager_for_tests

    reset_manager_for_tests()
    return MCPOAuthManager().get_or_build_provider(server_name, server_url, cfg)


@pytest.mark.parametrize("builder", [
    pytest.param(build_oauth_auth, id="build_oauth_auth"),
    pytest.param(_manager_builder, id="oauth_manager"),
])
def test_sdk_metadata_and_registration_requests_have_a_nonempty_default_user_agent(
    builder, tmp_path, monkeypatch
):
    """A WAF must not reject the SDK's raw discovery or DCR requests."""
    from tools.mcp_tool import sdk_httpx

    httpx = sdk_httpx()
    assert httpx is not None
    provider = _build_provider_via(builder, monkeypatch, tmp_path, {})
    resource_request = httpx.Request("POST", "https://mcp.example.com/mcp")

    async def oauth_auxiliary_requests():
        flow = provider.async_auth_flow(resource_request)
        try:
            outgoing_resource = await flow.__anext__()
            assert outgoing_resource is resource_request
            assert "User-Agent" not in outgoing_resource.headers
            unauthorized = httpx.Response(401, request=resource_request)
            prm_request = await flow.asend(unauthorized)
            asm_request = await flow.asend(httpx.Response(
                200,
                request=prm_request,
                json={
                    "resource": "https://mcp.example.com",
                    "authorization_servers": ["https://auth.example.com"],
                },
            ))
            registration_request = await flow.asend(httpx.Response(
                200,
                request=asm_request,
                json={
                    "issuer": "https://auth.example.com",
                    "authorization_endpoint": "https://auth.example.com/authorize",
                    "token_endpoint": "https://auth.example.com/token",
                    "registration_endpoint": "https://auth.example.com/register",
                    "response_types_supported": ["code"],
                },
            ))
            return prm_request, asm_request, registration_request
        finally:
            await flow.aclose()

    prm_request, asm_request, registration_request = asyncio.run(
        oauth_auxiliary_requests()
    )

    assert [request.method for request in (prm_request, asm_request, registration_request)] == [
        "GET", "GET", "POST",
    ]
    assert all(
        request.headers.get("User-Agent", "").strip()
        for request in (prm_request, asm_request, registration_request)
    )
    assert prm_request.headers.get("MCP-Protocol-Version")
    assert asm_request.headers.get("MCP-Protocol-Version")
    assert registration_request.headers.get("Content-Type") == "application/json"
    assert str(registration_request.url) == "https://auth.example.com/register"


@pytest.mark.parametrize("builder", [
    pytest.param(build_oauth_auth, id="build_oauth_auth"),
    pytest.param(_manager_builder, id="oauth_manager"),
])
def test_token_requests_carry_the_configured_user_agent(
    builder, tmp_path, monkeypatch
):
    """Both token-endpoint requests, on both provider construction paths."""
    provider = _build_provider_via(
        builder, monkeypatch, tmp_path, {"user_agent": "My-MCP-Client/1.0"}
    )
    _ready_for_token_requests(provider)

    exchange = asyncio.run(
        provider._exchange_token_authorization_code("code", "verifier")
    )
    refresh = asyncio.run(provider._refresh_token())

    assert exchange.headers["User-Agent"] == "My-MCP-Client/1.0"
    assert refresh.headers["User-Agent"] == "My-MCP-Client/1.0"


@pytest.mark.parametrize("builder", [
    pytest.param(build_oauth_auth, id="build_oauth_auth"),
    pytest.param(_manager_builder, id="oauth_manager"),
])
def test_unconfigured_token_requests_get_a_nonempty_default_user_agent(
    builder, tmp_path, monkeypatch
):
    """No config still produces WAF-compatible token requests."""
    provider = _build_provider_via(builder, monkeypatch, tmp_path, {})
    _ready_for_token_requests(provider)

    exchange = asyncio.run(
        provider._exchange_token_authorization_code("code", "verifier")
    )
    refresh = asyncio.run(provider._refresh_token())

    assert exchange.headers.get("User-Agent", "").strip()
    assert refresh.headers.get("User-Agent", "").strip()


def test_user_agent_does_not_disturb_token_auth_preparation(tmp_path, monkeypatch):
    """The stamp runs after prepare_token_auth — a confidential client's
    Authorization header must survive alongside the custom User-Agent."""
    provider = _build_provider_via(
        build_oauth_auth, monkeypatch, tmp_path,
        {"user_agent": "UA/1", "client_id": "pre", "client_secret": "shh",
         "token_endpoint_auth_method": "client_secret_basic"},
    )
    _ready_for_token_requests(provider)
    from mcp.shared.auth import OAuthClientInformationFull

    provider.context.client_info = OAuthClientInformationFull.model_validate({
        "client_id": "pre",
        "client_secret": "shh",
        "token_endpoint_auth_method": "client_secret_basic",
        "redirect_uris": ["http://127.0.0.1:33333/callback"],
    })

    exchange = asyncio.run(
        provider._exchange_token_authorization_code("code", "verifier")
    )

    assert exchange.headers["User-Agent"] == "UA/1"
    assert exchange.headers.get("Authorization", "").startswith("Basic ")
