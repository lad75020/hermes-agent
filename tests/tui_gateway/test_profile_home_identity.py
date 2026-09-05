"""Stable TUI Gateway profile identities across filesystem aliases."""

from __future__ import annotations

from types import SimpleNamespace

import tui_gateway.server as server


def test_config_and_profile_inventory_share_resolved_home_identity(tmp_path, monkeypatch):
    real_home = tmp_path / "real-home"
    real_home.mkdir()
    alias_home = tmp_path / "alias-home"
    alias_home.symlink_to(real_home, target_is_directory=True)

    monkeypatch.setattr(server, "_hermes_home", real_home)

    import hermes_cli.profiles as profiles

    monkeypatch.setattr(
        profiles,
        "list_profiles",
        lambda: [
            SimpleNamespace(
                name="default",
                path=alias_home,
                is_default=True,
                model="gpt-5",
                provider="openai",
                description="",
                display_name="",
                skill_count=0,
            )
        ],
    )

    config = server._methods["config.get"](
        "config", {"key": "profile"}
    )["result"]
    profile = server._methods["profiles.list"](
        "profiles", {"include_sessions": False}
    )["result"]["profiles"][0]

    assert config["home"] == str(real_home)
    assert profile["path"] == str(alias_home)
    assert config["home_identity"] == profile["path_identity"]
    assert config["home_identity"] == str(real_home.resolve())


def test_profile_identity_is_recomputed_after_symlink_retarget(tmp_path, monkeypatch):
    first_home = tmp_path / "first-home"
    second_home = tmp_path / "second-home"
    first_home.mkdir()
    second_home.mkdir()
    alias_home = tmp_path / "alias-home"
    alias_home.symlink_to(first_home, target_is_directory=True)

    import hermes_cli.profiles as profiles

    profile = SimpleNamespace(
        name="default",
        path=alias_home,
        is_default=True,
        model="gpt-5",
        provider="openai",
        description="",
        display_name="",
        skill_count=0,
    )
    monkeypatch.setattr(profiles, "list_profiles", lambda: [profile])

    first_identity = server._methods["profiles.list"](
        "first", {"include_sessions": False}
    )["result"]["profiles"][0]["path_identity"]

    alias_home.unlink()
    alias_home.symlink_to(second_home, target_is_directory=True)
    second_identity = server._methods["profiles.list"](
        "second", {"include_sessions": False}
    )["result"]["profiles"][0]["path_identity"]

    assert first_identity == str(first_home.resolve())
    assert second_identity == str(second_home.resolve())
    assert second_identity != first_identity


def test_broken_profile_alias_has_no_usable_identity(tmp_path, monkeypatch):
    broken_alias = tmp_path / "broken-alias"
    broken_alias.symlink_to(tmp_path / "missing-home", target_is_directory=True)

    import hermes_cli.profiles as profiles

    monkeypatch.setattr(
        profiles,
        "list_profiles",
        lambda: [
            SimpleNamespace(
                name="default",
                path=broken_alias,
                is_default=True,
                model="gpt-5",
                provider="openai",
                description="",
                display_name="",
                skill_count=0,
            )
        ],
    )

    profile = server._methods["profiles.list"](
        "profiles", {"include_sessions": False}
    )["result"]["profiles"][0]

    assert profile["path_identity"] is None
