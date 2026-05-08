"""Behavior retained from the local changes during the upstream rebase."""

from unittest.mock import MagicMock, patch

from agent.title_generator import (
    generate_title_from_response_text, auto_title_session_from_response, maybe_auto_title_from_response,
)


class TestAPIResponseTitle:
    """Tests for API response-only title generation."""

    def test_uses_required_prompt_and_caps_under_50_chars(self):
        captured_kwargs = {}

        def mock_call_llm(**kwargs):
            captured_kwargs.update(kwargs)
            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message.content = "A" * 80
            return resp

        with patch("agent.title_generator.call_llm", side_effect=mock_call_llm):
            title = generate_title_from_response_text("This is the first API response body")

        assert len(title) == 49
        assert title.endswith("...")
        assert captured_kwargs["task"] == "title_generation"
        assert captured_kwargs["messages"] == [
            {
                "role": "user",
                "content": "Provide a title of less than 50 characters for the following text : This is the first API response body",
            }
        ]

    def test_auto_title_from_response_sets_existing_session_title(self):
        db = MagicMock()
        db.get_session.return_value = {"id": "api-session"}
        db.get_session_title.return_value = None

        with patch("agent.title_generator.generate_title_from_response_text", return_value="Friendly API Title"):
            auto_title_session_from_response(db, "api-session", "assistant response")

        db.set_auto_title.assert_called_once_with("api-session", "Friendly API Title", source="llm")

    def test_auto_title_from_response_skips_missing_session_row(self):
        db = MagicMock()
        db.get_session.return_value = None
        db.get_session_title.return_value = None

        with patch("agent.title_generator.generate_title_from_response_text") as gen:
            auto_title_session_from_response(db, "missing", "assistant response")

        gen.assert_not_called()
        db.set_session_title.assert_not_called()

    def test_maybe_auto_title_from_response_skips_later_turns(self):
        history = [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "one"},
            {"role": "user", "content": "two"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
        ]
        with patch("agent.title_generator.auto_title_session_from_response") as mock_auto:
            maybe_auto_title_from_response(MagicMock(), "sess", "third response", history)
        mock_auto.assert_not_called()
