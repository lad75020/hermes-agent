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

def test_desktop_session_search_stamps_the_requested_profile(monkeypatch):
    monkeypatch.setattr(
        _rt_sessions, "_cron_profile_home", lambda profile: (profile, None)
    )
    monkeypatch.setattr(
        _rt_sessions,
        "_open_session_db_for_profile",
        lambda profile, *, read_only: _FakeSessionDB(read_only=read_only),
    )

    response = asyncio.run(
        _rt_sessions.search_sessions(q="20260603", limit=2, profile="worker")
    )

    assert {
        (row["profile"], row["is_default_profile"])
        for row in response["results"]
    } == {("worker", False)}

def test_desktop_session_search_attaches_profile_to_rich_results(monkeypatch):
    class _RichFakeSessionDB(_FakeSessionDB):
        def get_session_rich_row(self, session_id):
            return {
                "id": session_id,
                "source": "cli",
                "model": "claude",
                "title": "Custom Title",
                "started_at": 100,
                "ended_at": None,
                "last_active": 100,
                "message_count": 2,
                "tool_call_count": 0,
                "input_tokens": 10,
                "output_tokens": 20,
                "preview": "Test preview",
                "parent_session_id": None,
                "archived": False,
            }

    monkeypatch.setattr("hermes_state.SessionDB", _RichFakeSessionDB)
    monkeypatch.setattr("hermes_cli.profiles.profile_exists", lambda name: True)
    response = asyncio.run(_rt_sessions.search_sessions(q="20260603", limit=1, profile="personal"))
    assert response["results"][0]["profile"] == "personal"
    assert response["results"][0]["title"] == "Custom Title"

class _DeepLineageSessionDB(_FakeSessionDB):
    """A compression lineage deeper than the chain walk's defensive bound.

    Sessions s000..s178 form one in-place-compression lineage (each session's
    parent ended with end_reason='compression'). The forward chain walk is
    bounded; the bug remapped the SEARCH hit via tip(root), which truncates to
    a stale mid id, while the CLI resumes from the matched id and reaches the
    live tip (#125041).
    """

    DEPTH = 1101
    TIP = "s1100"
    MID = "s100"

    def search_sessions_by_id(self, query, limit=20, include_archived=True,
                              source=None, sources=None, exclude_sources=None):
        return []  # pragma: no cover - content-hit path only in this test

    def search_messages(self, query, source_filter=None, exclude_sources=None,
                        limit=20, fields=None):
        return [{
            "session_id": self.MID,
            "snippet": "content hit inside a deep lineage",
            "role": "assistant",
            "source": "desktop",
            "model": "gpt",
            "session_started": 200,
        }][:limit]

    def get_session(self, session_id):
        parent = None
        if session_id != "s000":
            parent = f"s{int(session_id[1:]) - 1:03d}"
        n = int(session_id[1:])
        return {"id": session_id, "parent_session_id": parent,
                "end_reason": "compression",
                "ended_at": n + 1, "started_at": n}

    def get_compression_tip(self, session_id):
        # Faithful simulation of the REAL bounded forward walk in
        # SessionDB.get_compression_chain: at most _CHAIN_CAP hops from the
        # START id, so a lineage deeper than the cap truncates when the walk
        # starts far from the tip. Resolving from the MATCHED id keeps the
        # remaining distance under the cap; the raised bound lets even a
        # root-started walk terminate at the live tip (#125041).
        from hermes_state_compression import _CHAIN_CAP

        idx = int(session_id[1:])
        return f"s{min(idx + _CHAIN_CAP, self.DEPTH - 1):03d}"

def test_deep_lineage_search_resolves_tip_from_matched_id(monkeypatch):
    monkeypatch.setattr("hermes_state.SessionDB", _DeepLineageSessionDB)

    response = asyncio.run(_rt_sessions.search_sessions(q="content", limit=2))

    [row] = response["results"]
    # The resume id MUST be the live tip — not a stale mid the bounded
    # root-started walk truncated to.
    assert row["session_id"] == _DeepLineageSessionDB.TIP
    # Dedupe/lineage bookkeeping stays keyed by the root.
    assert row["lineage_root"] == "s000"
