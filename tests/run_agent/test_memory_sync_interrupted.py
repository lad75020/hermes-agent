"""Regression guard for #15218 — external memory sync must skip interrupted turns.

Before this fix, ``run_conversation`` called
``memory_manager.sync_all(original_user_message, final_response)`` at the
end of every turn where both args were present.  That gate didn't check
the ``interrupted`` flag, so an external memory backend received partial
assistant output, aborted tool chains, or mid-stream resets as durable
conversational truth.  Downstream recall then treated that not-yet-real
state as if the user had seen it complete.

The fix is ``AIAgent._sync_external_memory_for_turn`` — a small helper
that replaces the inline block and returns early when ``interrupted``
is True (regardless of whether ``final_response`` and
``original_user_message`` happen to be populated).

These tests exercise the helper directly on a bare ``AIAgent`` built
via ``__new__`` so the full ``run_conversation`` machinery isn't needed
— the method is pure logic and three state arguments.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _bare_agent():
    """Build an ``AIAgent`` with only the attributes
    ``_sync_external_memory_for_turn`` touches — matches the bare-agent
    pattern used across ``tests/run_agent/test_interrupt_propagation.py``.
    """
    from run_agent import AIAgent

    agent = AIAgent.__new__(AIAgent)
    agent._memory_manager = MagicMock()
    # session_id is now propagated into sync_all / queue_prefetch_all so
    # providers that cache per-session state can update it mid-process
    # (see #6672).
    agent.session_id = "test_session_001"
    return agent


def _finalizer_ready_agent():
    agent = _bare_agent()
    agent.max_iterations = 5
    agent.iteration_budget = SimpleNamespace(remaining=5, used=1, max_total=5)
    agent.quiet_mode = True
    agent.model = "test-model"
    agent.provider = "test-provider"
    agent.base_url = ""
    agent.platform = "tui"
    agent.session_input_tokens = 0
    agent.session_output_tokens = 0
    agent.session_cache_read_tokens = 0
    agent.session_cache_write_tokens = 0
    agent.session_reasoning_tokens = 0
    agent.session_prompt_tokens = 0
    agent.session_completion_tokens = 0
    agent.session_total_tokens = 0
    agent.session_estimated_cost_usd = 0.0
    agent.session_cost_status = "ok"
    agent.session_cost_source = "test"
    agent.context_compressor = SimpleNamespace(last_prompt_tokens=0)
    agent._tool_guardrail_halt_decision = None
    agent._response_was_previewed = False
    agent._interrupt_message = ""
    agent._stream_callback = None
    agent._skill_nudge_interval = 0
    agent._iters_since_skill = 0
    agent.valid_tool_names = []
    agent._turn_failed_file_mutations = {}
    agent._save_trajectory = MagicMock()
    agent._cleanup_task_resources = MagicMock()
    agent._drop_trailing_empty_response_scaffolding = MagicMock()
    agent._persist_session = MagicMock()
    agent._file_mutation_verifier_enabled = MagicMock(return_value=False)
    agent._turn_completion_explainer_enabled = MagicMock(return_value=False)
    agent._drain_pending_steer = MagicMock(return_value=None)
    agent.clear_interrupt = MagicMock()
    agent._spawn_background_review = MagicMock()
    return agent


class TestSyncExternalMemoryForTurn:
    # --- Interrupt guard (the #15218 fix) -------------------------------

    def test_interrupted_turn_does_not_sync(self):
        """The whole point of #15218: even with a final_response and a
        user message, an interrupted turn must NOT reach the memory
        backend."""
        agent = _bare_agent()
        agent._sync_external_memory_for_turn(
            original_user_message="What time is it?",
            final_response="It is 3pm.",  # looks complete — but partial
            interrupted=True,
        )
        agent._memory_manager.sync_all.assert_not_called()
        agent._memory_manager.queue_prefetch_all.assert_not_called()

    def test_interrupted_turn_skips_even_when_response_is_full(self):
        """A long, seemingly-complete assistant response is still
        partial if ``interrupted`` is True — an interrupt may have
        landed between the streamed reply and the next tool call.  The
        memory backend has no way to distinguish on its own, so we must
        gate at the source."""
        agent = _bare_agent()
        agent._sync_external_memory_for_turn(
            original_user_message="Plan a trip to Lisbon",
            final_response="Here's a detailed 7-day itinerary: [...]",
            interrupted=True,
        )
        agent._memory_manager.sync_all.assert_not_called()

    # --- Normal completed turn still syncs ------------------------------

    def test_completed_turn_syncs_and_queues_prefetch(self):
        """Regression guard for the positive path: a normal completed
        turn must still trigger both ``sync_all`` AND
        ``queue_prefetch_all`` — otherwise the external memory backend
        never learns about anything and every user complains.
        """
        agent = _bare_agent()
        agent._sync_external_memory_for_turn(
            original_user_message="What's the weather in Paris?",
            final_response="It's sunny and 22°C.",
            interrupted=False,
        )
        agent._memory_manager.sync_all.assert_called_once_with(
            "What's the weather in Paris?", "It's sunny and 22°C.",
            session_id="test_session_001",
        )
        agent._memory_manager.queue_prefetch_all.assert_called_once_with(
            "What's the weather in Paris?",
            session_id="test_session_001",
        )

    def test_completed_turn_syncs_messages_when_present(self):
        agent = _bare_agent()
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "terminal",
                            "arguments": "{\"command\":\"pytest\"}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "name": "terminal",
                "tool_call_id": "call-1",
                "content": "final Hermes-processed output",
            }
        ]

        agent._sync_external_memory_for_turn(
            original_user_message="run tests",
            final_response="tests passed",
            interrupted=False,
            messages=messages,
        )

        agent._memory_manager.sync_all.assert_called_once_with(
            "run tests",
            "tests passed",
            session_id="test_session_001",
            messages=messages,
        )

    def test_run_conversation_finalizer_syncs_memory_after_successful_turn(self, monkeypatch):
        """Integration guard for the run_conversation post-response boundary.

        The TUI gateway calls ``AIAgent.run_conversation``.  A successful final
        assistant response must reach ``MemoryManager.sync_all`` with the
        original user message, final assistant text, and current message list.
        """
        from agent.turn_finalizer import finalize_turn

        monkeypatch.setattr(
            "hermes_cli.plugins.invoke_hook",
            lambda *args, **kwargs: [],
            raising=False,
        )
        agent = _finalizer_ready_agent()
        messages = [
            {"role": "user", "content": "Remember this completed turn"},
            {"role": "assistant", "content": "Completed response"},
        ]

        result = finalize_turn(
            agent,
            final_response="Completed response",
            api_call_count=1,
            interrupted=False,
            failed=False,
            messages=messages,
            conversation_history=[],
            effective_task_id="test_session_001",
            turn_id="turn-1",
            user_message="Remember this completed turn",
            original_user_message="Remember this completed turn",
            _should_review_memory=False,
            _turn_exit_reason="text_response(finish_reason=stop)",
        )

        assert result["completed"] is True
        assert result["external_memory_synced"] is True
        agent._memory_manager.sync_all.assert_called_once_with(
            "Remember this completed turn",
            "Completed response",
            session_id="test_session_001",
            messages=messages,
        )
        agent._memory_manager.queue_prefetch_all.assert_called_once_with(
            "Remember this completed turn",
            session_id="test_session_001",
        )

    def test_completed_skill_turn_keeps_original_message_for_memory_manager(self):
        """Provider-specific query shaping belongs inside the provider.

        The MemoryManager fan-out contract stays raw so non-OpenViking
        providers can decide for themselves whether slash-skill-expanded
        content is useful.
        """
        agent = _bare_agent()
        skill_message = (
            '[IMPORTANT: The user has invoked the "skill-creator" skill, indicating they want '
            "you to follow its instructions. The full skill content is loaded below.]\n\n"
            "# Skill Creator\n\n"
            "Large skill body that must not be searched or embedded.\n\n"
            "The user has provided the following instruction alongside the skill invocation: "
            "make a skill for release triage"
        )

        agent._sync_external_memory_for_turn(
            original_user_message=skill_message,
            final_response="Done.",
            interrupted=False,
        )

        agent._memory_manager.sync_all.assert_called_once_with(
            skill_message,
            "Done.",
            session_id="test_session_001",
        )
        agent._memory_manager.queue_prefetch_all.assert_called_once_with(
            skill_message,
            session_id="test_session_001",
        )

    # --- Edge cases (pre-existing behaviour preserved) ------------------

    def test_no_final_response_skips(self):
        """If the model produced no final_response (e.g. tool-only turn
        that never resolved), we must not fabricate an empty sync."""
        agent = _bare_agent()
        agent._sync_external_memory_for_turn(
            original_user_message="Hello",
            final_response=None,
            interrupted=False,
        )
        agent._memory_manager.sync_all.assert_not_called()

    def test_no_original_user_message_skips(self):
        """No user-origin message means this wasn't a user turn (e.g.
        a system-initiated refresh).  Don't sync an assistant-only
        exchange as if a user said something."""
        agent = _bare_agent()
        agent._sync_external_memory_for_turn(
            original_user_message=None,
            final_response="Proactive notification text",
            interrupted=False,
        )
        agent._memory_manager.sync_all.assert_not_called()

    def test_no_memory_manager_is_a_no_op(self):
        """Sessions without an external memory manager must not crash
        or try to call .sync_all on None."""
        from run_agent import AIAgent

        agent = AIAgent.__new__(AIAgent)
        agent._memory_manager = None

        # Must not raise.
        agent._sync_external_memory_for_turn(
            original_user_message="hi",
            final_response="hey",
            interrupted=False,
        )

    # --- Exception safety ----------------------------------------------

    def test_sync_exception_is_swallowed(self):
        """External memory providers are best-effort; a misconfigured
        or offline backend must not block the user from seeing their
        response by propagating the exception up."""
        agent = _bare_agent()
        agent._memory_manager.sync_all.side_effect = RuntimeError(
            "backend unreachable"
        )

        # Must not raise.
        agent._sync_external_memory_for_turn(
            original_user_message="hi",
            final_response="hey",
            interrupted=False,
        )
        # sync_all was attempted.
        agent._memory_manager.sync_all.assert_called_once()

    def test_prefetch_exception_is_swallowed(self):
        """Same best-effort contract applies to the prefetch step — a
        failure in queue_prefetch_all must not bubble out."""
        agent = _bare_agent()
        agent._memory_manager.queue_prefetch_all.side_effect = RuntimeError(
            "prefetch worker dead"
        )

        # Must not raise.
        agent._sync_external_memory_for_turn(
            original_user_message="hi",
            final_response="hey",
            interrupted=False,
        )
        # sync_all still happened before the prefetch blew up.
        agent._memory_manager.sync_all.assert_called_once()

    # --- Multimodal content flattening ----------------------------------

    def test_multimodal_user_message_is_flattened(self):
        """A turn with an attached image carries the user message as a
        list of typed parts.  Providers feed the content to regexes
        (sanitize_context), so a raw list raised ``expected string or
        bytes-like object, got 'list'`` and the turn silently never
        synced.  The boundary must flatten to text first."""
        agent = _bare_agent()
        agent._sync_external_memory_for_turn(
            original_user_message=[
                {"type": "text", "text": "what is in this screenshot?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
            final_response="A terminal window showing a stack trace.",
            interrupted=False,
        )
        agent._memory_manager.sync_all.assert_called_once_with(
            "[1 image] what is in this screenshot?",
            "A terminal window showing a stack trace.",
            session_id="test_session_001",
        )
        agent._memory_manager.queue_prefetch_all.assert_called_once_with(
            "[1 image] what is in this screenshot?",
            session_id="test_session_001",
        )

    def test_multimodal_response_is_flattened(self):
        agent = _bare_agent()
        agent._sync_external_memory_for_turn(
            original_user_message="describe it",
            final_response=[{"type": "text", "text": "a cat"}],
            interrupted=False,
        )
        agent._memory_manager.sync_all.assert_called_once_with(
            "describe it", "a cat",
            session_id="test_session_001",
        )

    def test_multimodal_with_no_text_at_all_skips(self):
        """Unknown-typed parts flatten to an empty string — don't sync a
        turn with no recoverable text."""
        agent = _bare_agent()
        agent._sync_external_memory_for_turn(
            original_user_message=[{"type": "audio", "data": "..."}],
            final_response="noted",
            interrupted=False,
        )
        agent._memory_manager.sync_all.assert_not_called()
        agent._memory_manager.queue_prefetch_all.assert_not_called()

    # --- The specific matrix the reporter asked about ------------------

    @pytest.mark.parametrize("interrupted,final,user,expect_sync", [
        (False, "resp", "user",  True),   # normal completed → sync
        (True,  "resp", "user",  False),  # interrupted → skip (the fix)
        (False, None,   "user",  False),  # no response → skip
        (False, "resp", None,    False),  # no user msg → skip
        (True,  None,   "user",  False),  # interrupted + no response → skip
        (True,  "resp", None,    False),  # interrupted + no user → skip
        (False, None,   None,    False),  # nothing → skip
        (True,  None,   None,    False),  # interrupted + nothing → skip
    ])
    def test_sync_matrix(self, interrupted, final, user, expect_sync):
        agent = _bare_agent()
        agent._sync_external_memory_for_turn(
            original_user_message=user,
            final_response=final,
            interrupted=interrupted,
        )
        if expect_sync:
            agent._memory_manager.sync_all.assert_called_once()
            agent._memory_manager.queue_prefetch_all.assert_called_once()
        else:
            agent._memory_manager.sync_all.assert_not_called()
            agent._memory_manager.queue_prefetch_all.assert_not_called()
