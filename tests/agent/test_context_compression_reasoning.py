"""Compression completion notifications retain the local structured reasoning contract."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

from agent.conversation_compression_reasoning import emit_compression_reasoning


def test_compress_context_emits_reasoning_json_message():
    emitted = []
    agent = SimpleNamespace(session_id="session-current", reasoning_callback=emitted.append,
                            context_compressor=SimpleNamespace(compression_count=1))
    emit_compression_reasoning(agent, old_session_id="session-parent", messages_before=3,
                               messages_after=2, tokens_before=1234, tokens_after=456)
    assert len(emitted) == 1
    assert json.loads(emitted[0]) == {
        "type": "context_compression", "status": "completed", "message": "Context compressed",
        "session_id": "session-current", "parent_session_id": "session-parent",
        "messages_before": 3, "messages_after": 2, "tokens_before": 1234, "tokens_after": 456,
        "compression_count": 1,
    }


def test_failed_reasoning_observer_does_not_interrupt_compression():
    agent = SimpleNamespace(session_id="session-current", reasoning_callback=Mock(side_effect=RuntimeError),
                            context_compressor=SimpleNamespace(compression_count=1))
    emit_compression_reasoning(agent, old_session_id=None, messages_before=3,
                               messages_after=2, tokens_before=1234, tokens_after=456)
    agent.reasoning_callback.assert_called_once()
