# Hermes Local Memory Provider

`local_memory` is a Hermes `MemoryProvider` plugin for local persistent memory.

## Runtime

- Python: `/Volumes/WDBlack4TB/.hermes/hermes-agent/venv/bin/python3` (Python 3.11)
- Ollama: `http://localhost:11434`
- Redis: `redis://localhost:6379`
- MongoDB: `mongodb://localhost:27017/hermes-local-memory`
- ChromaDB: `/Volumes/WDBlack4TB/.hermes/hermes-local-memory/chroma`

## Configuration

Copy `local_memory.example.json` to `$HERMES_HOME/local_memory.json` and adjust values. Keep credentials out of JSON config; use `.env` variables for secrets.

Activate in Hermes:

```sh
hermes config set memory.provider local_memory
```

## Worker

```sh
/Volumes/WDBlack4TB/.hermes/hermes-agent/venv/bin/python3 -m plugins.memory.local_memory.worker --hermes-home /Volumes/WDBlack4TB/.hermes
```

The provider `sync_turn()` path only enqueues Redis jobs. The worker stores raw turns in MongoDB, curates durable memories with Ollama, embeds memory text, and upserts Chroma vectors.

## Profile isolation

Every record carries `hermes_home`, `agent_identity`, `agent_workspace`, `platform`, `session_id`, `agent_context`, and optional user identifiers. Reads filter by active scope. Writes from `subagent`, `cron`, and `flush` contexts are skipped unless `write_non_primary_contexts` is explicitly enabled.

## Diagnostics

```sh
/Volumes/WDBlack4TB/.hermes/hermes-agent/venv/bin/python3 -m plugins.memory.local_memory.cli status --hermes-home /Volumes/WDBlack4TB/.hermes
```

Diagnostics report service health, queue depth, Chroma collection status, Ollama reachability, Python executable, and recent provider events without printing secrets.

## Recovery

- Redis down: turns complete but enqueue failures are recorded as provider events.
- Ollama down: recall falls back to deterministic degraded embeddings for local tests; worker retries or dead-letters failed curation/index work.
- MongoDB down: provider starts degraded and records failures when possible.
- Chroma drift: delete/reindex vectors from MongoDB active `durable_memories` records.

## SQLite compatibility

ChromaDB requires SQLite >= 3.35. If `import chromadb` fails with an unsupported SQLite error in the Hermes venv, use a Python build linked against newer SQLite or install a compatible `pysqlite3` package for the platform before running full integration tests.
