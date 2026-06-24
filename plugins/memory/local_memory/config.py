"""Configuration handling for the local memory provider."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any, Dict


@dataclass
class LocalMemoryConfig:
    enabled: bool = True
    mongo_uri: str = "mongodb://localhost:27017/hermes-local-memory"
    mongo_database: str = "hermes-local-memory"
    redis_url: str = "redis://localhost:6379"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_curator_model: str = "qwen2.5:7b"
    chroma_path: str = "/Volumes/WDBlack4TB/.hermes/hermes-local-memory/chroma"
    chroma_collection: str = "hermes_local_memory"
    max_prefetch_results: int = 8
    max_prefetch_chars: int = 3000
    min_relevance: float = 0.25
    sync_enqueue_timeout_ms: int = 100
    worker_poll_timeout_sec: float = 5.0
    worker_max_attempts: int = 5
    write_non_primary_contexts: bool = False
    raw_turn_retention_days: int = 365
    curator_prompt_version: str = "local-memory-curator-v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower().strip()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce(raw: Dict[str, Any]) -> LocalMemoryConfig:
    defaults = LocalMemoryConfig()
    data = defaults.to_dict()
    data.update({k: v for k, v in raw.items() if k in data and v is not None})
    data["enabled"] = _as_bool(data.get("enabled"), True)
    data["write_non_primary_contexts"] = _as_bool(data.get("write_non_primary_contexts"), False)
    for key in ("max_prefetch_results", "max_prefetch_chars", "sync_enqueue_timeout_ms", "worker_max_attempts", "raw_turn_retention_days"):
        data[key] = int(data[key])
    for key in ("min_relevance", "worker_poll_timeout_sec"):
        data[key] = float(data[key])
    data["max_prefetch_results"] = max(1, min(20, data["max_prefetch_results"]))
    data["max_prefetch_chars"] = max(500, min(8000, data["max_prefetch_chars"]))
    data["min_relevance"] = max(0.0, min(1.0, data["min_relevance"]))
    return LocalMemoryConfig(**data)


def config_path_for(hermes_home: str) -> Path:
    return Path(hermes_home).expanduser() / "local_memory.json"


def load_config(hermes_home: str) -> LocalMemoryConfig:
    raw: Dict[str, Any] = {}
    path = config_path_for(hermes_home)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw.update(loaded)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid local memory config JSON at {path}: {exc}") from exc

    env_map = {
        "mongo_uri": "HERMES_LOCAL_MEMORY_MONGO_URI",
        "mongo_database": "HERMES_LOCAL_MEMORY_MONGO_DATABASE",
        "redis_url": "HERMES_LOCAL_MEMORY_REDIS_URL",
        "ollama_base_url": "HERMES_LOCAL_MEMORY_OLLAMA_BASE_URL",
        "ollama_embedding_model": "HERMES_LOCAL_MEMORY_EMBEDDING_MODEL",
        "ollama_curator_model": "HERMES_LOCAL_MEMORY_CURATOR_MODEL",
        "chroma_path": "HERMES_LOCAL_MEMORY_CHROMA_PATH",
        "chroma_collection": "HERMES_LOCAL_MEMORY_CHROMA_COLLECTION",
    }
    for key, env_name in env_map.items():
        if os.getenv(env_name):
            raw[key] = os.environ[env_name]
    return _coerce(raw)


def save_config(values: Dict[str, Any], hermes_home: str) -> None:
    path = config_path_for(hermes_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    current: Dict[str, Any] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    current.update({k: v for k, v in values.items() if k in LocalMemoryConfig().__dict__})
    config = _coerce(current).to_dict()
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
