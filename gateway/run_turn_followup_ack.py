"""Processing-lifecycle hooks for runner-drained queued follow-ups.

A message that arrives mid-turn is parked in the adapter's pending slot and drained in-band by
``TurnRunner._run_agent_queued_followup``, never by ``BasePlatformAdapter._process_message_background``
— the only other call site for ``on_processing_start`` / ``on_processing_complete``. Without firing
them here every adapter that renders a read-receipt reaction from the hooks silently skips queued,
interrupting and steer-demoted messages (#72502, salvage #72503).
"""

from __future__ import annotations

import asyncio
import logging

from gateway.platforms.base import BasePlatformAdapter, MessageEvent, ProcessingOutcome


def retain_processing_reply(event: MessageEvent | None, source, reply: str) -> None:
    """Keep a queued turn's own reply before a later turn replaces the chain's result."""
    from gateway.run import _sanitize_gateway_final_response

    if event is not None and event._processing_final_response is None:
        event.retain_processing_reply(_sanitize_gateway_final_response(source.platform, reply))


def shape_turn_reply(result, source, *, history_len=0, display_kind=None, reply_expected=None):
    """Apply the same text policy before normal delivery and queued completion hooks."""
    from agent.i18n import t
    from gateway.response_filters import (
        is_intentional_silence_agent_result, is_machinery_display_kind, silence_allowed,
    )
    from gateway.run import (
        _is_gateway_hidden_reasoning_incomplete_turn, _normalize_empty_agent_response,
        _sanitize_gateway_final_response,
    )
    from gateway.run_turn import _unexpected_silence_reply

    response = result.get("final_response") or ""
    if _is_gateway_hidden_reasoning_incomplete_turn(result):
        response = ""
    intentional_silence = is_intentional_silence_agent_result(result, response)
    kind = result.get("queued_terminal_display_kind", display_kind)
    expected = result.get("queued_terminal_reply_expected", reply_expected)
    if intentional_silence and not silence_allowed(kind, expected):
        logging.getLogger("gateway.run").warning(
            "silence marker rejected on a user turn: platform=%s chat=%s", source.platform, source.chat_id)
        intentional_silence = False
        response = _unexpected_silence_reply()
    elif intentional_silence and not is_machinery_display_kind(kind):
        logging.getLogger("gateway.run").debug(
            "silence marker suppressed on an unaddressed turn: platform=%s chat=%s", source.platform, source.chat_id)
    if response == "(empty)" and not intentional_silence:
        from agent.turn_explainers import EMPTY_RESPONSE_EXPLANATION
        model = str(result.get("model") or "").strip() or t("gateway.errors.empty_response_model_label")
        response = t("gateway.shared.warn_passthrough", error=EMPTY_RESPONSE_EXPLANATION.format(model=model))
    if not intentional_silence:
        response = _normalize_empty_agent_response(result, response, history_len=history_len)
        response = _sanitize_gateway_final_response(source.platform, response)
    return response, intentional_silence



def retain_interrupted_reply(event: MessageEvent | None, result) -> None:
    """An interrupted turn owns a canceled completion before its successor starts."""
    if event is not None and result.get("interrupted"):
        event.retain_processing_reply("", ProcessingOutcome.CANCELLED)


def retain_followup_reply(event: MessageEvent | None, source, result, *, history_len, display_kind, reply_expected):
    """Shape terminal replies without overwriting a result retained before recursion."""
    if event is None or event._processing_final_response is not None:
        return
    reply, silent = shape_turn_reply(
        result, source, history_len=history_len, display_kind=display_kind, reply_expected=reply_expected,
    )
    retain_processing_reply(event, source, "" if silent or result.get("_notification_reply_muted") else reply)


def _followup_processing_hooks_apply(adapter, event: MessageEvent | None) -> bool:
    """Both conditions are necessary: a real inbound platform message to acknowledge (adapters key their
    marker off ``message_id`` — Slack/Telegram/Feishu/Matrix/Photon — or off ``raw_message`` — Signal,
    Discord; synthetic drains such as ``/goal`` continuations, wake-ups and startup auto-resume carry
    neither and must stay silent), and an adapter that overrides ``on_processing_start``. We bracket, so
    both halves must belong to us: a complete-only adapter (Google Chat reaps its typing card there,
    webhook ends its per-delivery session) would otherwise be handed a completion for a turn whose reply
    is delivered only after the drain chain unwinds back into ``_process_message_background``."""
    if adapter is None or event is None:
        return False
    if not (getattr(event, "message_id", None) or getattr(event, "raw_message", None)):
        return False
    start_hook = getattr(type(adapter), "on_processing_start", None)
    return start_hook is not None and start_hook is not BasePlatformAdapter.on_processing_start


def _followup_cancel_outcome(adapter) -> ProcessingOutcome:
    """Classify a cancelled follow-up exactly as ``_process_message_background`` does: only cancels the
    adapter itself routed (``/stop``, ``/new``, ``/reset``, cleanup) are CANCELLED, anything else is a
    failure. Signal and Matrix leave the in-progress marker in place on CANCELLED, so reporting an
    unexpected cancellation as CANCELLED would strand it."""
    expected = getattr(adapter, "_expected_cancelled_tasks", None)
    if expected is None:
        return ProcessingOutcome.FAILURE
    try:
        current = asyncio.current_task()
    except RuntimeError:
        current = None
    if current is None:
        return ProcessingOutcome.FAILURE
    try:
        return ProcessingOutcome.CANCELLED if current in expected else ProcessingOutcome.FAILURE
    except TypeError:
        return ProcessingOutcome.FAILURE


async def _run_followup_processing_hook(adapter, event: MessageEvent | None, hook_name: str, *args) -> None:
    """Fire one lifecycle hook for a runner-drained follow-up; no-op per ``_followup_processing_hooks_apply``."""
    if not _followup_processing_hooks_apply(adapter, event):
        return
    run_hook = getattr(adapter, "_run_processing_hook", None)
    if not callable(run_hook):
        return
    await run_hook(hook_name, event, *args)
