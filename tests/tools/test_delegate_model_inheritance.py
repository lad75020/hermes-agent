"""Behavioral tests for delegated model inheritance routes."""

from types import SimpleNamespace

from tools.delegate_tool_config import _resolve_child_runtime, _resolve_delegation_credentials


def _parent():
    fallback_entry = {"provider": "nous", "model": "fallback-model"}
    return SimpleNamespace(
        model="parent-model",
        provider="nous",
        requested_provider="nous",
        base_url="https://inference.nousresearch.com/v1",
        api_key="test-key",
        api_mode="chat_completions",
        client=None,
        _client_kwargs={},
        request_overrides={},
        capabilities={},
        acp_command=None,
        acp_args=[],
        reasoning_config=None,
        _fallback_chain=[fallback_entry],
        openrouter_min_coding_score=None,
        providers_allowed=None,
        providers_ignored=None,
        providers_order=None,
        provider_sort=None,
        provider_require_parameters=False,
        provider_data_collection="",
        max_tokens=None,
    ), fallback_entry


def test_auto_model_route_inherits_parent_model_and_fallback():
    parent, fallback_entry = _parent()

    credentials = _resolve_delegation_credentials({"model": "auto"}, parent)
    assert credentials["model"] is None

    child = _resolve_child_runtime(
        parent,
        {},
        parent.api_key,
        model="auto",
        override_provider=credentials["provider"],
        override_base_url=credentials["base_url"],
        override_api_key=credentials["api_key"],
        override_api_mode=credentials["api_mode"],
        override_acp_command=None,
        override_acp_args=None,
    )

    assert child["model"] == parent.model
    assert child["provider"] == parent.provider
    assert child["fallback_model"] == [fallback_entry]
