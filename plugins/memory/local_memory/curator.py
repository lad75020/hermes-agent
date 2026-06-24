"""Curation and deduplication helpers for local memory."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List

from .models import CurationCandidate, DurableMemoryRecord, IdentityScope, content_hash, looks_like_secret, normalize_content, utc_now_iso

_MEMORY_TYPE_PATTERNS = [
    ("preference", re.compile(r"\b(prefer|likes?|wants?|does not want|hates?)\b", re.I)),
    ("correction", re.compile(r"\b(correction|actually|instead|not .* anymore)\b", re.I)),
    ("project_note", re.compile(r"\b(project|repo|application|service|uses|path)\b", re.I)),
    ("convention", re.compile(r"\b(always|never|convention|standard|format)\b", re.I)),
]


def classify_memory(content: str) -> str:
    for name, pattern in _MEMORY_TYPE_PATTERNS:
        if pattern.search(content):
            return name
    return "fact"


def candidate_from_text(content: str, confidence: float = 0.75) -> CurationCandidate | None:
    normalized = normalize_content(content)
    if len(normalized) < 10:
        return None
    if looks_like_secret(content):
        return None
    return CurationCandidate(content=content.strip()[:2000], memory_type=classify_memory(content), confidence=confidence)


def fallback_extract_candidates(user_content: str, assistant_content: str = "") -> List[CurationCandidate]:
    """Extract conservative candidates without an LLM when Ollama curation is unavailable."""
    text = "\n".join(part for part in [user_content, assistant_content] if part)
    candidates: List[CurationCandidate] = []
    explicit = re.findall(r"(?i)(?:remember that|please remember that|note that)\s+([^\n.]+[.]?)", text)
    for item in explicit:
        candidate = candidate_from_text(item, confidence=0.9)
        if candidate:
            candidates.append(candidate)
    # Keep fallback intentionally sparse: it should not diary temporary progress.
    return candidates


def parse_ollama_curation(raw: str) -> List[CurationCandidate]:
    """Parse strict-ish Ollama JSON curation output into validated candidates."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    raw_candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(raw_candidates, list):
        return []
    candidates: List[CurationCandidate] = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        candidate = candidate_from_text(content, float(item.get("confidence", 0.75)))
        if candidate:
            candidate.memory_type = str(item.get("memory_type") or candidate.memory_type)
            candidate.sensitivity = str(item.get("sensitivity") or "normal")
            candidates.append(candidate)
    return candidates


def build_memory(candidate: CurationCandidate, scope: IdentityScope, *, source_turn_id: str = "") -> DurableMemoryRecord:
    """Create a durable memory record from a curated candidate."""
    memory_id = content_hash(f"{scope.agent_identity}:{scope.agent_workspace}:{scope.user_id}:{candidate.content}")[:24]
    return DurableMemoryRecord(
        memory_id=memory_id,
        content=candidate.content,
        memory_type=candidate.memory_type,
        scope=scope,
        source_turn_ids=[source_turn_id] if source_turn_id else [],
        source_session_ids=[scope.session_id] if scope.session_id else [],
        confidence=max(0.0, min(1.0, candidate.confidence)),
        sensitivity=candidate.sensitivity,
    )


def should_merge(existing: DurableMemoryRecord, incoming: DurableMemoryRecord) -> bool:
    return existing.content_hash == incoming.content_hash or existing.normalized_content == incoming.normalized_content


def merge_memory(existing: DurableMemoryRecord, incoming: DurableMemoryRecord) -> DurableMemoryRecord:
    """Merge evidence from an incoming memory into an existing active memory."""
    existing.source_turn_ids = sorted(set(existing.source_turn_ids + incoming.source_turn_ids))
    existing.source_session_ids = sorted(set(existing.source_session_ids + incoming.source_session_ids))
    existing.confidence = max(existing.confidence, incoming.confidence)
    existing.updated_at = utc_now_iso()
    existing.revision += 1
    return existing
