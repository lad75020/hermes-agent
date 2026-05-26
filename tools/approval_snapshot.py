"""Serializable pending-approval views for API and dashboard clients."""

def snapshot_gateway_approvals() -> list[dict]:
    """Return serializable snapshots of pending gateway approvals.

    The dashboard/native apps must not see private thread Event objects or
    mutate the queue directly. They resolve approvals FIFO by ``session_key``
    through :func:`resolve_gateway_approval`.
    """
    from tools.approval import _lock, _gateway_queues
    snapshots: list[dict] = []
    with _lock:
        queues = [(session_key, list(queue)) for session_key, queue in _gateway_queues.items()]

    for session_key, queue in queues:
        for index, entry in enumerate(queue, start=1):
            data = dict(entry.data or {})
            pattern_key = data.get("pattern_key") or ""
            pattern_keys = data.get("pattern_keys") or ([pattern_key] if pattern_key else [])
            pattern_keys = [str(key) for key in pattern_keys if str(key)]
            has_tirith = any(key.startswith("tirith:") for key in pattern_keys)
            scope_options = ["once", "session"]
            if not has_tirith:
                scope_options.append("always")
            scope_options.append("deny")
            snapshots.append({
                "id": f"{session_key}:{index}",
                "session_key": session_key,
                "queue_position": index,
                "kind": data.get("kind") or "shell_command",
                "title": data.get("title") or (
                    "Security approval required" if has_tirith else "Command approval required"
                ),
                "command": str(data.get("command") or ""),
                "description": str(data.get("description") or ""),
                "pattern_key": pattern_key or None,
                "pattern_keys": pattern_keys,
                "created_at": getattr(entry, "created_at", None),
                "surface": data.get("surface") or "gateway",
                "scope_options": scope_options,
            })
    return snapshots
