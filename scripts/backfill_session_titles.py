#!/usr/bin/env python3
"""Backfill titles for existing untitled Hermes sessions.

This one-shot maintenance script finds sessions whose title is empty, extracts
the first titleable user request, and runs the current Hermes session-title
generator. By default it writes LLM-provenance titles to the active Hermes state
DB. Use ``--dry-run`` to preview candidates without calling the title LLM or
writing anything.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Iterable

# Allow running this file directly from a source checkout without installing the
# package first.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.title_generator import generate_title, is_titleable_user_message  # noqa: E402
from hermes_state import SessionDB  # noqa: E402

logger = logging.getLogger("backfill_session_titles")


def _content_to_text(content: Any) -> str:
    """Return human-readable text for stored message content."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif item.get("type") in {"image_url", "input_image"}:
                    parts.append("[image]")
                elif item.get("type") in {"file", "input_file"}:
                    parts.append("[file]")
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text.strip()
    return str(content).strip()


def _iter_untitled_sessions(
    db: SessionDB, *, source: str | None = None
) -> Iterable[dict[str, Any]]:
    """Yield sessions whose title/friendly name is empty."""
    clauses = ["(title IS NULL OR TRIM(title) = '')"]
    params: list[Any] = []
    if source:
        clauses.append("source = ?")
        params.append(source)

    query = f"""
        SELECT id, source, started_at, message_count
        FROM sessions
        WHERE {' AND '.join(clauses)}
        ORDER BY started_at ASC, id ASC
    """
    # Script-only maintenance query: SessionDB has no public untitled iterator.
    with db._lock:
        rows = db._conn.execute(query, params).fetchall()
    for row in rows:
        yield dict(row)


def _first_titleable_user_request(db: SessionDB, session_id: str) -> str | None:
    """Return the first real user request, skipping persisted control turns."""
    for message in db.get_messages(session_id):
        if message.get("role") != "user":
            continue
        text = _content_to_text(message.get("content"))
        if text and is_titleable_user_message(text):
            return text
    return None


def _set_unique_title(db: SessionDB, session_id: str, title: str) -> str:
    """Persist an LLM title, suffixing on collisions with existing sessions."""
    base = title.strip()
    candidate = base
    for _attempt in range(100):
        try:
            if db.set_auto_title(session_id, candidate, source="llm"):
                return candidate
            raise RuntimeError(
                f"session was renamed or disappeared before title update: {session_id}"
            )
        except ValueError as exc:
            if "already in use" not in str(exc):
                raise
            candidate = db.get_next_title_in_lineage(base)
    raise RuntimeError(
        f"could not find a unique title for {session_id!r} based on {base!r}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to state.db; defaults to the active Hermes home",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Only backfill one source, e.g. api, cli, telegram",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Maximum number of sessions to process"
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Per-title LLM timeout in seconds"
    )
    parser.add_argument(
        "--sleep", type=float, default=0.0, help="Delay between title-generation calls"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List candidates only; do not call the LLM or write titles",
    )
    parser.add_argument("--verbose", action="store_true", help="Show debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    db = SessionDB(args.db) if args.db else SessionDB()
    scanned = 0
    skipped = 0
    updated = 0
    failed = 0

    try:
        for session in _iter_untitled_sessions(db, source=args.source):
            if args.limit is not None and scanned >= max(0, args.limit):
                break
            scanned += 1
            session_id = session["id"]
            first_request = _first_titleable_user_request(db, session_id)
            if not first_request:
                skipped += 1
                logger.info(
                    "SKIP %s (%s): no titleable user request",
                    session_id,
                    session.get("source"),
                )
                continue

            preview = " ".join(first_request.split())[:100]
            if args.dry_run:
                logger.info(
                    "DRY  %s (%s): %s",
                    session_id,
                    session.get("source"),
                    preview,
                )
                continue

            try:
                title = generate_title(first_request, timeout=args.timeout)
                if not title:
                    skipped += 1
                    logger.warning("SKIP %s: generator returned no title", session_id)
                    continue
                final_title = _set_unique_title(db, session_id, title)
                updated += 1
                logger.info("OK   %s: %s", session_id, final_title)
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # Continue the one-shot batch after individual failures.
                failed += 1
                logger.error("FAIL %s: %s", session_id, exc)

            if args.sleep > 0:
                time.sleep(args.sleep)
    finally:
        db.close()

    logger.info(
        "Done. scanned=%d updated=%d skipped=%d failed=%d%s",
        scanned,
        updated,
        skipped,
        failed,
        " (dry run)" if args.dry_run else "",
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
