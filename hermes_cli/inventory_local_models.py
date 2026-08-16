"""Fallback picker row for the local Ollama Launch provider."""

def _build_ollama_launch_row_if_missing(ctx) -> dict | None:
    """Build a fallback ollama-launch row from local installed models.

    A profile can point ``model.provider`` at ``ollama-launch`` without
    carrying a persisted ``providers.ollama-launch`` config block. In that
    case provider discovery currently returns no row (no credential-backed
    source), so picker surfaces lose all models even though ``ollama list``
    is authoritative for local instances.
    """
    if str(ctx.current_provider or "").strip().lower() != "ollama-launch":
        return None
    try:
        from hermes_cli.ollama_refresh import list_installed_ollama_models
    except Exception:
        return None

    try:
        models = list_installed_ollama_models(timeout=1.5)
    except Exception:
        return None
    if models is None:
        return None

    return {
        "slug": "ollama-launch",
        "name": "Ollama Launch",
        "is_current": True,
        "is_user_defined": False,
        "models": list(models),
        "total_models": len(models),
        "source": "configured-current",
    }
