"""Configured fast mode reaches newly constructed TUI agents."""

import types

from tui_gateway import server


def test_make_agent_seeds_fast_request_overrides_from_config(monkeypatch):
    captured = {}

    def fake_agent(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(
            model=kwargs.get("model"),
            service_tier=kwargs.get("service_tier"),
            request_overrides=kwargs.get("request_overrides") or {},
        )

    monkeypatch.delenv("HERMES_MODEL", raising=False)
    monkeypatch.delenv("HERMES_INFERENCE_MODEL", raising=False)
    monkeypatch.delenv("HERMES_TUI_PROVIDER", raising=False)
    monkeypatch.setattr(
        server,
        "_load_cfg",
        lambda: {
            "model": {"default": "gpt-5.5", "provider": "openai-codex"},
            "agent": {"service_tier": "fast"},
        },
    )
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda requested=None, target_model=None: {
            "provider": "openai-codex",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "token",
            "api_mode": "codex_responses",
            "credential_pool": None,
        },
    )
    monkeypatch.setattr("run_agent.AIAgent", fake_agent)
    monkeypatch.setattr(server, "_load_enabled_toolsets", lambda: ["file"])
    monkeypatch.setattr(server, "_get_db", lambda: None)

    agent = server._make_agent("sid", "session-key")

    assert agent.model == "gpt-5.5"
    assert agent.service_tier == "priority"
    assert agent.request_overrides == {"service_tier": "priority"}
    assert captured["request_overrides"] == {"service_tier": "priority"}
