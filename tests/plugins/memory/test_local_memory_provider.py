from __future__ import annotations

from types import SimpleNamespace

from plugins.memory.local_memory import LocalMemoryProvider
from plugins.memory.local_memory.chroma_index import InMemoryChromaIndex
from plugins.memory.local_memory.config import LocalMemoryConfig
from plugins.memory.local_memory.mongo_store import InMemoryMongoStore
from plugins.memory.local_memory.redis_queue import InMemoryRedisQueue
from plugins.memory.local_memory.worker import LocalMemoryWorker


def _provider() -> LocalMemoryProvider:
    provider = LocalMemoryProvider(
        config=LocalMemoryConfig(enabled=True),
        mongo_store=InMemoryMongoStore(),
        redis_queue=InMemoryRedisQueue(),
        chroma_index=InMemoryChromaIndex(),
        ollama_client=SimpleNamespace(embed=lambda text: [float(len(text) % 7), 1.0]),
    )
    provider.initialize(
        "session-1",
        hermes_home="/tmp/hermes-test",
        platform="tui",
        agent_identity="default",
        agent_workspace="workspace",
    )
    return provider


def _worker_provider() -> LocalMemoryProvider:
    provider = LocalMemoryProvider(
        config=LocalMemoryConfig(enabled=True, min_relevance=0.0, max_prefetch_chars=8000),
        mongo_store=InMemoryMongoStore(),
        redis_queue=InMemoryRedisQueue(),
        chroma_index=InMemoryChromaIndex(),
        ollama_client=SimpleNamespace(
            embed=lambda text: [1.0, 0.0],
            curate=lambda user, assistant, existing: '{"candidates": []}',
        ),
    )
    provider.initialize(
        "session-1",
        hermes_home="/tmp/hermes-test",
        platform="tui",
        agent_identity="default",
        agent_workspace="workspace",
    )
    return provider


def test_on_memory_write_add_mirrors_builtin_memory_save_to_mongo_and_chroma():
    provider = _provider()

    provider.on_memory_write(
        "add",
        "user",
        "Laurent prefers concise autonomous progress",
        metadata={"session_id": "session-1", "tool_name": "memory"},
    )

    memories = list(provider.mongo_store.memories.values())
    assert len(memories) == 1
    memory = memories[0]
    assert memory.content == "Laurent prefers concise autonomous progress"
    assert memory.memory_type == "preference"
    assert memory.source_session_ids == ["session-1"]
    assert memory.memory_id in provider.chroma_index.documents
    assert provider.chroma_index.documents[memory.memory_id] == memory.content


def test_on_memory_write_remove_tombstones_mongo_and_deletes_chroma_vector():
    provider = _provider()
    provider.on_memory_write("add", "memory", "Project uses pytest for verification")
    memory_id = next(iter(provider.mongo_store.memories))
    assert memory_id in provider.chroma_index.documents

    provider.on_memory_write(
        "remove",
        "memory",
        "",
        metadata={"old_text": "Project uses pytest for verification"},
    )

    assert provider.mongo_store.memories[memory_id].status == "tombstoned"
    assert memory_id not in provider.chroma_index.documents


def test_on_memory_write_replace_removes_old_text_and_adds_new_text():
    provider = _provider()
    provider.on_memory_write("add", "memory", "Old local memory preference")
    old_id = next(iter(provider.mongo_store.memories))

    provider.on_memory_write(
        "replace",
        "memory",
        "New local memory preference",
        metadata={"old_text": "Old local memory preference"},
    )

    active = [m for m in provider.mongo_store.memories.values() if m.status == "active"]
    assert len(active) == 1
    assert active[0].content == "New local memory preference"
    assert provider.mongo_store.memories[old_id].status == "tombstoned"
    assert old_id not in provider.chroma_index.documents


def test_local_memory_status_separates_actual_queue_depth_from_cumulative_metrics():
    provider = _provider()
    provider.sync_turn("user", "assistant", session_id="session-1")
    assert len(provider.mongo_store.raw_turns) == 1
    job = provider.redis_queue.pop()
    assert job is not None
    provider.redis_queue.ack(job)

    health = provider.redis_queue.health()

    assert health["queue_key"] == "hermes:local-memory:queue"
    assert health["metrics_key"] == "hermes:local-memory:metrics"
    assert health["queue_depth"] == 0
    assert health["cumulative_metrics"] == {"enqueued": 1, "acked": 1}


def test_sync_turn_records_raw_turn_before_worker_runs():
    provider = _provider()

    provider.sync_turn(
        "User asks from HermesMacOS",
        "Assistant replies through TUI gateway",
        session_id="tui-session",
        messages=[
            {"role": "user", "content": "User asks from HermesMacOS"},
            {"role": "assistant", "content": "Assistant replies through TUI gateway"},
        ],
    )

    assert len(provider.mongo_store.raw_turns) == 1
    raw = next(iter(provider.mongo_store.raw_turns.values()))
    assert raw["user_content"] == "User asks from HermesMacOS"
    assert raw["assistant_content"] == "Assistant replies through TUI gateway"
    assert raw["scope"]["platform"] == "tui"
    assert raw["messages"][-1]["content"] == "Assistant replies through TUI gateway"
    job = provider.redis_queue.pop()
    assert job is not None
    assert job.payload["raw_turn_id"]


def test_worker_indexes_larger_turn_chunks_to_mongo_and_chroma():
    provider = _worker_provider()
    assistant = (
        "First sentence only would be insufficient. "
        + "The later details include RETRIEVABLE_SECOND_SENTENCE_CONTEXT and implementation caveats. "
        + "More assistant explanation follows so the indexed context is a real chunk rather than a tiny summary. " * 8
    )
    provider.sync_turn("Please explain the storage issue", assistant, session_id="session-1")
    job = provider.redis_queue.pop()
    assert job is not None

    worker = LocalMemoryWorker(
        config=provider.config,
        mongo_store=provider.mongo_store,
        redis_queue=provider.redis_queue,
        chroma_index=provider.chroma_index,
        ollama_client=provider.ollama_client,
    )
    worker.process_job(job)

    chunks = list(provider.mongo_store.turn_chunks.values())
    assert chunks
    assistant_chunks = [chunk for chunk in chunks if chunk.role == "assistant"]
    assert assistant_chunks
    assert any("RETRIEVABLE_SECOND_SENTENCE_CONTEXT" in chunk.content for chunk in assistant_chunks)
    assert any(provider.chroma_index.documents.get(chunk.chunk_id) == chunk.content for chunk in assistant_chunks)

    recalled = provider._recall("RETRIEVABLE_SECOND_SENTENCE_CONTEXT", limit=5, include_context_wrapper=False)
    assert any(row.get("record_type") == "turn_chunk" and "RETRIEVABLE_SECOND_SENTENCE_CONTEXT" in row.get("content", "") for row in recalled)


def test_prefetch_context_includes_turn_chunk_text_not_only_curated_memory():
    provider = _worker_provider()
    assistant = (
        "Short opener. "
        + "A later section says UNIQUE_PREFETCH_CHUNK_MARKER belongs in recalled context with surrounding explanation. "
        + "Additional details keep this as conversation context instead of a one-sentence durable memory. " * 7
    )
    provider.sync_turn("What happened?", assistant, session_id="session-1")
    job = provider.redis_queue.pop()
    assert job is not None
    worker = LocalMemoryWorker(
        config=provider.config,
        mongo_store=provider.mongo_store,
        redis_queue=provider.redis_queue,
        chroma_index=provider.chroma_index,
        ollama_client=provider.ollama_client,
    )
    worker.process_job(job)

    context = provider.prefetch("UNIQUE_PREFETCH_CHUNK_MARKER", session_id="session-1")

    assert "conversation chunks" in context
    assert "UNIQUE_PREFETCH_CHUNK_MARKER" in context
