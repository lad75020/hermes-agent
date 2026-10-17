"""launchd opens bootstrap stdio before the gateway can access its runtime home."""

import hashlib
import json
import plistlib
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import hermes_cli.gateway as gw

pytestmark = pytest.mark.platforms("macos")


@pytest.fixture
def launchd_account(tmp_path, monkeypatch, _isolate_launchd_bootstrap_logs):
    import pwd
    import hermes_constants
    from hermes_cli import gateway_launchd

    monkeypatch.setattr(gateway_launchd, "_launchd_bootstrap_log_dir", _isolate_launchd_bootstrap_logs)
    account = tmp_path / "account"
    monkeypatch.setattr(gw, "PROJECT_ROOT", tmp_path / "checkout")
    monkeypatch.setattr(gw, "get_python_path", lambda: sys.executable)
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: SimpleNamespace(pw_dir=str(account)))
    monkeypatch.setattr(Path, "home", lambda: account)
    monkeypatch.setattr(hermes_constants, "_get_platform_default_hermes_home", lambda: account / ".hermes")
    monkeypatch.setattr(gw, "_build_service_path_dirs", lambda: ["/usr/bin"])
    monkeypatch.setattr(gw, "_append_node_dir_for_service", lambda dirs: None)
    monkeypatch.setenv("PATH", "/usr/bin")
    return account


def test_bootstrap_stdio_is_local_and_service_scoped(launchd_account, tmp_path, monkeypatch):
    """All service identities keep runtime redirection while launchd opens local files."""
    account = launchd_account
    external = tmp_path / "external" / "hermes"
    other = tmp_path / "other-external" / "hermes"
    homes = [account / ".hermes", external, external / "profiles" / "work", other]
    suffixes = ["", hashlib.sha256(str(external).encode()).hexdigest()[:8], "work",
                hashlib.sha256(str(other).encode()).hexdigest()[:8]]
    paths = set()
    for home, suffix in zip(homes, suffixes):
        monkeypatch.setenv("HERMES_HOME", str(home))
        # Profile isolation may remap HOME; launchd paths belong to the account.
        monkeypatch.setenv("HOME", str(home / "home"))
        label = "ai.hermes.gateway" + (f"-{suffix}" if suffix else "")
        bootstrap = account / "Library" / "Logs" / "Hermes"
        if suffix:
            bootstrap /= label
        first = plistlib.loads(gw.generate_launchd_plist().encode())
        second = plistlib.loads(gw.generate_launchd_plist().encode())
        assert first["Label"] == label
        assert first["StandardOutPath"] == second["StandardOutPath"] == str(bootstrap / "gateway.log")
        assert first["StandardErrorPath"] == second["StandardErrorPath"] == str(bootstrap / "gateway.error.log")
        assert bootstrap.is_dir()
        paths.add(first["StandardOutPath"])
        assert first["EnvironmentVariables"]["HERMES_HOME"] == str(home)
        args = first["ProgramArguments"]
        assert args[:4] == ["/usr/bin/osascript", "-l", "JavaScript", "-e"]
        start = args[4].index("$.system(") + len("$.system(")
        shell, _ = json.JSONDecoder().raw_decode(args[4], start)
        argv = shlex.split(shell)
        assert argv[-4:] == [">>", str(home / "logs" / "gateway.log"),
                             "2>>", str(home / "logs" / "gateway.error.log")]
        error_arg = argv.index("--error-log")
        assert argv[error_arg + 1] == str(home / "logs" / "gateway.error.log")
        assert "--external-supervisor" in argv
    assert len(paths) == len(homes)


def test_bootstrap_stdio_round_trips_xml_path(launchd_account, tmp_path, monkeypatch):
    import pwd

    account = launchd_account / 'local & <logs> "quoted"'
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: SimpleNamespace(pw_dir=str(account)))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "external"))
    parsed = plistlib.loads(gw.generate_launchd_plist().encode())
    bootstrap = account / "Library" / "Logs" / "Hermes" / parsed["Label"]
    assert parsed["StandardOutPath"] == str(bootstrap / "gateway.log")
    assert parsed["StandardErrorPath"] == str(bootstrap / "gateway.error.log")
