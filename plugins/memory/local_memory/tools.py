"""Agent-facing local memory tool schemas and handlers."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .curator import build_memory, candidate_from_text, merge_memory
from .models import CurationCandidate, IdentityScope, MemoryFeedbackRecord

SEARCH_SCHEMA = {
    "name": "local_memory_search",
    "description": "Search local durable memories for relevant facts, preferences, project notes, and corrections.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}, "memory_type": {"type": "string"}, "include_superseded": {"type": "boolean"}}, "required": ["query"]},
}
REMEMBER_SCHEMA = {
    "name": "local_memory_remember",
    "description": "Store or merge a durable local memory.",
    "parameters": {"type": "object", "properties": {"content": {"type": "string"}, "memory_type": {"type": "string"}, "source": {"type": "string"}, "confidence": {"type": "number"}}, "required": ["content"]},
}
FORGET_SCHEMA = {
    "name": "local_memory_forget",
    "description": "Forget, tombstone, or supersede local durable memories by id or precise query.",
    "parameters": {"type": "object", "properties": {"memory_id": {"type": "string"}, "query": {"type": "string"}, "reason": {"type": "string"}, "require_exact_single_match": {"type": "boolean"}}, "oneOf": [{"required": ["memory_id"]}, {"required": ["query"]}]},
}
FEEDBACK_SCHEMA = {
    "name": "local_memory_feedback",
    "description": "Record feedback on a recalled memory.",
    "parameters": {"type": "object", "properties": {"memory_id": {"type": "string"}, "feedback_type": {"type": "string"}, "comment": {"type": "string"}, "corrected_content": {"type": "string"}}, "required": ["memory_id", "feedback_type"]},
}
ALL_TOOL_SCHEMAS = [SEARCH_SCHEMA, REMEMBER_SCHEMA, FORGET_SCHEMA, FEEDBACK_SCHEMA]


def json_result(**kwargs: Any) -> str:
    return json.dumps(kwargs, sort_keys=True)


class LocalMemoryToolHandler:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    @property
    def scope(self) -> IdentityScope:
        if self.provider.scope is None:
            raise RuntimeError("local_memory provider is not initialized")
        return self.provider.scope

    def search(self, args: Dict[str, Any]) -> str:
        query = str(args.get("query") or "").strip()
        limit = max(1, min(20, int(args.get("limit") or 5)))
        if not query:
            return json_result(success=False, results=[], message="query is required")
        results = self.provider._recall(query, limit=limit, include_context_wrapper=False)
        return json_result(success=True, results=results, message=f"Found {len(results)} memories")

    def remember(self, args: Dict[str, Any]) -> str:
        content = str(args.get("content") or "").strip()
        if not content:
            return json_result(success=False, memory_id="", operation="rejected", message="content is required")
        candidate = candidate_from_text(content, float(args.get("confidence", 0.9)))
        if not candidate:
            return json_result(success=False, memory_id="", operation="rejected", message="memory rejected as empty, low-value, or secret-like")
        candidate.memory_type = str(args.get("memory_type") or candidate.memory_type)
        memory = build_memory(candidate, self.scope)
        existing = self.provider.mongo_store.find_duplicate(memory)
        if existing:
            memory = merge_memory(existing, memory)
            operation = "merged"
        else:
            operation = "created"
        self.provider.mongo_store.upsert_memory(memory)
        embedding = self.provider._safe_embed(memory.content)
        if embedding:
            memory.embedding = {"model": self.provider.config.ollama_embedding_model, "dim": len(embedding)}
            self.provider.chroma_index.upsert_memory(memory, embedding)
        return json_result(success=True, memory_id=memory.memory_id, operation=operation, message=f"Memory {operation}")

    def forget(self, args: Dict[str, Any]) -> str:
        memory_id = str(args.get("memory_id") or "").strip()
        if not memory_id and args.get("query"):
            results = self.provider._recall(str(args["query"]), limit=2, include_context_wrapper=False)
            if len(results) == 1 or not args.get("require_exact_single_match", True):
                memory_id = results[0]["memory_id"] if results else ""
        if not memory_id:
            return json_result(success=False, affected=[], message="memory_id or exact single query match is required")
        ok = self.provider.mongo_store.tombstone_memory(memory_id, str(args.get("reason") or "forget_tool"))
        if ok:
            self.provider.chroma_index.delete_memory(memory_id)
        return json_result(success=ok, affected=[memory_id] if ok else [], message="Memory forgotten" if ok else "Memory not found")

    def feedback(self, args: Dict[str, Any]) -> str:
        memory_id = str(args.get("memory_id") or "").strip()
        feedback_type = str(args.get("feedback_type") or "").strip()
        if not memory_id or not feedback_type:
            return json_result(success=False, feedback_id="", message="memory_id and feedback_type are required")
        record = MemoryFeedbackRecord(memory_id=memory_id, feedback_type=feedback_type, scope=self.scope, comment=str(args.get("comment") or ""), corrected_content=str(args.get("corrected_content") or ""))
        feedback_id = self.provider.mongo_store.add_feedback(record)
        updated = False
        if feedback_type in {"wrong", "stale", "never_recall"}:
            updated = self.provider.mongo_store.tombstone_memory(memory_id, feedback_type)
            if updated:
                self.provider.chroma_index.delete_memory(memory_id)
        return json_result(success=True, feedback_id=feedback_id, memory_updated=updated, message="Feedback recorded")

    def handle(self, tool_name: str, args: Dict[str, Any]) -> str:
        dispatch = {
            "local_memory_search": self.search,
            "local_memory_remember": self.remember,
            "local_memory_forget": self.forget,
            "local_memory_feedback": self.feedback,
        }
        handler = dispatch.get(tool_name)
        if not handler:
            return json_result(success=False, message=f"Unknown local memory tool: {tool_name}")
        try:
            return handler(args or {})
        except Exception as exc:  # noqa: BLE001 - tool-safe error boundary
            return json_result(success=False, message=str(exc))
