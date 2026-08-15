"""Refresh the local Ollama provider model lists from ``ollama list``.

The ``ollama`` and ``ollama-launch`` providers in ``config.yaml`` carry a
static ``models:`` list that goes stale as the user pulls/removes models with
``ollama pull`` / ``ollama rm``. This module rewrites those lists from the
authoritative source of truth — the locally installed models reported by
``ollama list`` — so the model picker in the dashboard and gateway always
reflects what is actually installed.

It is wired into the dashboard startup (``cmd_dashboard`` just before
``start_server``) and the gateway foreground startup (``run_gateway`` just
before ``start_gateway``) so the refresh happens every time either surface
boots.

Design constraints:
  * **Best-effort / never fatal.** A missing ``ollama`` binary, a stopped
    daemon, a parse hiccup, or an unwritable config must never block the
    dashboard or gateway from starting. Every failure path is swallowed and
    (at most) logged at debug level.
  * **Surgical writes.** Only the ``models:`` list of each *already present*
    ``ollama`` / ``ollama-launch`` provider is touched. Providers that don't
    exist are left alone (we do not invent config). All other keys
    (``api``/``base_url``, ``api_key``, ``default_model``, ``name``, ...) are
    preserved verbatim by editing the raw on-disk config in place.
  * **No-op when unchanged.** If the installed set already matches config, no
    write happens (avoids needless mtime churn / cache invalidation).
"""

from __future__ import annotations

import logging
import shutil
import subprocess  # nosec B404 - fixed argv, no shell
from typing import List, Optional

logger = logging.getLogger(__name__)

# Providers whose ``models:`` list mirrors locally-installed Ollama models.
_OLLAMA_PROVIDER_NAMES = ("ollama", "ollama-launch")


def list_installed_ollama_models(timeout: float = 10.0) -> Optional[List[str]]:
    """Return installed model names from ``ollama list``, or ``None`` on failure.

    Parses the tabular output, taking the first whitespace-delimited column
    (``NAME``) of every row after the header. Returns ``None`` (not ``[]``)
    when ``ollama`` is unavailable or errors, so callers can distinguish
    "couldn't ask" from "asked, genuinely zero models" and avoid clobbering a
    populated config with an empty list on a transient failure.
    """
    exe = shutil.which("ollama")
    if not exe:
        logger.debug("ollama binary not found on PATH; skipping model refresh")
        return None

    try:
        proc = subprocess.run(  # nosec B603 - fixed argv from shutil.which, no shell
            [exe, "list"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("`ollama list` failed to run: %s", exc)
        return None

    if proc.returncode != 0:
        logger.debug(
            "`ollama list` exited %s (daemon down?); skipping refresh: %s",
            proc.returncode,
            (proc.stderr or "").strip(),
        )
        return None

    lines = (proc.stdout or "").splitlines()
    if not lines:
        return None

    models: List[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        first = line.split()[0]
        # Skip the header row (``NAME  ID  SIZE  MODIFIED``).
        if first.upper() == "NAME":
            continue
        if first not in seen:
            seen.add(first)
            models.append(first)

    # An empty result after a clean exit means genuinely no models installed;
    # return the empty list so config reflects reality. ``None`` is reserved
    # for the couldn't-ask cases handled above.
    return models


def refresh_ollama_provider_models(*, quiet: bool = True) -> bool:
    """Rewrite ``ollama`` / ``ollama-launch`` ``models:`` from ``ollama list``.

    Returns ``True`` when the config was updated on disk, ``False`` otherwise
    (nothing installed to change, no such providers, already up to date, or
    any best-effort failure). Never raises.
    """
    try:
        installed = list_installed_ollama_models()
        if not installed:
            # None (couldn't ask) or [] (nothing installed) → leave config as-is.
            return False

        from hermes_cli.config import (
            atomic_config_write,
            get_config_path,
            read_raw_config,
        )

        raw = read_raw_config()
        if not isinstance(raw, dict):
            return False
        providers = raw.get("providers")
        if not isinstance(providers, dict):
            return False

        changed = False
        updated_names: List[str] = []
        for name in _OLLAMA_PROVIDER_NAMES:
            entry = providers.get(name)
            if not isinstance(entry, dict):
                continue  # provider not configured — do not invent it
            current = entry.get("models")
            if current == installed:
                continue  # already current
            entry["models"] = list(installed)
            changed = True
            updated_names.append(name)

        if not changed:
            return False

        atomic_config_write(get_config_path(), raw, sort_keys=False)

        if not quiet:
            print(
                f"\u2713 Refreshed Ollama models from `ollama list` "
                f"({len(installed)} model(s)) for: {', '.join(updated_names)}"
            )
        logger.info(
            "Refreshed Ollama provider models (%d installed) for: %s",
            len(installed),
            ", ".join(updated_names),
        )
        return True
    except Exception:  # noqa: BLE001 - best-effort, must never break startup
        logger.debug("Ollama model refresh failed (non-fatal)", exc_info=True)
        return False
