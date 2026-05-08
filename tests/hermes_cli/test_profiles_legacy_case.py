"""Behavior retained from the local changes during the upstream rebase."""

from hermes_cli.profiles import get_profile_dir, list_profiles
from tests.hermes_cli.test_profiles import profile_env as profile_env


class TestLegacyProfileCase:
    def test_existing_legacy_mixed_case_profile_dir_resolves(self, profile_env):
        tmp_path = profile_env
        legacy_dir = tmp_path / ".hermes" / "profiles" / "Ollama"
        legacy_dir.mkdir(parents=True)
        assert get_profile_dir("ollama") == legacy_dir
        assert get_profile_dir("Ollama") == legacy_dir

    def test_includes_legacy_mixed_case_profile_dirs_normalized(self, profile_env):
        tmp_path = profile_env
        legacy_dir = tmp_path / ".hermes" / "profiles" / "Ollama"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "config.yaml").write_text("model:\n  default: gemma4:e4b\n  provider: custom\n")
        profiles = list_profiles()
        by_name = {p.name: p for p in profiles}
        assert "ollama" in by_name
        assert by_name["ollama"].path == legacy_dir
        assert by_name["ollama"].model == "gemma4:e4b"
        assert by_name["ollama"].provider == "custom"
