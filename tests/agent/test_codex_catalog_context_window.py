"""Codex opt-in windows follow the same account and route's catalog maximum."""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent import model_metadata as mm
from agent.context_engine import ContextEngine


_BASE = "gpt-6.1-sol"
_VARIANT = f"{_BASE}-900k"
_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJjYXRhbG9nLXRlc3QifQ.test"
_ROUTE = {
    "provider": "openai-codex",
    "base_url": "https://chatgpt.com/backend-api/codex",
    "api_key": _TOKEN,
}


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr(mm, "_codex_oauth_context_cache", {})
    monkeypatch.setattr(mm, "_codex_oauth_max_context_cache", {})
    response = MagicMock(status_code=200)
    get = MagicMock(return_value=response)
    monkeypatch.setattr(mm.model_metadata_http, "get", get)

    def publish(default=500_000, maximum=872_000, slug=_BASE):
        item = {"slug": slug, "context_window": default}
        if maximum is not None:
            item["max_context_window"] = maximum
        response.json.return_value = {"models": [item]}
        return get

    return publish


@pytest.mark.parametrize("default", [272_000, 500_000, 1_050_000])
@pytest.mark.parametrize("maximum", [200_000, 872_000, 1_050_000])
def test_variant_uses_catalog_max_independently_of_default(catalog, default, maximum):
    get = catalog(default, maximum)
    expected = min(900_000, maximum)
    assert mm._resolve_codex_oauth_context_length_with_source(
        _VARIANT, _TOKEN, _ROUTE["base_url"]
    ) == (expected, "live")
    assert mm.get_model_context_length(_VARIANT, **_ROUTE) == expected
    assert mm._resolve_codex_oauth_context_length_with_source(
        f"openai/{_VARIANT}", _TOKEN, _ROUTE["base_url"]
    ) == (expected, "memory")
    assert mm.get_model_context_length(_BASE, **_ROUTE) == default
    assert mm.strip_codex_context_variant_suffix(_VARIANT) == _BASE
    get.assert_called_once()


@pytest.mark.parametrize("maximum", [None, 0, -1, "872000", 872_000.0, False, True])
@pytest.mark.parametrize("default", [272_000, 200_000, 500_000, 1_050_000])
def test_missing_or_invalid_max_preserves_conservative_fallback(catalog, default, maximum):
    catalog(default, maximum)
    expected = 900_000 if default == 272_000 else default
    assert mm.get_model_context_length(_VARIANT, **_ROUTE) == expected
    assert mm.get_model_context_length(_BASE, **_ROUTE) == default


@pytest.mark.parametrize("model", ["gpt-5.5", "gpt-5.5-900k", "gpt-6.1-sol-pro-900k"])
def test_ineligible_model_keeps_catalog_default(catalog, model):
    catalog(slug=model)
    assert mm.get_model_context_length(model, **_ROUTE) == 500_000
    assert mm.strip_codex_context_variant_suffix(model) == model


def test_changed_default_cap_survives_failed_refresh(catalog, monkeypatch):
    get = catalog(default=500_000, maximum=600_000)
    now = time.time()
    assert mm.get_model_context_length(_VARIANT, **_ROUTE) == 600_000
    monkeypatch.setattr(mm.time, "time", lambda: now + mm._CODEX_OAUTH_CONTEXT_CACHE_TTL + 1)
    get.side_effect = OSError("catalog unavailable")
    assert mm._resolve_codex_oauth_context_length_with_source(
        _VARIANT, _TOKEN, _ROUTE["base_url"]
    ) == (600_000, "fallback")
    assert mm.get_model_context_length(_VARIANT, **_ROUTE) == 600_000
    assert get.call_count == 2  # Failed refresh is negatively cached.


@pytest.mark.parametrize("maximum,expected", [(600_000, 600_000), (None, 500_000)])
def test_successful_ttl_refresh_replaces_catalog_maximum(catalog, monkeypatch, maximum, expected):
    now = time.time()
    monkeypatch.setattr(mm.time, "time", lambda: now)
    get = catalog(default=500_000, maximum=872_000)
    assert mm._resolve_codex_oauth_context_length_with_source(
        _VARIANT, _TOKEN, _ROUTE["base_url"]
    ) == (872_000, "live")

    catalog(default=500_000, maximum=maximum)
    assert mm._resolve_codex_oauth_context_length_with_source(
        _VARIANT, _TOKEN, _ROUTE["base_url"]
    ) == (872_000, "memory")
    get.assert_called_once()

    monkeypatch.setattr(mm.time, "time", lambda: now + mm._CODEX_OAUTH_CONTEXT_CACHE_TTL + 1)
    assert mm._resolve_codex_oauth_context_length_with_source(
        _VARIANT, _TOKEN, _ROUTE["base_url"]
    ) == (expected, "live")
    assert mm.get_model_context_length(_VARIANT, **_ROUTE) == expected
    assert mm.get_model_context_length(_BASE, **_ROUTE) == 500_000
    assert get.call_count == 2


@pytest.mark.parametrize("other_route", [
    {**_ROUTE, "api_key": _TOKEN + "-other-account"},
    {**_ROUTE, "base_url": "https://codex.example.test/v1"},
])
def test_observed_max_is_isolated_by_account_and_route(catalog, other_route):
    get = catalog(maximum=600_000)
    assert mm.get_model_context_length(_VARIANT, **_ROUTE) == 600_000
    catalog(default=500_000, maximum=None)
    assert mm.get_model_context_length(_VARIANT, **other_route) == 500_000
    assert mm.get_model_context_length(_VARIANT, **_ROUTE) == 600_000
    assert get.call_count == 2


def test_explicit_override_precedes_catalog(catalog):
    get = catalog()
    assert mm.get_model_context_length(
        _VARIANT, config_context_length=321_000, **_ROUTE
    ) == 321_000
    get.assert_not_called()


@pytest.mark.parametrize("maximum,expected", [(872_000, 872_000), (1_050_000, 900_000), (None, 900_000)])
def test_custom_codex_responses_route_keeps_table_first_policy(catalog, maximum, expected):
    get = catalog(maximum=maximum)
    base_url = "https://codex.example.test/v1"
    route = {
        "provider": "custom:codex-proxy", "base_url": base_url, "api_key": "test-proxy-key",
        "custom_providers": [{"name": "codex-proxy", "base_url": base_url, "api_mode": "codex_responses"}],
    }
    assert mm.get_model_context_length(_VARIANT, **route) == expected
    assert mm.get_model_context_length(_BASE, **route) == mm._CODEX_OAUTH_CONTEXT_FALLBACK[_BASE]
    get.assert_called_once()
    assert get.call_args.args[0].startswith(f"{base_url}/models?")
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer test-proxy-key"


class _CatalogEngine(ContextEngine):
    """Exercise the external-engine host contract without loading a live plugin."""

    name = "catalog-test"
    threshold_percent = 0.7

    def update_from_response(self, usage):
        self.last_prompt_tokens = usage["prompt_tokens"]

    def should_compress(self, prompt_tokens=None):
        return (self.last_prompt_tokens if prompt_tokens is None else prompt_tokens) >= self.threshold_tokens

    def compress(self, messages, current_tokens=None):
        return messages


@pytest.mark.parametrize("external", [False, True], ids=["builtin", "external"])
def test_catalog_window_reaches_engines_usage_and_breakdown(catalog, external):
    # Use the test interpreter without consulting or activating the adjacent installed runtime.
    with (
        patch("pm.environments.activate_dependencies"),
        patch("hermes_cli._early_recovery.recover_if_needed"),
        patch("hermes_cli.venv_sync.prepare_launch", return_value=None),
    ):
        from agent.agent_init import _build_context_engine, _parse_compression_config
        from tui_gateway.server import _get_usage
    from agent.context_breakdown import compute_session_context_breakdown
    from agent.context_compressor import ContextCompressor

    get = catalog()
    engine = _CatalogEngine() if external else None
    cfg = {"compression": {"threshold": 0.7, "threshold_tokens": None}}
    if external:
        cfg["context"] = {"engine": engine.name}
    agent = SimpleNamespace(
        model=_VARIANT, **_ROUTE, api_mode="codex_responses", quiet_mode=True,
        session_id="catalog-context-test", max_tokens=None, tools=[], _memory_store=None,
    )
    parts = {"stable": "test guidance", "context": "", "volatile": ""}
    with (
        patch("plugins.context_engine.load_context_engine", return_value=engine),
        patch("agent.system_prompt.build_system_prompt_parts", return_value=parts),
    ):
        # Rebuilding for the base and back must not retain the previous model's window.
        for model, expected in [(_VARIANT, 872_000), (_BASE, 500_000), (_VARIANT, 872_000)]:
            agent.model = model
            cs = _parse_compression_config(agent, cfg)
            _build_context_engine(agent, cfg, cs, None, None, None)
            compressor = agent.context_compressor
            if external:
                assert compressor is engine
            else:
                assert isinstance(compressor, ContextCompressor)
            assert compressor.context_length == expected
            if model == _VARIANT:
                assert compressor.threshold_tokens == 610_400
            compressor.update_from_response({"prompt_tokens": 436_000, "completion_tokens": 0})
            usage = _get_usage(agent)
            breakdown = compute_session_context_breakdown(agent, [{"role": "user", "content": "hello"}])
            for payload in (usage, breakdown):
                assert payload["context_max"] == expected
                assert payload["context_used"] == 436_000
                assert payload["context_percent"] == round(436_000 / expected * 100)
    get.assert_called_once()
