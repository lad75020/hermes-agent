"""Publish a completed compression boundary to reasoning-stream consumers."""

import json
import logging

logger = logging.getLogger(__name__)


def emit_compression_reasoning(
    agent, *, old_session_id, messages_before, messages_after, tokens_before, tokens_after,
):
    """Report committed compaction without letting an observer interrupt the turn."""
    callback = getattr(agent, "reasoning_callback", None)
    if not callback:
        return
    message = {
        "type": "context_compression",
        "status": "completed",
        "message": "Context compressed",
        "session_id": agent.session_id,
        "parent_session_id": old_session_id,
        "messages_before": messages_before,
        "messages_after": messages_after,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "compression_count": agent.context_compressor.compression_count,
    }
    try:
        callback(json.dumps(message, default=str))
    except Exception:
        logger.debug("Compression reasoning callback failed", exc_info=True)
