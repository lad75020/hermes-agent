"""Diagnostics helpers for local memory provider operations."""
from __future__ import annotations

import sys
from typing import Any, Dict

from .config import LocalMemoryConfig
from .models import IdentityScope


def collect_diagnostics(config: LocalMemoryConfig, scope: IdentityScope | None, *, mongo_store: Any, redis_queue: Any, chroma_index: Any, ollama_client: Any) -> Dict[str, Any]:
    """Collect secret-safe status for all provider dependencies."""
    return {
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "scope": scope.to_dict() if scope else {},
        "config": {
            "mongo_database": config.mongo_database,
            "redis_url": config.redis_url.split("@")[-1],
            "ollama_base_url": config.ollama_base_url,
            "chroma_path": config.chroma_path,
            "chroma_collection": config.chroma_collection,
        },
        "mongo": mongo_store.health() if mongo_store else {"ok": False, "error": "not initialized"},
        "redis": redis_queue.health() if redis_queue else {"ok": False, "error": "not initialized"},
        "chroma": chroma_index.health() if chroma_index else {"ok": False, "error": "not initialized"},
        "ollama": ollama_client.health() if ollama_client else {"ok": False, "error": "not initialized"},
        "recent_events": mongo_store.recent_events(5) if mongo_store else [],
    }
