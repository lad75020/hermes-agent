"""Redis ingestion queue adapter and in-memory queue."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .models import IngestionJob

QUEUE_KEY = "hermes:local-memory:queue"
DEAD_KEY = "hermes:local-memory:dead"
RETRY_KEY = "hermes:local-memory:retry"
LEASE_KEY = "hermes:local-memory:lease"
METRICS_KEY = "hermes:local-memory:metrics"


class RedisQueue:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import redis  # type: ignore
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def health(self) -> Dict[str, Any]:
        try:
            return {
                "ok": bool(self.client.ping()),
                "queue_depth": self.client.llen(QUEUE_KEY),
                "retry_depth": self.client.zcard(RETRY_KEY),
                "dead_depth": self.client.llen(DEAD_KEY),
                "leased_depth": self.client.hlen(LEASE_KEY),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def enqueue(self, job: IngestionJob) -> None:
        self.client.rpush(QUEUE_KEY, json.dumps(job.to_dict(), sort_keys=True))
        self.client.hincrby(METRICS_KEY, "enqueued", 1)

    def _release_due_retries(self) -> None:
        now = time.time()
        due = self.client.zrangebyscore(RETRY_KEY, 0, now, start=0, num=100)
        for raw in due:
            pipe = self.client.pipeline()
            pipe.zrem(RETRY_KEY, raw)
            pipe.rpush(QUEUE_KEY, raw)
            pipe.execute()

    def pop(self, timeout: float = 1.0) -> Optional[IngestionJob]:
        """Pop the next ingestion job.

        Redis BLPOP returns nil when its server-side timeout expires. Some
        clients/servers can instead raise a socket read timeout at the same
        boundary (for example when socket timeout and BLPOP timeout are both
        5s). An idle queue is expected for this worker, so treat read timeouts
        as no job available and let the outer loop poll again.
        """
        self._release_due_retries()
        try:
            result = self.client.blpop(QUEUE_KEY, timeout=max(1, int(timeout)))
        except TimeoutError:
            return None
        except Exception as exc:  # noqa: BLE001 - redis is optional at import time
            if exc.__class__.__name__ == "TimeoutError":
                try:
                    self.client.connection_pool.disconnect()
                except Exception:
                    pass
                return None
            raise
        if not result:
            return None
        _, raw = result
        job = IngestionJob.from_dict(json.loads(raw))
        self.client.hset(LEASE_KEY, job.job_id, raw)
        return job

    def ack(self, job: IngestionJob) -> None:
        self.client.hdel(LEASE_KEY, job.job_id)
        self.client.hincrby(METRICS_KEY, "acked", 1)

    def retry(self, job: IngestionJob, error: Exception) -> None:
        job.schedule_retry(error)
        score = datetime.fromisoformat(job.not_before).timestamp() if job.not_before else time.time()
        self.client.hdel(LEASE_KEY, job.job_id)
        self.client.zadd(RETRY_KEY, {json.dumps(job.to_dict(), sort_keys=True): score})
        self.client.hincrby(METRICS_KEY, "retried", 1)

    def dead_letter(self, job: IngestionJob, error: str) -> None:
        payload = job.to_dict() | {"last_error": {"code": "WorkerError", "message": error[:500], "at": datetime.now(timezone.utc).isoformat()}}
        self.client.hdel(LEASE_KEY, job.job_id)
        self.client.rpush(DEAD_KEY, json.dumps(payload, sort_keys=True))
        self.client.hincrby(METRICS_KEY, "dead", 1)

    def set_prefetch_cache(self, session_id: str, query_hash: str, value: str, ttl: int = 120) -> None:
        self.client.setex(f"hermes:local-memory:prefetch:{session_id}:{query_hash}", ttl, value)

    def get_prefetch_cache(self, session_id: str, query_hash: str) -> str:
        value = self.client.get(f"hermes:local-memory:prefetch:{session_id}:{query_hash}")
        return str(value or "")


class InMemoryRedisQueue:
    def __init__(self) -> None:
        self.jobs: list[IngestionJob] = []
        self.retry_jobs: list[IngestionJob] = []
        self.dead: list[tuple[IngestionJob, str]] = []
        self.leased: dict[str, IngestionJob] = {}
        self.cache: dict[str, str] = {}

    def health(self) -> Dict[str, Any]:
        return {"ok": True, "queue_depth": len(self.jobs), "retry_depth": len(self.retry_jobs), "dead_depth": len(self.dead), "leased_depth": len(self.leased)}

    def enqueue(self, job: IngestionJob) -> None:
        self.jobs.append(job)

    def pop(self, timeout: float = 0.0) -> Optional[IngestionJob]:
        if not self.jobs and self.retry_jobs:
            self.jobs.extend(self.retry_jobs)
            self.retry_jobs.clear()
        job = self.jobs.pop(0) if self.jobs else None
        if job is not None:
            self.leased[job.job_id] = job
        return job

    def ack(self, job: IngestionJob) -> None:
        self.leased.pop(job.job_id, None)

    def retry(self, job: IngestionJob, error: Exception) -> None:
        job.schedule_retry(error)
        self.leased.pop(job.job_id, None)
        self.retry_jobs.append(job)

    def dead_letter(self, job: IngestionJob, error: str) -> None:
        self.leased.pop(job.job_id, None)
        self.dead.append((job, error))

    def set_prefetch_cache(self, session_id: str, query_hash: str, value: str, ttl: int = 120) -> None:
        self.cache[f"{session_id}:{query_hash}"] = value

    def get_prefetch_cache(self, session_id: str, query_hash: str) -> str:
        return self.cache.get(f"{session_id}:{query_hash}", "")
