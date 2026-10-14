"""A2A tasks own complete turn replies, independently of streaming delivery fragments."""

import asyncio
import io
import json
import time
from types import SimpleNamespace

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.event import MessageEvent, ProcessingOutcome
from gateway.stream_consumer import GatewayStreamConsumer, StreamConsumerConfig
from plugins.platforms.a2a import protocol
from plugins.platforms.a2a.adapter import A2AAdapter


FULL_REPLY = "The callback carries the entire sentence from beginning to end."


@pytest.mark.asyncio
@pytest.mark.parametrize("rpc_stream", [False, True], ids=["SendMessage", "SendStreamingMessage"])
@pytest.mark.parametrize("delivery", ["suffix", "whole-preview", "normal", "tools", "empty-fragment", "empty"])
async def test_rpc_returns_authoritative_turn_reply(monkeypatch, rpc_stream, delivery):
    adapter = A2AAdapter(PlatformConfig(enabled=True, typing_indicator=False))
    adapter._loop = asyncio.get_running_loop()
    sends = []
    preview_sent = asyncio.Event()
    original_send = adapter.send

    async def record_send(chat_id, content, reply_to=None, metadata=None):
        result = await original_send(chat_id, content, reply_to=reply_to, metadata=metadata)
        sends.append((content, metadata or {}))
        preview_sent.set()
        return result

    monkeypatch.setattr(adapter, "send", record_send)

    async def turn(event):
        if delivery == "normal":
            return FULL_REPLY
        if delivery == "empty":
            return ""
        consumer = GatewayStreamConsumer(adapter, event.source.chat_id, StreamConsumerConfig(
            edit_interval=0, buffer_threshold=1, cursor="", transport="edit"))
        if delivery == "empty-fragment":
            await adapter.send(event.source.chat_id, "", metadata={"notify": True})
        if delivery == "tools":
            await consumer._send_commentary("Checking a tool before answering.")
            await adapter.send(event.source.chat_id, "Tool segment", metadata={"notify": True, "_interim_send": True})
            preview_sent.clear()
        stream_task = asyncio.create_task(consumer.run())
        consumer.on_delta(FULL_REPLY if delivery == "whole-preview" else "The callback carries the entire sentence ")
        await asyncio.wait_for(preview_sent.wait(), timeout=5)
        consumer.finish(FULL_REPLY)
        await stream_task
        # This is the gateway's already_sent contract: the normal send is suppressed,
        # but the full sanitized response is retained on this exact inbound event.
        event._streamed_final_response = FULL_REPLY
        return None

    adapter._message_handler = turn

    async def dispatch(event):
        await adapter._process_message_background(event, adapter._source_session_key(event.source))

    monkeypatch.setattr(adapter, "handle_message", dispatch)
    params = {"message": protocol.text_message(protocol.ROLE_USER, "Reply with exactly: " + FULL_REPLY, context_id="reply-context")}
    if rpc_stream:
        handler = SimpleNamespace(wfile=io.BytesIO(), send_response=lambda *_: None,
                                  send_header=lambda *_: None, end_headers=lambda: None)
        await asyncio.to_thread(adapter._rpc_message_stream, handler, 1, params, "peer")
        frames = [json.loads(line[6:])["result"] for line in handler.wfile.getvalue().decode().splitlines()
                  if line.startswith("data: ")]
        reply = next((f["artifactUpdate"]["artifact"]["parts"][0]["text"] for f in frames if "artifactUpdate" in f), "")
        assert frames[-1]["statusUpdate"]["status"]["state"] == protocol.STATE_COMPLETED
        task_id = frames[-1]["statusUpdate"]["taskId"]
    else:
        result = await asyncio.to_thread(adapter._rpc_message_send, 1, params, "peer", v1_response=True)
        task = result["result"]["task"]
        reply = protocol.extract_text(task["status"].get("message", {}))
        assert task["status"]["state"] == protocol.STATE_COMPLETED
        task_id = task["id"]
        if delivery != "empty":
            assert task["artifacts"][0]["parts"][0]["text"] == FULL_REPLY
    assert reply == ("" if delivery == "empty" else FULL_REPLY)
    stored = adapter._rpc_tasks_get(2, {"taskId": task_id})["result"]
    assert protocol.extract_text(stored["status"].get("message", {})) == reply
    assert not adapter._pending and not adapter._active_tasks
    if delivery == "suffix":
        assert any(text == "from beginning to end." and md.get("notify") for text, md in sends)


@pytest.mark.asyncio
async def test_completion_owns_task_even_with_shared_context_and_late_sends():
    adapter = A2AAdapter(PlatformConfig(enabled=True))
    first = adapter._add_pending("first", "shared")
    second = adapter._add_pending("second", "shared")
    other = adapter._add_pending("other", "other-context")
    await adapter.send("shared", "interim", metadata={"notify": True})
    assert not first.done() and not second.done() and not other.done()
    await adapter.on_processing_complete(SimpleNamespace(message_id="second", _processing_final_response="second full"), ProcessingOutcome.SUCCESS)
    assert second.result(timeout=0) == (protocol.STATE_COMPLETED, "second full")
    assert not first.done() and not other.done()
    await adapter.send("shared", "late suffix", metadata={"notify": True})
    await adapter.on_processing_complete(SimpleNamespace(message_id="first", _processing_final_response="first full"), ProcessingOutcome.SUCCESS)
    assert first.result(timeout=0) == (protocol.STATE_COMPLETED, "first full")
    assert not other.done()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,state", [(ProcessingOutcome.FAILURE, protocol.STATE_FAILED),
                                          (ProcessingOutcome.CANCELLED, protocol.STATE_CANCELED)])
async def test_preview_cannot_hide_failure_or_cancellation(outcome, state):
    adapter = A2AAdapter(PlatformConfig(enabled=True))
    future = adapter._add_pending("task", "context")
    await adapter.send("context", "preview", metadata={"notify": True})
    await adapter.on_processing_complete(MessageEvent(text="request", message_id="task"), outcome)
    assert future.result(timeout=0)[0] == state


@pytest.mark.asyncio
async def test_authoritative_reply_still_redacts_and_requests_input():
    adapter = A2AAdapter(PlatformConfig(enabled=True))
    adapter.tasks.create("task", "context", "peer")
    future = adapter._add_pending("task", "context")
    event = MessageEvent(text="request", message_id="task")
    event._processing_final_response = "[INPUT_REQUIRED] Confirm contact alice@example.com before proceeding."
    await adapter.send("context", "unrelated preview", metadata={"notify": True})
    await adapter.on_processing_complete(event, ProcessingOutcome.SUCCESS)
    state, reply = adapter._finalize_task(
        {"task_id": "task", "context_id": "context", "peer": "peer", "started": time.time()},
        *future.result(timeout=0))
    assert state == protocol.STATE_INPUT_REQUIRED
    assert reply == "Confirm contact [redacted-email] before proceeding."
    assert adapter.tasks.get("task")["reply"] == reply


@pytest.mark.asyncio
async def test_queued_a2a_turns_keep_their_own_complete_replies(monkeypatch, tmp_path):
    from tests.gateway.test_queued_followup_processing_hooks import (
        _install_fake_agent, _make_runner, _TwoTurnAgent,
    )

    _TwoTurnAgent.calls = []
    _install_fake_agent(monkeypatch, tmp_path, _TwoTurnAgent)
    adapter = A2AAdapter(PlatformConfig(enabled=True, typing_indicator=False))
    runner = _make_runner(adapter)
    source = adapter.build_source(chat_id="shared", chat_type="dm", user_id="peer")
    session_key = adapter._source_session_key(source)
    first = adapter._add_pending("first", "shared")
    second = adapter._add_pending("second", "shared")
    adapter._pending_messages[session_key] = MessageEvent(text="second", source=source, message_id="second")

    async def turn(event):
        result = await runner._run_agent(message=event.text, context_prompt="", history=[], source=source,
                                        session_id="queued-a2a", session_key=session_key, inbound_event=event)
        return result["final_response"]

    adapter._message_handler = turn
    await adapter._process_message_background(MessageEvent(text="first", source=source, message_id="first"), session_key)
    assert _TwoTurnAgent.calls == ["first", "second"]
    assert first.result(timeout=0) == (protocol.STATE_COMPLETED, "done-1")
    assert second.result(timeout=0) == (protocol.STATE_COMPLETED, "done-2")


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [False, True])
async def test_prompt_rewrite_reaches_handler_and_original_completion(monkeypatch, tmp_path, streamed):
    from unittest.mock import AsyncMock
    from hermes_state import SessionDB
    from tests.gateway.test_first_turn_session_meta_rebaseline import _bootstrap, SESSION_ID

    db = SessionDB(db_path=tmp_path / "rewrite.db")
    db.create_session(SESSION_ID, source="a2a")
    runner = _bootstrap(monkeypatch, tmp_path, db)
    adapter = A2AAdapter(PlatformConfig(enabled=True, typing_indicator=False))
    runner.adapters = {adapter.platform: adapter}
    source = adapter.build_source(chat_id="rewrite-context", chat_type="dm", user_id="peer")
    key = adapter._source_session_key(source)
    monkeypatch.setattr("hermes_cli.lifecycle.ainvoke_hook", AsyncMock(
        return_value=[{"action": "rewrite", "text": "optimized request"}]))
    runner._run_agent = AsyncMock(return_value={
        "final_response": FULL_REPLY, "messages": [], "already_sent": streamed,
    })
    adapter._message_handler = runner._handle_message
    future = adapter._add_pending("rewrite-task", source.chat_id)
    event = MessageEvent(text="original request", source=source, message_id="rewrite-task")
    await adapter._process_message_background(event, key)
    assert runner._run_agent.call_args.kwargs["message"] == "optimized request"
    assert future.result(timeout=0) == (protocol.STATE_COMPLETED, FULL_REPLY)
    db.close()


@pytest.mark.asyncio
async def test_interrupted_middle_queued_task_does_not_take_successors_reply(monkeypatch, tmp_path):
    from tests.gateway.test_queued_followup_processing_hooks import _install_fake_agent, _make_runner, _TwoTurnAgent

    adapter = A2AAdapter(PlatformConfig(enabled=True, typing_indicator=False))
    source = adapter.build_source(chat_id="interrupt-context", chat_type="dm", user_id="peer")
    key = adapter._source_session_key(source)

    class InterruptedMiddleAgent(_TwoTurnAgent):
        calls = []

        def run_conversation(self, message, **kwargs):
            result = super().run_conversation(message, **kwargs)
            if message == "B":
                adapter._pending_messages[key] = MessageEvent(text="C", source=source, message_id="C")
                result.update(interrupted=True, final_response="Operation interrupted.")
            return result

    _install_fake_agent(monkeypatch, tmp_path, InterruptedMiddleAgent)
    runner = _make_runner(adapter)
    futures = {name: adapter._add_pending(name, source.chat_id) for name in ("A", "B", "C")}
    adapter._pending_messages[key] = MessageEvent(text="B", source=source, message_id="B")

    async def handler(event):
        result = await runner._run_agent(message=event.text, context_prompt="", history=[], source=source,
                                        session_id="interrupt-chain", session_key=key, inbound_event=event)
        return result["final_response"]

    adapter._message_handler = handler
    await adapter._process_message_background(MessageEvent(text="A", source=source, message_id="A"), key)
    assert InterruptedMiddleAgent.calls == ["A", "B", "C"]
    assert futures["A"].result(timeout=0) == (protocol.STATE_COMPLETED, "done-1")
    assert futures["B"].result(timeout=0) == (protocol.STATE_CANCELED, "")
    assert futures["C"].result(timeout=0) == (protocol.STATE_COMPLETED, "done-3")


@pytest.mark.asyncio
@pytest.mark.parametrize("reply_expected", [None, False])
async def test_terminal_queued_silence_is_shaped_before_task_completion(monkeypatch, tmp_path, reply_expected):
    from gateway.run_turn import _unexpected_silence_reply
    from tests.gateway.test_queued_followup_processing_hooks import _install_fake_agent, _make_runner, _TwoTurnAgent

    class SilentLastAgent(_TwoTurnAgent):
        calls = []

        def run_conversation(self, message, **kwargs):
            result = super().run_conversation(message, **kwargs)
            if message == "last":
                result["final_response"] = "[SILENT]"
            return result

    _install_fake_agent(monkeypatch, tmp_path, SilentLastAgent)
    adapter = A2AAdapter(PlatformConfig(enabled=True, typing_indicator=False))
    runner = _make_runner(adapter)
    source = adapter.build_source(chat_id="silent-context", chat_type="dm", user_id="peer")
    key = adapter._source_session_key(source)
    future = adapter._add_pending("last", source.chat_id)
    adapter._pending_messages[key] = MessageEvent(text="last", source=source, message_id="last", reply_expected=reply_expected)
    await runner._run_agent(message="first", context_prompt="", history=[], source=source,
                            session_id="silent-chain", session_key=key)
    expected = "" if reply_expected is False else _unexpected_silence_reply()
    assert future.result(timeout=0) == (protocol.STATE_COMPLETED, expected)
