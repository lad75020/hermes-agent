"""GPT-6.2 Sol extended context is an explicit, catalog-gated 872K opt-in."""

from unittest.mock import MagicMock

import pytest

from agent import model_metadata as mm
from hermes_cli import codex_models


BASE = "gpt-6.2-sol"
VARIANT = f"{BASE}-900k"
TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJleHRlbmRlZC10ZXN0In0.test"
URL = "https://chatgpt.com/backend-api/codex"


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr(mm, "_codex_oauth_context_cache", {})
    monkeypatch.setattr(mm, "_codex_oauth_max_context_cache", {})
    response = MagicMock(status_code=200)
    get = MagicMock(return_value=response)
    monkeypatch.setattr(mm.model_metadata_http, "get", get)
    monkeypatch.setattr("httpx.get", get)
    monkeypatch.setattr(codex_models, "_read_default_model", lambda *a: VARIANT)
    monkeypatch.setattr(codex_models, "_read_cache_models", lambda *a: [BASE, VARIANT])

    def publish(default=500_000, maximum=872_000, slug=BASE):
        item = {"slug": slug, "context_window": default}
        if maximum is not None:
            item["max_context_window"] = maximum
        response.json.return_value = {"models": [item]}
        return get

    return publish


def test_picker_derives_opt_in_only_from_account_discovered_base(catalog):
    get = catalog()
    models = codex_models.get_codex_model_ids(access_token=TOKEN, base_url=URL)
    assert models == [BASE, VARIANT]
    assert mm.has_codex_context_variant(BASE)
    assert mm.is_codex_context_variant(VARIANT)
    # Offline config/cache hints cannot bypass this model's account-discovery gate.
    assert codex_models.codex_model_requires_account_discovery(VARIANT)
    fallback = codex_models.get_codex_model_ids()
    assert BASE not in fallback and VARIANT not in fallback
    catalog(slug="gpt-6.1-sol")
    other_account = codex_models.get_codex_model_ids(access_token=TOKEN, base_url=URL)
    assert BASE not in other_account and VARIANT not in other_account
    assert get.call_count == 2


@pytest.mark.parametrize("base", [
    "gpt-6.2-astra", "gpt-6.2-sol-pro", "gpt-6.2-sol-mini",
    "gpt-6.2-sol-2026-11-22", "gpt-6.2-astra-2026-11-22", "gpt-6.20-sol",
])
def test_similar_models_do_not_gain_extended_context(catalog, base):
    catalog(slug=base)
    assert not mm.has_codex_context_variant(base)
    assert not mm.is_codex_context_variant(f"{base}-900k")
    assert mm.strip_codex_context_variant_suffix(f"{base}-900k") == f"{base}-900k"
    assert f"{base}-900k" not in codex_models.get_codex_model_ids(access_token=TOKEN, base_url=URL)


@pytest.mark.parametrize("prefix", ["", "openai/"])
def test_opt_in_wire_model_and_capabilities_match_base(prefix):
    from agent.reasoning_effort import codex_supported_efforts
    from agent.transports.codex import ResponsesApiTransport
    from hermes_cli.models import model_supports_ultrafast

    model = prefix + VARIANT
    assert mm.strip_codex_context_variant_suffix(model) == prefix + BASE
    assert mm.strip_codex_context_variant_suffix(prefix + BASE) == prefix + BASE
    assert codex_supported_efforts(model) == codex_supported_efforts(BASE)
    assert model_supports_ultrafast(model) == model_supports_ultrafast(BASE)
    transport = ResponsesApiTransport()
    kwargs = transport.build_kwargs(
        model=model, messages=[{"role": "user", "content": "Hi"}], tools=[],
        provider="openai-codex", base_url=URL, is_codex_backend=True,
        request_overrides={"reasoning": {"effort": "none"}, "temperature": 0.5},
    )
    wire = transport.preflight_kwargs(kwargs, sanitize_harmony_tokens=True)
    assert wire["model"] == prefix + BASE
    assert wire["reasoning"]["effort"] == "low"
    assert "temperature" not in wire


@pytest.mark.parametrize("default", [272_000, 500_000, 1_050_000])
@pytest.mark.parametrize("maximum", [200_000, 600_000, 872_000, 900_000, 1_050_000])
def test_opt_in_uses_published_maximum_bounded_by_approved_ceiling(catalog, default, maximum):
    get = catalog(default, maximum)
    expected = min(872_000, maximum)
    assert mm._resolve_codex_oauth_context_length_with_source(VARIANT, TOKEN, URL) == (expected, "live")
    assert mm.get_model_context_length(VARIANT, provider="openai-codex", api_key=TOKEN, base_url=URL) == expected
    assert mm._resolve_codex_oauth_context_length_with_source(f"openai/{VARIANT}", TOKEN, URL) == (expected, "memory")
    assert mm.get_model_context_length(BASE, provider="openai-codex", api_key=TOKEN, base_url=URL) == default
    get.assert_called_once()


@pytest.mark.parametrize("default", [272_000, 500_000, 1_050_000])
@pytest.mark.parametrize("maximum", [None, 0, -1, "872000", 872_000.0, False, True, {}, []])
def test_opt_in_never_expands_without_valid_catalog_maximum(catalog, default, maximum):
    catalog(default, maximum)
    assert mm.get_model_context_length(VARIANT, provider="openai-codex", api_key=TOKEN, base_url=URL) == min(default, 872_000)
    assert mm.get_model_context_length(BASE, provider="openai-codex", api_key=TOKEN, base_url=URL) == default


def test_offline_opt_in_and_base_keep_500k_fallback(catalog):
    get = catalog()
    get.side_effect = OSError("catalog unavailable")
    for token in ("", TOKEN):
        for model in (BASE, VARIANT):
            assert mm._resolve_codex_oauth_context_length_with_source(model, token, URL) == (500_000, "fallback")
    get.assert_called_once()


@pytest.mark.parametrize("maximum,expected", [(600_000, 600_000), (872_000, 872_000), (1_050_000, 872_000), (None, 500_000), (True, 500_000)])
def test_custom_codex_route_uses_own_published_maximum(catalog, maximum, expected):
    # A proxy's direct-API-sized default is not evidence for expanding the Codex window.
    get = catalog(default=1_050_000, maximum=maximum)
    proxy = "https://codex.example.test/v1"
    route = {
        "provider": "custom:codex-proxy", "base_url": proxy, "api_key": "test-proxy-key",
        "custom_providers": [{"name": "codex-proxy", "base_url": proxy, "api_mode": "codex_responses"}],
    }
    assert mm.get_model_context_length(VARIANT, **route) == expected
    assert mm.get_model_context_length(BASE, **route) == 500_000
    get.assert_called_once()
    assert get.call_args.args[0].startswith(f"{proxy}/models?")
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer test-proxy-key"


@pytest.mark.parametrize("other_token,other_url", [(TOKEN + "-other", URL), (TOKEN, "https://codex.example.test/v1")])
def test_catalog_evidence_does_not_cross_accounts_or_endpoints(catalog, other_token, other_url):
    catalog()
    assert mm._resolve_codex_oauth_context_length_with_source(VARIANT, TOKEN, URL) == (872_000, "live")
    catalog(maximum=None)
    assert mm._resolve_codex_oauth_context_length_with_source(VARIANT, other_token, other_url) == (500_000, "live")
    assert mm._resolve_codex_oauth_context_length_with_source(VARIANT, TOKEN, URL) == (872_000, "memory")
