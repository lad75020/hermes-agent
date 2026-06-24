"""ChromaDB adapter plus a deterministic in-memory index for tests."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Sequence

from .config import LocalMemoryConfig
from .models import DurableMemoryRecord


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(float(a[i]) * float(b[i]) for i in range(size))
    norm_a = math.sqrt(sum(float(v) * float(v) for v in a[:size]))
    norm_b = math.sqrt(sum(float(v) * float(v) for v in b[:size]))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _chroma_where_filter(where: Dict[str, Any]) -> Dict[str, Any] | None:
    """Convert simple equality filters into Chroma's one-operator where form."""
    filters = [{key: {"$eq": value}} for key, value in (where or {}).items()]
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


class ChromaIndex:
    def __init__(self, config: LocalMemoryConfig) -> None:
        self.config = config
        self._client = None
        self._collection = None

    def bootstrap(self) -> None:
        import chromadb  # type: ignore
        Path(self.config.chroma_path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self.config.chroma_path)
        self._collection = self._client.get_or_create_collection(self.config.chroma_collection)

    def health(self) -> Dict[str, Any]:
        try:
            if self._collection is None:
                self.bootstrap()
            return {"ok": True, "path": self.config.chroma_path, "collection": self.config.chroma_collection, "count": self._collection.count()}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def upsert_memory(self, memory: DurableMemoryRecord, embedding: List[float]) -> None:
        if self._collection is None:
            self.bootstrap()
        metadata = memory.scope.chroma_where() | {
            "memory_id": memory.memory_id,
            "status": memory.status,
            "memory_type": memory.memory_type,
            "content_hash": memory.content_hash,
            "embedding_model": str(memory.embedding.get("model", self.config.ollama_embedding_model)),
            "embedding_dim": len(embedding),
            "updated_at": memory.updated_at,
        }
        self._collection.upsert(ids=[memory.memory_id], embeddings=[embedding], documents=[memory.content], metadatas=[metadata])

    def delete_memory(self, memory_id: str) -> None:
        if self._collection is None:
            self.bootstrap()
        self._collection.delete(ids=[memory_id])

    def find_memory_documents_by_keywords(self, keywords: Sequence[str], *, where: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        if self._collection is None:
            self.bootstrap()
        cleaned = [str(keyword).strip().lower() for keyword in keywords if str(keyword).strip()]
        if not cleaned:
            return []
        result = self._collection.get(where=_chroma_where_filter(where), include=["documents", "metadatas"])
        ids = result.get("ids") or []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        rows: List[Dict[str, Any]] = []
        for index, item_id in enumerate(ids):
            document = str(documents[index] if index < len(documents) else "")
            haystack = document.lower()
            if not any(keyword in haystack for keyword in cleaned):
                continue
            metadata = metadatas[index] if index < len(metadatas) else {}
            rows.append({"memory_id": str((metadata or {}).get("memory_id") or item_id), "document": document, "metadata": metadata or {}})
            if len(rows) >= max(1, int(limit)):
                break
        return rows

    def search(self, embedding: List[float], *, where: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        if self._collection is None:
            self.bootstrap()
        result = self._collection.query(query_embeddings=[embedding], n_results=limit, where=_chroma_where_filter(where))
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        return [{"memory_id": mid, "score": 1.0 - float(distances[i] if i < len(distances) else 0.0), "metadata": metadatas[i] if i < len(metadatas) else {}} for i, mid in enumerate(ids)]


class InMemoryChromaIndex:
    def __init__(self) -> None:
        self.vectors: Dict[str, List[float]] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self.documents: Dict[str, str] = {}

    def bootstrap(self) -> None:  # pragma: no cover - intentional no-op
        return None

    def health(self) -> Dict[str, Any]:
        return {"ok": True, "count": len(self.vectors)}

    def upsert_memory(self, memory: DurableMemoryRecord, embedding: List[float]) -> None:
        self.vectors[memory.memory_id] = list(embedding)
        self.documents[memory.memory_id] = memory.content
        self.metadata[memory.memory_id] = memory.scope.chroma_where() | {"status": memory.status, "memory_type": memory.memory_type, "memory_id": memory.memory_id, "content_hash": memory.content_hash}

    def delete_memory(self, memory_id: str) -> None:
        self.vectors.pop(memory_id, None)
        self.metadata.pop(memory_id, None)
        self.documents.pop(memory_id, None)

    def find_memory_documents_by_keywords(self, keywords: Sequence[str], *, where: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        cleaned = [str(keyword).strip().lower() for keyword in keywords if str(keyword).strip()]
        if not cleaned:
            return []
        rows: List[Dict[str, Any]] = []
        for memory_id, document in self.documents.items():
            meta = self.metadata.get(memory_id, {})
            if any(meta.get(k) != v for k, v in (where or {}).items()):
                continue
            haystack = document.lower()
            if not any(keyword in haystack for keyword in cleaned):
                continue
            rows.append({"memory_id": memory_id, "document": document, "metadata": meta})
            if len(rows) >= max(1, int(limit)):
                break
        return rows

    def search(self, embedding: List[float], *, where: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        rows = []
        for memory_id, vector in self.vectors.items():
            meta = self.metadata.get(memory_id, {})
            if any(meta.get(k) != v for k, v in (where or {}).items()):
                continue
            rows.append({"memory_id": memory_id, "score": cosine_similarity(embedding, vector), "metadata": meta})
        return sorted(rows, key=lambda item: item["score"], reverse=True)[:limit]
