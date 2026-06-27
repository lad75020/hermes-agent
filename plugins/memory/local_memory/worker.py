"""Redis-backed ingestion worker for the local memory provider."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from .chroma_index import ChromaIndex
from .config import LocalMemoryConfig, _coerce, load_config
from .curator import build_memory, fallback_extract_candidates, merge_memory, parse_ollama_curation
from .models import IngestionJob, RawTurnRecord, TurnChunkRecord
from .mongo_store import MongoStore
from .ollama_client import OllamaClient
from .redis_queue import RedisQueue


class LocalMemoryWorker:
    def __init__(self, *, config: LocalMemoryConfig, mongo_store: Any, redis_queue: Any, chroma_index: Any, ollama_client: Any) -> None:
        self.config = config
        self.mongo_store = mongo_store
        self.redis_queue = redis_queue
        self.chroma_index = chroma_index
        self.ollama_client = ollama_client

    def _split_text(self, text: str) -> List[str]:
        normalized = "\n".join(line.rstrip() for line in (text or "").splitlines()).strip()
        if not normalized:
            return []
        size = max(1, int(self.config.turn_chunk_chars))
        overlap = max(0, min(size // 2, int(self.config.turn_chunk_overlap_chars)))
        chunks: List[str] = []
        start = 0
        while start < len(normalized) and len(chunks) < int(self.config.max_turn_chunks):
            end = min(len(normalized), start + size)
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(normalized):
                break
            start = max(end - overlap, start + 1)
        return chunks

    def _build_turn_chunks(self, raw: RawTurnRecord, raw_turn_id: str) -> List[TurnChunkRecord]:
        built: List[TurnChunkRecord] = []
        for role, text in (("user", raw.user_content), ("assistant", raw.assistant_content)):
            parts = self._split_text(text)
            for index, content in enumerate(parts):
                built.append(
                    TurnChunkRecord(
                        raw_turn_id=raw_turn_id,
                        idempotency_key=raw.idempotency_key,
                        scope=raw.scope,
                        role=role,
                        content=content,
                        chunk_index=index,
                        total_chunks=len(parts),
                    )
                )
        return built

    def _index_turn_chunks(self, raw: RawTurnRecord, raw_turn_id: str) -> List[str]:
        chunks = self._build_turn_chunks(raw, raw_turn_id)
        if not chunks:
            return []
        self.mongo_store.upsert_turn_chunks(chunks)
        written: List[str] = []
        for chunk in chunks:
            embedding = self.ollama_client.embed(chunk.content)
            self.chroma_index.upsert_turn_chunk(chunk, embedding)
            written.append(chunk.chunk_id)
        return written

    def process_one(self) -> bool:
        job = self.redis_queue.pop(timeout=self.config.worker_poll_timeout_sec)
        if job is None:
            return False
        try:
            self.process_job(job)
            if hasattr(self.redis_queue, "ack"):
                self.redis_queue.ack(job)
            return True
        except Exception as exc:  # noqa: BLE001
            if job.attempt + 1 >= job.max_attempts:
                self.redis_queue.dead_letter(job, str(exc))
            elif hasattr(self.redis_queue, "retry"):
                self.redis_queue.retry(job, exc)
            else:
                job.schedule_retry(exc)
                self.redis_queue.enqueue(job)
            self.mongo_store.record_event("worker_failure", str(exc), "error", {"job_id": job.job_id, "attempt": job.attempt}, job.scope)
            return False

    def process_job(self, job: IngestionJob) -> List[str]:
        payload = job.payload
        raw = RawTurnRecord(
            idempotency_key=job.idempotency_key,
            scope=job.scope,
            user_content=str(payload.get("user_content") or ""),
            assistant_content=str(payload.get("assistant_content") or ""),
            messages=list(payload.get("messages") or []),
            content_hash=str(payload.get("content_hash") or ""),
        )
        raw_turn_id = str(payload.get("raw_turn_id") or "") or self.mongo_store.insert_raw_turn(raw)
        written_chunks = self._index_turn_chunks(raw, raw_turn_id)
        candidates = []
        try:
            curated_raw = self.ollama_client.curate(raw.user_content, raw.assistant_content, [])
            candidates = parse_ollama_curation(curated_raw)
        except Exception as exc:  # noqa: BLE001 - fallback is deliberate
            self.mongo_store.record_event("curation_fallback", str(exc), "warning", {"job_id": job.job_id}, job.scope)
        if not candidates:
            candidates = fallback_extract_candidates(raw.user_content, raw.assistant_content)

        written: List[str] = []
        for candidate in candidates:
            memory = build_memory(candidate, job.scope, source_turn_id=raw_turn_id)
            existing = self.mongo_store.find_duplicate(memory)
            if existing:
                memory = merge_memory(existing, memory)
            self.mongo_store.upsert_memory(memory)
            embedding = self.ollama_client.embed(memory.content)
            memory.embedding = {"model": self.config.ollama_embedding_model, "dim": len(embedding)}
            self.mongo_store.upsert_memory(memory)
            self.chroma_index.upsert_memory(memory, embedding)
            written.append(memory.memory_id)
        self.mongo_store.record_event("job_processed", f"Processed {job.job_id}", "info", {"memories": written, "turn_chunks": written_chunks}, job.scope)
        return written


def _load_config_file(path: str) -> LocalMemoryConfig:
    with open(path, "r", encoding="utf-8") as fh:
        return _coerce(json.load(fh))


def build_worker(hermes_home: str, config_path: str = "") -> LocalMemoryWorker:
    config = _load_config_file(config_path) if config_path else load_config(hermes_home)
    mongo = MongoStore(config.mongo_uri, config.mongo_database)
    redis = RedisQueue(config.redis_url)
    chroma = ChromaIndex(config)
    ollama = OllamaClient(config)
    return LocalMemoryWorker(config=config, mongo_store=mongo, redis_queue=redis, chroma_index=chroma, ollama_client=ollama)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Hermes local memory ingestion worker")
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    parser.add_argument("--config", default="", help="Optional explicit local_memory.json path")
    parser.add_argument("--poll-timeout", type=float, default=None, help="Override queue poll timeout in seconds")
    parser.add_argument("--once", action="store_true", help="Process at most one job")
    parser.add_argument("--max-jobs", type=int, default=0, help="Process at most N jobs, 0 means forever")
    args = parser.parse_args(argv)
    worker = build_worker(args.hermes_home, args.config)
    if args.poll_timeout is not None:
        worker.config.worker_poll_timeout_sec = max(0.1, args.poll_timeout)
    processed = 0
    while True:
        did_work = worker.process_one()
        processed += int(did_work)
        if args.once or (args.max_jobs and processed >= args.max_jobs):
            break
    print(json.dumps({"processed": processed}, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
