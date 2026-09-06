import asyncio

from hermes_cli import web_server
import hermes_cli.web_routers.sessions as _rt_sessions


class _FakeSessionDB:
    """Fake backing the /api/sessions/search endpoint.

    The endpoint surfaces direct session-id matches first, then FTS message
    matches, deduping both by compression lineage root. This fake has no
    compression chains (get_session returns no parent), so each session is its
    own lineage root.
    """

    closed = False
    opened_read_only = None
    requested_fields = None

    def __init__(self, *args, **kwargs):
        type(self).opened_read_only = kwargs.get("read_only")

    @staticmethod
    def _source_allowed(row, source=None, sources=None, exclude_sources=None):
        row_source = row.get("source")
        if source and row_source != source:
            return False
        if sources and row_source not in sources:
            return False
        if exclude_sources and row_source in exclude_sources:
            return False
        return True

    def search_sessions_by_id(
        self,
        query,
        limit=20,
        include_archived=True,
        source=None,
        sources=None,
        exclude_sources=None,
    ):
        assert query == "20260603"
        assert include_archived is True
        rows = [
            {
                "id": "20260603_090200_exact",
                "preview": "ID match preview",
                "source": "cli",
                "model": "claude",
                "started_at": 100,
            }
        ]
        return [
            row
            for row in rows
            if self._source_allowed(
                row, source=source, sources=sources, exclude_sources=exclude_sources
            )
        ][:limit]

    def search_messages(
        self,
        query,
        source_filter=None,
        exclude_sources=None,
        limit=20,
        fields=None,
    ):
        assert query == "20260603*"
        type(self).requested_fields = fields
        rows = [
            {
                "session_id": "20260603_090200_exact",
                "snippet": "duplicate content hit should not replace ID hit",
                "role": "user",
                "source": "cli",
                "model": "claude",
                "session_started": 100,
            },
            {
                "session_id": "content_session",
                "snippet": "content hit",
                "role": "assistant",
                "source": "desktop",
                "model": "gpt",
                "session_started": 200,
            },
        ]
        return [
            row
            for row in rows
            if self._source_allowed(
                row, sources=source_filter, exclude_sources=exclude_sources
            )
        ][:limit]

    def get_session(self, session_id):
        # No compression chains in this fixture — every session is its own root.
        return {"id": session_id, "parent_session_id": None}

    def get_compression_tip(self, session_id):
        return session_id

    def close(self):
        self.closed = True


def test_desktop_session_search_merges_id_matches_before_content_matches(monkeypatch):
    _FakeSessionDB.opened_read_only = None
    _FakeSessionDB.requested_fields = None
    monkeypatch.setattr("hermes_state.SessionDB", _FakeSessionDB)

    response = asyncio.run(_rt_sessions.search_sessions(q="20260603", limit=2))

    assert _FakeSessionDB.requested_fields is not None
    assert "context" not in _FakeSessionDB.requested_fields
    # ID match surfaces first; the content hit on the SAME session is deduped
    # by lineage root (not double-listed); the unrelated content hit follows.
    assert response == {
        "results": [
            {
                "id": "20260603_090200_exact",
                "session_id": "20260603_090200_exact",
                "lineage_root": "20260603_090200_exact",
                "snippet": "ID match preview",
                "role": None,
                "source": "cli",
                "model": "claude",
                "session_started": 100,
            },
            {
                "id": "content_session",
                "session_id": "content_session",
                "lineage_root": "content_session",
                "snippet": "content hit",
                "role": "assistant",
                "source": "desktop",
                "model": "gpt",
                "session_started": 200,
            },
        ]
    }
    assert _FakeSessionDB.opened_read_only is True


class _ConversationSessionDB:
    def __init__(self):
        self.closed = False
        self.search_kwargs = None

    def search_conversations(self, **kwargs):
        self.search_kwargs = kwargs
        return {
            "matches": [
                {"session_id": "session-a", "role": "assistant", "snippet": "representative"},
                {"session_id": "session-a", "role": "user", "snippet": "another hit"},
            ],
            "matched_messages": 7,
            "matched_sessions": 6,
            "next_offset": 3,
            "snapshot_max_message_id": 42,
        }

    def get_session(self, session_id):
        return {"id": session_id, "title": "Conversation A"} if session_id == "session-a" else None

    def get_messages(self, session_id):
        raise AssertionError("summary view must not load the complete transcript")

    def get_history_summary_messages(self, session_ids):
        assert session_ids == ["session-a"]
        return {"session-a": [
            {"role": "user", "content": "full conversation"},
            {"role": "assistant", "content": "terminal answer", "tool_calls": None},
        ]}

    def close(self):
        self.closed = True


def test_full_conversation_search_is_profile_scoped_and_expands_matches(monkeypatch):
    db = _ConversationSessionDB()
    opened = []
    monkeypatch.setattr(
        _rt_sessions,
        "_open_session_db_for_profile",
        lambda profile, *, read_only: opened.append((profile, read_only)) or db,
    )

    response = asyncio.run(_rt_sessions.search_session_conversations(
        q="needle", limit=5, offset=2, source="cli, desktop",
        role="user,assistant,tool", profile="Work", snapshot_max_message_id=42,
        message_view="summary"))

    assert opened == [("Work", True)]
    assert db.search_kwargs == {
        "query": "needle",
        "source_filter": ["cli", "desktop"],
        "role_filter": ["user", "assistant"],
        "limit": 5,
        "offset": 2,
        "final_answers_only": True,
        "snapshot_max_message_id": 42,
    }
    assert response == {
        "results": [{
            "session_id": "session-a",
            "session": {"id": "session-a", "title": "Conversation A"},
            "matches": [
                {"session_id": "session-a", "role": "assistant", "snippet": "representative"},
                {"session_id": "session-a", "role": "user", "snippet": "another hit"},
            ],
            "messages": [
                {"role": "user", "content": "full conversation"},
                {"role": "assistant", "content": "terminal answer"},
            ],
        }],
        "limit": 5,
        "offset": 2,
        "matched_messages": 7,
        "matched_sessions": 6,
        "has_more": True,
        "next_offset": 3,
        "snapshot_max_message_id": 42,
    }
    assert db.closed is True


def test_history_summary_wire_message_is_minimal_and_content_bounded():
    message = {
        "id": 7,
        "role": "assistant",
        "content": "x" * 20_000,
        "timestamp": 123.0,
        "tool_name": None,
        "reasoning": "must not reach the wire",
        "display_metadata": {"large": "payload"},
    }

    result = _rt_sessions._history_summary_wire_message(message)

    assert set(result) == {"id", "role", "content", "timestamp", "content_truncated"}
    assert result["content_truncated"] is True
    assert result["content"].startswith("x" * 8_000)
    assert result["content"].endswith("[Content truncated in history search.]")
    assert len(result["content"]) < 8_100
