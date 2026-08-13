"""Explicit profile selection takes precedence over a stale live-session model."""

from tui_gateway import methods_complete


def test_explicit_profile_ignores_stale_session_agent(monkeypatch):
    agent = object()
    monkeypatch.setattr(methods_complete, "_sessions", {"sid": {"agent": agent}})
    assert methods_complete._session_agent({"session_id": "sid", "profile": "other"}) is None


def test_session_without_explicit_profile_retains_live_agent(monkeypatch):
    agent = object()
    monkeypatch.setattr(methods_complete, "_sessions", {"sid": {"agent": agent}})
    assert methods_complete._session_agent({"session_id": "sid"}) is agent
