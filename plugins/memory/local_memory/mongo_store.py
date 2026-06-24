"""MongoDB persistence adapter plus in-memory store for tests."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .models import DurableMemoryRecord, IdentityScope, MemoryFeedbackRecord, ProviderEvent, RawTurnRecord, TombstoneRecord, content_hash, utc_now_iso


class MongoStore:
    def __init__(self, uri: str, database: str) -> None:
        self.uri = uri
        self.database = database
        self._client = None
        self._db = None

    def bootstrap(self) -> None:
        from pymongo import MongoClient  # type: ignore
        self._client = MongoClient(self.uri, serverSelectionTimeoutMS=1500)
        self._db = self._client[self.database]
        self._db.raw_turns.create_index("idempotency_key", unique=True)
        self._db.durable_memories.create_index([("scope.agent_identity", 1), ("scope.agent_workspace", 1), ("scope.user_id", 1), ("status", 1)])
        self._db.durable_memories.create_index([("scope.agent_identity", 1), ("scope.agent_workspace", 1), ("content_hash", 1)])

    @property
    def db(self):
        if self._db is None:
            self.bootstrap()
        return self._db

    def health(self) -> Dict[str, Any]:
        try:
            self.db.command("ping")
            return {"ok": True, "database": self.database}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def insert_raw_turn(self, raw: RawTurnRecord) -> str:
        data = raw.to_dict()
        result = self.db.raw_turns.update_one({"idempotency_key": raw.idempotency_key}, {"$setOnInsert": data}, upsert=True)
        existing = self.db.raw_turns.find_one({"idempotency_key": raw.idempotency_key})
        return str(existing.get("_id") or result.upserted_id or raw.idempotency_key)

    def upsert_memory(self, memory: DurableMemoryRecord) -> DurableMemoryRecord:
        self.db.durable_memories.update_one({"_id": memory.memory_id}, {"$set": memory.to_dict()}, upsert=True)
        return memory

    def get_memory(self, memory_id: str) -> Optional[DurableMemoryRecord]:
        data = self.db.durable_memories.find_one({"_id": memory_id})
        return DurableMemoryRecord.from_dict(data) if data else None

    def get_active_memories(self, ids: Iterable[str], scope: IdentityScope | None = None) -> List[DurableMemoryRecord]:
        query: Dict[str, Any] = {"_id": {"$in": list(ids)}, "status": "active"}
        if scope:
            query.update({"scope.agent_identity": scope.agent_identity, "scope.agent_workspace": scope.agent_workspace})
            if scope.user_id:
                query["scope.user_id"] = scope.user_id
        return [DurableMemoryRecord.from_dict(row) for row in self.db.durable_memories.find(query)]

    def find_duplicate(self, memory: DurableMemoryRecord) -> Optional[DurableMemoryRecord]:
        query = {"content_hash": memory.content_hash, "status": "active", "scope.agent_identity": memory.scope.agent_identity, "scope.agent_workspace": memory.scope.agent_workspace}
        if memory.scope.user_id:
            query["scope.user_id"] = memory.scope.user_id
        row = self.db.durable_memories.find_one(query)
        return DurableMemoryRecord.from_dict(row) if row else None

    def tombstone_memory(self, memory_id: str, reason: str = "forget_tool") -> bool:
        row = self.db.durable_memories.find_one({"_id": memory_id})
        result = self.db.durable_memories.update_one({"_id": memory_id}, {"$set": {"status": "tombstoned", "updated_at": utc_now_iso()}})
        scope = IdentityScope.from_kwargs("")
        if row and row.get("scope"):
            scope = DurableMemoryRecord.from_dict(row).scope
        tombstone = TombstoneRecord(memory_id=memory_id, reason=reason, scope=scope)
        self.db.tombstones.update_one({"memory_id": memory_id}, {"$set": tombstone.to_dict()}, upsert=True)
        return result.matched_count > 0

    def add_feedback(self, feedback: MemoryFeedbackRecord) -> str:
        result = self.db.memory_feedback.insert_one(feedback.to_dict())
        return str(result.inserted_id)

    def record_event(self, event_type: str, message: str, severity: str = "info", metadata: Dict[str, Any] | None = None, scope: IdentityScope | None = None) -> None:
        self.db.provider_events.insert_one(ProviderEvent(event_type=event_type, message=message, severity=severity, metadata=metadata or {}, scope=scope).to_dict())

    def prune_events(self, keep: int = 500) -> int:
        rows = list(self.db.provider_events.find({}, {"_id": 1}).sort("created_at", -1).skip(keep))
        if not rows:
            return 0
        result = self.db.provider_events.delete_many({"_id": {"$in": [row["_id"] for row in rows]}})
        return int(result.deleted_count)

    def recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        return list(self.db.provider_events.find({}, {"_id": 0}).sort("created_at", -1).limit(limit))


class InMemoryMongoStore:
    def __init__(self) -> None:
        self.raw_turns: Dict[str, Dict[str, Any]] = {}
        self.memories: Dict[str, DurableMemoryRecord] = {}
        self.feedback: List[MemoryFeedbackRecord] = []
        self.events: List[Dict[str, Any]] = []

    def bootstrap(self) -> None:
        return None

    def health(self) -> Dict[str, Any]:
        return {"ok": True, "raw_turns": len(self.raw_turns), "memories": len(self.memories)}

    def insert_raw_turn(self, raw: RawTurnRecord) -> str:
        key = raw.idempotency_key
        self.raw_turns.setdefault(key, raw.to_dict() | {"_id": key})
        return key

    def upsert_memory(self, memory: DurableMemoryRecord) -> DurableMemoryRecord:
        self.memories[memory.memory_id] = memory
        return memory

    def get_memory(self, memory_id: str) -> Optional[DurableMemoryRecord]:
        return self.memories.get(memory_id)

    def get_active_memories(self, ids: Iterable[str], scope: IdentityScope | None = None) -> List[DurableMemoryRecord]:
        out: List[DurableMemoryRecord] = []
        for memory_id in ids:
            memory = self.memories.get(memory_id)
            if not memory or memory.status != "active":
                continue
            if scope and (memory.scope.agent_identity != scope.agent_identity or memory.scope.agent_workspace != scope.agent_workspace):
                continue
            if scope and scope.user_id and memory.scope.user_id != scope.user_id:
                continue
            out.append(memory)
        return out

    def find_duplicate(self, memory: DurableMemoryRecord) -> Optional[DurableMemoryRecord]:
        for existing in self.memories.values():
            if existing.status == "active" and existing.content_hash == memory.content_hash and existing.scope.agent_identity == memory.scope.agent_identity and existing.scope.agent_workspace == memory.scope.agent_workspace:
                return existing
        return None

    def tombstone_memory(self, memory_id: str, reason: str = "forget_tool") -> bool:
        memory = self.memories.get(memory_id)
        if not memory:
            return False
        memory.status = "tombstoned"
        memory.updated_at = utc_now_iso()
        return True

    def add_feedback(self, feedback: MemoryFeedbackRecord) -> str:
        self.feedback.append(feedback)
        return f"feedback-{len(self.feedback)}"

    def record_event(self, event_type: str, message: str, severity: str = "info", metadata: Dict[str, Any] | None = None, scope: IdentityScope | None = None) -> None:
        self.events.append(ProviderEvent(event_type=event_type, message=message, severity=severity, metadata=metadata or {}, scope=scope).to_dict())

    def prune_events(self, keep: int = 500) -> int:
        if len(self.events) <= keep:
            return 0
        removed = len(self.events) - keep
        self.events = self.events[-keep:]
        return removed

    def recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        return list(reversed(self.events[-limit:]))
