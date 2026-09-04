from __future__ import annotations

import sys
from types import SimpleNamespace

from scripts import backfill_session_titles as backfill


class _FakeDB:
    def __init__(self) -> None:
        self.closed = False
        self.writes: list[tuple[str, str, str]] = []

    def close(self) -> None:
        self.closed = True

    def set_auto_title(self, session_id: str, title: str, *, source: str) -> bool:
        self.writes.append((session_id, title, source))
        return True


def test_first_titleable_user_request_skips_control_turns(monkeypatch):
    db = SimpleNamespace(
        get_messages=lambda _session_id: [
            {"role": "assistant", "content": "ignore"},
            {"role": "user", "content": "[System: The active model for this chat has changed to x]"},
            {"role": "user", "content": "Repair session title backfill"},
        ]
    )

    assert (
        backfill._first_titleable_user_request(db, "session-1")
        == "Repair session title backfill"
    )


def test_set_unique_title_uses_llm_provenance_and_lineage_suffix():
    class CollisionDB(_FakeDB):
        def set_auto_title(self, session_id: str, title: str, *, source: str) -> bool:
            self.writes.append((session_id, title, source))
            if len(self.writes) == 1:
                raise ValueError("Title 'Repair sessions' is already in use by session other")
            return True

        @staticmethod
        def get_next_title_in_lineage(_base: str) -> str:
            return "Repair sessions #2"

    db = CollisionDB()

    assert backfill._set_unique_title(db, "session-1", "Repair sessions") == "Repair sessions #2"
    assert db.writes == [
        ("session-1", "Repair sessions", "llm"),
        ("session-1", "Repair sessions #2", "llm"),
    ]


def test_main_dry_run_never_calls_model_or_writes(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(backfill, "SessionDB", lambda *args, **kwargs: db)
    monkeypatch.setattr(
        backfill,
        "_iter_untitled_sessions",
        lambda _db, source=None: iter(
            [{"id": "session-1", "source": source or "cli"}]
        ),
    )
    monkeypatch.setattr(
        backfill,
        "_first_titleable_user_request",
        lambda _db, _session_id: "Repair session title backfill",
    )
    monkeypatch.setattr(
        backfill,
        "generate_title",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("dry-run called the title model")
        ),
    )
    monkeypatch.setattr(sys, "argv", ["backfill_session_titles.py", "--dry-run"])

    assert backfill.main() == 0
    assert db.writes == []
    assert db.closed is True
