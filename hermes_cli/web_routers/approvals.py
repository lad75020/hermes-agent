"""Dashboard approval listing and resolution."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
_log = logging.getLogger(__name__)

class ApprovalResolve(BaseModel):
    session_key: Optional[str] = None
    choice: str
    resolve_all: bool = False


@router.get("/api/approvals")
async def get_approvals():
    """List pending gateway approval requests for dashboard/native clients."""
    try:
        from tools.approval import snapshot_gateway_approvals

        approvals = snapshot_gateway_approvals()
        return {"approvals": approvals, "count": len(approvals)}
    except Exception:
        _log.exception("GET /api/approvals failed")
        raise HTTPException(status_code=500, detail="Failed to list approvals")


def _normalize_approval_choice(choice: str) -> str:
    normalized = (choice or "").strip().lower()
    aliases = {
        "approve": "once",
        "allow": "once",
        "yes": "once",
        "no": "deny",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"once", "session", "always", "deny"}:
        raise HTTPException(status_code=400, detail="Invalid approval choice")
    return normalized


def _resolve_dashboard_approval(session_key: str, choice: str, resolve_all: bool = False):
    session_key = (session_key or "").strip()
    if not session_key:
        raise HTTPException(status_code=400, detail="session_key is required")
    normalized_choice = _normalize_approval_choice(choice)
    try:
        from tools.approval import resolve_gateway_approval

        resolved = resolve_gateway_approval(
            session_key,
            normalized_choice,
            resolve_all=bool(resolve_all),
        )
    except HTTPException:
        raise
    except Exception:
        _log.exception("POST /api/approvals/resolve failed")
        raise HTTPException(status_code=500, detail="Failed to resolve approval")
    if resolved <= 0:
        raise HTTPException(status_code=404, detail="No pending approval for session")
    return {
        "ok": True,
        "session_key": session_key,
        "choice": normalized_choice,
        "resolve_all": bool(resolve_all),
        "resolved": resolved,
    }


@router.post("/api/approvals/resolve")
async def resolve_approval(body: ApprovalResolve):
    return _resolve_dashboard_approval(
        body.session_key or "",
        body.choice,
        resolve_all=body.resolve_all,
    )


@router.post("/api/approvals/{session_key}/resolve")
async def resolve_approval_for_session(session_key: str, body: ApprovalResolve):
    return _resolve_dashboard_approval(
        session_key,
        body.choice,
        resolve_all=body.resolve_all,
    )
