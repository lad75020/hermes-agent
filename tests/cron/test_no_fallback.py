"""Per-job fallback policy."""
from cron.scheduler import _job_fallback_chain

def test_no_fallback_disables_inherited_chain():
    cfg = {"fallback_providers": [{"provider": "anthropic", "model": "backup"}]}
    assert _job_fallback_chain({"no_fallback": True}, cfg) is None
    assert _job_fallback_chain({}, cfg)
