"""Behavior retained from the local changes during the upstream rebase."""

from unittest.mock import MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from tests.gateway.test_api_server import _create_app, adapter as adapter


class TestAPIDebugEvents:
    @pytest.mark.asyncio
    async def test_profiles_returns_hermes_profiles(self, adapter):
        fake_profile = MagicMock()
        fake_profile.name = "coder"
        fake_profile.is_default = False
        fake_profile.model = "anthropic/claude-sonnet-4"
        fake_profile.provider = "anthropic"
        fake_profile.gateway_running = False
        fake_profile.skill_count = 12
        app = _create_app(adapter)
        with patch("hermes_cli.profiles.list_profiles", return_value=[fake_profile]):
            async with TestClient(TestServer(app)) as cli:
                resp = await cli.get("/v1/profiles")
                assert resp.status == 200
                data = await resp.json()
                assert data["object"] == "list"
                assert data["data"][0]["id"] == "coder"
                assert data["data"][0]["object"] == "hermes.profile"
                assert data["data"][0]["model"] == "anthropic/claude-sonnet-4"

    def test_parse_profile_header_validates_known_profile(self, adapter):
        request = MagicMock()
        request.headers = {"X-Hermes-Profile": "Coder"}
        with (
            patch("hermes_cli.profiles.normalize_profile_name", return_value="coder"),
            patch("hermes_cli.profiles.validate_profile_name"),
            patch("hermes_cli.profiles.profile_exists", return_value=True),
        ):
            profile, err = adapter._parse_profile_header(request)
        assert err is None
        assert profile == "coder"

    def test_parse_profile_header_rejects_unknown_profile(self, adapter):
        request = MagicMock()
        request.headers = {"X-Hermes-Profile": "missing"}
        with (
            patch("hermes_cli.profiles.normalize_profile_name", return_value="missing"),
            patch("hermes_cli.profiles.validate_profile_name"),
            patch("hermes_cli.profiles.profile_exists", return_value=False),
        ):
            profile, err = adapter._parse_profile_header(request)
        assert profile == "default"
        assert err.status == 404

    @pytest.mark.asyncio
    async def test_stream_includes_reasoning_summary_and_tool_output_events(self, adapter):
        """Chat-completions streaming exposes Hermes debug SSE events for reasoning and tool output."""
        import json as _json

        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            async def _mock_run_agent(**kwargs):
                reasoning_cb = kwargs.get("reasoning_callback")
                ts_cb = kwargs.get("tool_start_callback")
                tc_cb = kwargs.get("tool_complete_callback")
                cb = kwargs.get("stream_delta_callback")
                if reasoning_cb:
                    reasoning_cb("Need to inspect the filesystem.")
                if ts_cb:
                    ts_cb("call_terminal_1", "terminal", {"command": "pwd"})
                if tc_cb:
                    tc_cb("call_terminal_1", "terminal", {"command": "pwd"}, {"output": "/tmp\\n", "exit_code": 0})
                if cb:
                    cb("done.")
                return (
                    {"final_response": "done.", "messages": [], "api_calls": 1},
                    {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                )

            with patch.object(adapter, "_run_agent", side_effect=_mock_run_agent):
                resp = await cli.post(
                    "/v1/chat/completions",
                    json={
                        "model": "test",
                        "messages": [{"role": "user", "content": "debug"}],
                        "stream": True,
                    },
                )
                assert resp.status == 200
                body = await resp.text()

        assert "event: Hermes.reasoning.summary" in body
        assert "Need to inspect the filesystem." in body
        assert "event: Hermes.tool.output" in body
        assert '"tool": "terminal"' in body
        assert '"toolCallId": "call_terminal_1"' in body
        assert "/tmp" in body

        for line in body.splitlines():
            if not line.startswith("data: ") or line.strip() == "data: [DONE]":
                continue
            try:
                chunk = _json.loads(line[len("data: "):])
            except _json.JSONDecodeError:
                continue
            if chunk.get("object") == "chat.completion.chunk":
                content = "".join(choice.get("delta", {}).get("content", "") for choice in chunk.get("choices", []))
                assert "Need to inspect" not in content
                assert "/tmp" not in content
