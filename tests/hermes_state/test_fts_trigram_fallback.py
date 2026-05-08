"""Base FTS search remains available on SQLite builds without trigram."""

import sqlite3

from hermes_state import SessionDB


class _NoTrigramCursor(sqlite3.Cursor):
    def executescript(self, sql_script):
        if "tokenize='trigram'" in sql_script:
            raise sqlite3.OperationalError("no such tokenizer: trigram")
        return super().executescript(sql_script)


class _NoTrigramConnection(sqlite3.Connection):
    def cursor(self, factory=None):
        return super().cursor(factory or _NoTrigramCursor)


def test_session_db_falls_back_when_trigram_tokenizer_is_unavailable(tmp_path, monkeypatch):
    real_connect = sqlite3.connect

    def connect(*args, **kwargs):
        kwargs["factory"] = _NoTrigramConnection
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    with SessionDB(tmp_path / "state.db") as db:
        db.create_session("fallback-session", source="cli", model="test-model")
        db.append_message("fallback-session", "user", "ordinary fallback search needle")
        results = db.search_messages("needle", limit=5)
        assert results
        assert results[0]["session_id"] == "fallback-session"
