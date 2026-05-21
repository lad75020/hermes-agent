"""Local API listeners retain session continuity and browser control headers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from tests.gateway.test_api_server import _create_app, _make_adapter, adapter as adapter


class TestLocalAPIContinuity:
    @pytest.mark.asyncio
    async def test_cors_allows_hermes_control_headers(self):
        adapter = _make_adapter(cors_origins=["http://localhost:3000"])
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.options(
                "/v1/chat/completions",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": (
                        "content-type,x-hermes-session-id,x-hermes-session-key,"
                        "x-hermes-profile,x-hermes-request-id"
                    ),
                },
            )
            assert resp.status == 200
            allow_headers = resp.headers.get("Access-Control-Allow-Headers", "")
            assert "X-Hermes-Session-Id" in allow_headers
            assert "X-Hermes-Session-Key" in allow_headers
            assert "X-Hermes-Profile" in allow_headers
            assert "X-Hermes-Request-Id" in allow_headers

    @pytest.mark.asyncio
    async def test_provided_session_id_is_used_without_api_key(self, adapter):
        """Local no-key mode accepts caller-supplied transcript session IDs."""
        mock_result = {"final_response": "Continuing!", "messages": [], "api_calls": 1}
        mock_db = MagicMock()
        mock_db.get_messages_as_conversation.return_value = []
        adapter._session_db = mock_db
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with (
                patch.object(adapter, "_run_agent", new_callable=AsyncMock) as mock_run,
                patch("gateway.platforms.api_server_runs._resolve_live_session_id", new_callable=AsyncMock,
                      return_value="local-session-123"),
            ):
                mock_run.return_value = (mock_result, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
                resp = await cli.post(
                    "/v1/chat/completions",
                    headers={"X-Hermes-Session-Id": "local-session-123"},
                    json={"model": "hermes-agent", "messages": [{"role": "user", "content": "Continue"}]},
                )
            assert resp.status == 200
            assert resp.headers.get("X-Hermes-Session-Id") == "local-session-123"
            assert mock_run.call_args.kwargs["session_id"] == "local-session-123"
            mock_db.get_messages_as_conversation.assert_called_once_with("local-session-123")

    @pytest.mark.asyncio
    async def test_session_key_accepted_without_api_key(self, adapter):
        """Local no-key mode accepts caller-supplied memory scope, matching /v1/responses."""
        mock_result = {"final_response": "ok", "messages": [], "api_calls": 1}
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            with patch.object(adapter, "_run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = (mock_result, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
                resp = await cli.post(
                    "/v1/chat/completions",
                    headers={"X-Hermes-Session-Key": "whatever"},
                    json={"model": "hermes-agent", "messages": [{"role": "user", "content": "hi"}]},
                )
            assert resp.status == 200
            assert resp.headers.get("X-Hermes-Session-Key") == "whatever"
            assert mock_run.call_args.kwargs["gateway_session_key"] == "whatever"
