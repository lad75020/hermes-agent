"""Dashboard agent-plugin route regression tests."""

from fastapi.testclient import TestClient


def test_agent_plugin_action_routes_accept_namespaced_plugin_keys(monkeypatch):
    """Slash-containing plugin keys must not be shadowed into HTTP 405."""
    from hermes_cli import web_server
    import hermes_cli.plugins_cmd as plugins_cmd

    calls = []

    def fake_set_enabled(name: str, enabled: bool):
        calls.append((name, enabled))
        return {"ok": True, "name": name, "enabled": enabled}

    def fake_update(name: str):
        calls.append((name, "update"))
        return {"ok": True, "name": name}

    monkeypatch.setattr(
        plugins_cmd,
        "dashboard_set_agent_plugin_enabled",
        fake_set_enabled,
    )
    monkeypatch.setattr(plugins_cmd, "dashboard_update_user_plugin", fake_update)
    monkeypatch.setattr(web_server, "_get_dashboard_plugins", lambda *a, **kw: [])

    client = TestClient(web_server.app)
    headers = {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}

    assert client.post(
        "/api/dashboard/agent-plugins/observability/langfuse/enable",
        headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/dashboard/agent-plugins/observability%2Flangfuse/disable",
        headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/dashboard/agent-plugins/observability/langfuse/update",
        headers=headers,
    ).status_code == 200

    assert calls == [
        ("observability/langfuse", True),
        ("observability/langfuse", False),
        ("observability/langfuse", "update"),
    ]


def test_agent_plugin_action_routes_still_accept_single_segment_keys(monkeypatch):
    from hermes_cli import web_server
    import hermes_cli.plugins_cmd as plugins_cmd

    calls = []

    def fake_set_enabled(name: str, enabled: bool):
        calls.append((name, enabled))
        return {"ok": True, "name": name, "enabled": enabled}

    monkeypatch.setattr(
        plugins_cmd,
        "dashboard_set_agent_plugin_enabled",
        fake_set_enabled,
    )

    client = TestClient(web_server.app)
    headers = {web_server._SESSION_HEADER_NAME: web_server._SESSION_TOKEN}

    response = client.post(
        "/api/dashboard/agent-plugins/example-dashboard/enable",
        headers=headers,
    )

    assert response.status_code == 200
    assert calls == [("example-dashboard", True)]
