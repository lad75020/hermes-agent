"""Behavior retained from the local changes during the upstream rebase."""

from tests.hermes_cli.test_web_server import TestWebServerEndpoints as _WebEndpoints


class TestSessionConversationSearch:
    _setup_test_client = _WebEndpoints._setup_test_client

    def test_search_session_conversations_returns_json_conversations(self):
        from hermes_state import SessionDB

        db = SessionDB()
        try:
            db.create_session("history-search-session", source="cli", model="test-model")
            db.append_message("history-search-session", "user", "please find the dashboard needle")
            db.append_message("history-search-session", "assistant", "the dashboard needle is here")
        finally:
            db.close()

        resp = self.client.get(
            "/api/sessions/search/conversations",
            params={"q": "needle", "limit": "10", "role": "user,assistant"},
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()
        assert data["matched_messages"] >= 1
        assert data["matched_sessions"] == 1
        result = data["results"][0]
        assert result["session_id"] == "history-search-session"
        assert result["session"]["id"] == "history-search-session"
        assert [message["role"] for message in result["messages"]] == ["user", "assistant"]
        assert "needle" in result["matches"][0]["snippet"]
