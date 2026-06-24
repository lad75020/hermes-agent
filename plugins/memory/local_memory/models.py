"""Typed data structures for the Hermes local memory provider."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp in ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat()


def normalize_content(content: str) -> str:
    """Normalize memory content for hashing and duplicate detection."""
    return re.sub(r"\s+", " ", (content or "").strip().lower())


def content_hash(content: str) -> str:
    """Return a stable SHA-256 hash for normalized content."""
    return sha256(normalize_content(content).encode("utf-8")).hexdigest()


_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^\s'\"]{12,}"),
    re.compile(r"\b(?:sk|pk|ghp|gho|xox[baprs])-?[A-Za-z0-9_\-]{20,}\b"),
]


def looks_like_secret(content: str) -> bool:
    """Return True when content resembles credentials that must not be memorized."""
    return any(pattern.search(content or "") for pattern in _SECRET_PATTERNS)


@dataclass(frozen=True)
class IdentityScope:
    """Identity boundary for all memory reads and writes."""

    hermes_home: str
    agent_identity: str = "default"
    agent_workspace: str = "hermes"
    platform: str = "cli"
    session_id: str = ""
    agent_context: str = "primary"
    user_id: str = ""
    user_id_alt: str = ""
    parent_session_id: str = ""

    @classmethod
    def from_kwargs(cls, session_id: str, **kwargs: Any) -> "IdentityScope":
        """Build a scope from MemoryProvider.initialize keyword arguments."""
        return cls(
            hermes_home=str(kwargs.get("hermes_home") or ""),
            agent_identity=str(kwargs.get("agent_identity") or "default"),
            agent_workspace=str(kwargs.get("agent_workspace") or "hermes"),
            platform=str(kwargs.get("platform") or "cli"),
            session_id=str(session_id or kwargs.get("session_id") or ""),
            agent_context=str(kwargs.get("agent_context") or "primary"),
            user_id=str(kwargs.get("user_id") or ""),
            user_id_alt=str(kwargs.get("user_id_alt") or ""),
            parent_session_id=str(kwargs.get("parent_session_id") or ""),
        )

    def to_dict(self) -> Dict[str, str]:
        """Serialize to a plain dict with scalar values for Mongo/Chroma metadata."""
        return asdict(self)

    def chroma_where(self) -> Dict[str, str]:
        """Return scalar scope filters suitable for Chroma metadata queries."""
        where = {
            "agent_identity": self.agent_identity,
            "agent_workspace": self.agent_workspace,
        }
        if self.user_id:
            where["user_id"] = self.user_id
        return where

    def allows_write(self, write_non_primary_contexts: bool = False) -> bool:
        """Return whether this scope may write durable memories by default."""
        return write_non_primary_contexts or self.agent_context == "primary"


@dataclass
class RawTurnRecord:
    idempotency_key: str
    scope: IdentityScope
    user_content: str
    assistant_content: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    content_hash: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    curation_status: str = "queued"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["scope"] = self.scope.to_dict()
        if not data["content_hash"]:
            data["content_hash"] = content_hash(self.user_content + "\n" + self.assistant_content)
        return data


@dataclass
class DurableMemoryRecord:
    content: str
    scope: IdentityScope
    memory_type: str = "fact"
    memory_id: str = ""
    source_turn_ids: List[str] = field(default_factory=list)
    source_session_ids: List[str] = field(default_factory=list)
    confidence: float = 0.8
    sensitivity: str = "normal"
    status: str = "active"
    revision: int = 1
    supersedes: str = ""
    superseded_by: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    embedding: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.memory_id:
            self.memory_id = content_hash(self.content)[:24]

    @property
    def normalized_content(self) -> str:
        return normalize_content(self.content)

    @property
    def content_hash(self) -> str:
        return content_hash(self.content)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["_id"] = self.memory_id
        data["scope"] = self.scope.to_dict()
        data["normalized_content"] = self.normalized_content
        data["content_hash"] = self.content_hash
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DurableMemoryRecord":
        scope_data = data.get("scope") or {}
        scope = scope_data if isinstance(scope_data, IdentityScope) else IdentityScope(**{k: str(v) for k, v in scope_data.items() if k in IdentityScope.__dataclass_fields__})
        return cls(
            memory_id=str(data.get("memory_id") or data.get("_id") or ""),
            content=str(data.get("content") or ""),
            scope=scope,
            memory_type=str(data.get("memory_type") or "fact"),
            source_turn_ids=list(data.get("source_turn_ids") or []),
            source_session_ids=list(data.get("source_session_ids") or []),
            confidence=float(data.get("confidence", 0.8)),
            sensitivity=str(data.get("sensitivity") or "normal"),
            status=str(data.get("status") or "active"),
            revision=int(data.get("revision", 1)),
            supersedes=str(data.get("supersedes") or ""),
            superseded_by=str(data.get("superseded_by") or ""),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            embedding=dict(data.get("embedding") or {}),
        )


@dataclass
class IngestionJob:
    job_id: str
    idempotency_key: str
    job_type: str
    scope: IdentityScope
    payload: Dict[str, Any]
    schema_version: str = "1.0"
    created_at: str = field(default_factory=utc_now_iso)
    not_before: str = ""
    attempt: int = 0
    max_attempts: int = 5
    last_error: Dict[str, str] = field(default_factory=dict)

    def schedule_retry(self, error: Exception, *, base_delay_seconds: float = 1.0) -> None:
        """Advance retry state with exponential backoff metadata."""
        self.attempt += 1
        delay = min(300.0, max(0.1, base_delay_seconds) * (2 ** max(0, self.attempt - 1)))
        self.not_before = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        self.last_error = {"code": error.__class__.__name__, "message": str(error)[:500], "at": utc_now_iso()}

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["scope"] = self.scope.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IngestionJob":
        scope_raw = data.get("scope") or {}
        scope = scope_raw if isinstance(scope_raw, IdentityScope) else IdentityScope(**{k: str(v) for k, v in scope_raw.items() if k in IdentityScope.__dataclass_fields__})
        return cls(
            job_id=str(data["job_id"]),
            idempotency_key=str(data["idempotency_key"]),
            job_type=str(data.get("job_type") or "turn_ingest"),
            scope=scope,
            payload=dict(data.get("payload") or {}),
            schema_version=str(data.get("schema_version") or "1.0"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            not_before=str(data.get("not_before") or ""),
            attempt=int(data.get("attempt", 0)),
            max_attempts=int(data.get("max_attempts", 5)),
            last_error=dict(data.get("last_error") or {}),
        )


@dataclass
class CurationCandidate:
    content: str
    memory_type: str = "fact"
    confidence: float = 0.8
    sensitivity: str = "normal"


@dataclass
class CurationResult:
    """Structured output from the Ollama curation step."""

    candidates: List[CurationCandidate] = field(default_factory=list)
    raw_response: str = ""
    prompt_version: str = "local-memory-curator-v1"
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidates": [asdict(candidate) for candidate in self.candidates],
            "raw_response": self.raw_response[:4000],
            "prompt_version": self.prompt_version,
            "created_at": self.created_at,
        }


@dataclass
class TombstoneRecord:
    """Audit record for a forgotten or superseded memory."""

    memory_id: str
    reason: str
    scope: IdentityScope
    superseded_by: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["scope"] = self.scope.to_dict()
        return data


@dataclass
class ProviderEvent:
    """Secret-safe provider event for diagnostics and operations."""

    event_type: str
    message: str
    severity: str = "info"
    metadata: Dict[str, Any] = field(default_factory=dict)
    scope: Optional[IdentityScope] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "message": self.message[:1000],
            "severity": self.severity,
            "metadata": self.metadata,
            "scope": self.scope.to_dict() if self.scope else {},
            "created_at": self.created_at,
        }


@dataclass
class MemoryFeedbackRecord:
    memory_id: str
    feedback_type: str
    scope: IdentityScope
    comment: str = ""
    corrected_content: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["scope"] = self.scope.to_dict()
        return data
