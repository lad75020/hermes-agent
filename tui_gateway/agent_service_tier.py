"""Resolve configured fast-mode overrides when constructing a TUI agent."""


def agent_request_overrides(model, runtime, service_tier):
    overrides = dict(runtime.get("request_overrides") or {})
    if service_tier == "priority":
        from hermes_cli.models import resolve_fast_mode_overrides
        fast = resolve_fast_mode_overrides(model, provider=runtime.get("provider"), base_url=runtime.get("base_url"))
        overrides.update(fast or {})
    return overrides or None
