"""Tests for hermes_cli.ollama_refresh — local Ollama model list refresh."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from hermes_cli import ollama_refresh as orf

_OLLAMA_LIST_OUTPUT = (
    "NAME                 ID              SIZE      MODIFIED     \n"
    "gemma4:31b-mlx       637cc0ff1570    18 GB     1 hour ago   \n"
    "qwen3.8:27b-mlx      5642e97495e1    18 GB     1 hour ago   \n"
    "nomic-embed:latest   0a109f422b47    274 MB    7 weeks ago  \n"
)
_EXPECTED = ["gemma4:31b-mlx", "qwen3.8:27b-mlx", "nomic-embed:latest"]


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ── list_installed_ollama_models ─────────────────────────────────────────


def test_parses_names_skips_header(monkeypatch):
    monkeypatch.setattr(orf.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        orf.subprocess, "run", lambda *a, **k: _Completed(0, _OLLAMA_LIST_OUTPUT)
    )
    assert orf.list_installed_ollama_models() == _EXPECTED


def test_missing_binary_returns_none(monkeypatch):
    monkeypatch.setattr(orf.shutil, "which", lambda _: None)
    assert orf.list_installed_ollama_models() is None


def test_nonzero_exit_returns_none(monkeypatch):
    monkeypatch.setattr(orf.shutil, "which", lambda _: "/usr/bin/ollama")
    monkeypatch.setattr(
        orf.subprocess, "run", lambda *a, **k: _Completed(1, "", "daemon down")
    )
    assert orf.list_installed_ollama_models() is None


def test_subprocess_error_returns_none(monkeypatch):
    monkeypatch.setattr(orf.shutil, "which", lambda _: "/usr/bin/ollama")

    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ollama", timeout=1)

    monkeypatch.setattr(orf.subprocess, "run", _boom)
    assert orf.list_installed_ollama_models() is None


def test_clean_run_zero_models_returns_empty(monkeypatch):
    monkeypatch.setattr(orf.shutil, "which", lambda _: "/usr/bin/ollama")
    header_only = "NAME    ID    SIZE    MODIFIED\n"
    monkeypatch.setattr(
        orf.subprocess, "run", lambda *a, **k: _Completed(0, header_only)
    )
    assert orf.list_installed_ollama_models() == []


def test_dedupes(monkeypatch):
    monkeypatch.setattr(orf.shutil, "which", lambda _: "/usr/bin/ollama")
    dupe = _OLLAMA_LIST_OUTPUT + "gemma4:31b-mlx  x  1 GB  now\n"
    monkeypatch.setattr(orf.subprocess, "run", lambda *a, **k: _Completed(0, dupe))
    assert orf.list_installed_ollama_models() == _EXPECTED


# ── refresh_ollama_provider_models ───────────────────────────────────────


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Point the config helpers at a temp config.yaml with both provider shapes."""
    path = tmp_path / "config.yaml"
    data = {
        "model": {"default": "x"},
        "providers": {
            "ollama-launch": {
                "api": "http://localhost:11434/v1",
                "default_model": "old:1b",
                "models": ["stale-a", "stale-b"],
                "name": "Ollama",
            },
            "ollama": {
                "base_url": "http://localhost:11434",
                "api_key": "ollama",
                "models": [],
            },
            "other": {"models": ["keep-me"]},
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    from hermes_cli import config as cfgmod

    monkeypatch.setattr(cfgmod, "get_config_path", lambda: path)
    # read_raw_config / atomic_config_write read+write the real path we set.
    monkeypatch.setattr(
        cfgmod, "read_raw_config", lambda: yaml.safe_load(path.read_text())
    )
    return path


def _install(monkeypatch, models):
    monkeypatch.setattr(orf, "list_installed_ollama_models", lambda *a, **k: models)


def test_refresh_rewrites_both_providers(cfg: Path, monkeypatch):
    _install(monkeypatch, _EXPECTED)
    assert orf.refresh_ollama_provider_models() is True
    out = yaml.safe_load(cfg.read_text())
    assert out["providers"]["ollama-launch"]["models"] == _EXPECTED
    assert out["providers"]["ollama"]["models"] == _EXPECTED
    # Non-ollama provider untouched.
    assert out["providers"]["other"]["models"] == ["keep-me"]
    # Sibling keys preserved verbatim.
    launch = out["providers"]["ollama-launch"]
    assert launch["api"] == "http://localhost:11434/v1"
    assert launch["default_model"] == "old:1b"
    assert launch["name"] == "Ollama"


def test_refresh_idempotent(cfg: Path, monkeypatch):
    _install(monkeypatch, _EXPECTED)
    assert orf.refresh_ollama_provider_models() is True
    # Second run: config already current → no write, returns False.
    assert orf.refresh_ollama_provider_models() is False


def test_refresh_noop_when_cannot_ask(cfg: Path, monkeypatch):
    _install(monkeypatch, None)  # couldn't ask
    assert orf.refresh_ollama_provider_models() is False
    out = yaml.safe_load(cfg.read_text())
    assert out["providers"]["ollama-launch"]["models"] == ["stale-a", "stale-b"]


def test_refresh_noop_when_empty(cfg: Path, monkeypatch):
    _install(monkeypatch, [])  # genuinely nothing installed → don't clobber
    assert orf.refresh_ollama_provider_models() is False
    out = yaml.safe_load(cfg.read_text())
    assert out["providers"]["ollama-launch"]["models"] == ["stale-a", "stale-b"]


def test_refresh_never_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(orf, "list_installed_ollama_models", _boom)
    assert orf.refresh_ollama_provider_models() is False
