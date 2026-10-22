"""Desktop native extras must not block unrelated plugin admission on Android."""

import os
from pathlib import Path
import shutil
import sys
import tomllib

from packaging.markers import Marker, default_environment
from packaging.requirements import Requirement
import pytest
import tomli_w

from pm import extras, workspace
from pm.environment import PythonEnvironment
from tests.pm._fixtures import _wheel


def _metadata():
    root = Path(__file__).resolve().parents[2]
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("system,supported", [
    ("android", False), ("linux", True), ("darwin", True), ("win32", True),
])
def test_google_meet_selection_and_explicit_install_gate(monkeypatch, system, supported):
    monkeypatch.setattr(extras, "_PLATFORM_GATES", None)
    environment = {**default_environment(), "sys_platform": system,
                   "python_version": "3.14", "python_full_version": "3.14.0"}
    metadata = _metadata()
    assert any(Marker(marker).evaluate(environment)
               for marker in metadata["tool"]["uv"]["environments"])
    requirements = metadata["project"]["optional-dependencies"]["google-meet"]
    for requirement in map(Requirement, requirements):
        assert (requirement.marker is None or requirement.marker.evaluate(environment)) == supported
    assert extras.extra_supported("google-meet", environment=environment,
                                  importable=lambda _: False) == supported


@pytest.mark.parametrize("system,platform_system,machine", [
    ("android", "Android", "aarch64"),
    ("linux", "Linux", "x86_64"),
    ("darwin", "Darwin", "arm64"),
    ("darwin", "Darwin", "x86_64"),
    ("win32", "Windows", "AMD64"),
    ("win32", "Windows", "ARM64"),
])
def test_native_audio_selection_and_explicit_install_gates(
    monkeypatch, system, platform_system, machine,
):
    monkeypatch.setattr(extras, "_PLATFORM_GATES", None)
    environment = {**default_environment(), "sys_platform": system,
                   "platform_system": platform_system, "platform_machine": machine,
                   "python_version": "3.14", "python_full_version": "3.14.0"}
    optional = _metadata()["project"]["optional-dependencies"]
    supported = (system != "android"
                 and not (system == "darwin" and machine == "x86_64")
                 and not (system == "win32" and machine == "ARM64"))
    native = {"faster-whisper", "pyopen-wakeword", "kittentts", "piper-tts"}
    for extra in ("voice", "stt-whisper", "wake", "wake-openwakeword", "kittentts", "piper"):
        selected = {req.name for req in map(Requirement, optional[extra])
                    if req.marker is None or req.marker.evaluate(environment)}
        assert bool(selected & native) == supported, extra
        # Mixed bundles retain audio I/O and other wake engines.
        assert extras.extra_supported(extra, environment=environment,
                                      importable=lambda _: False) == (
            supported or extra in {"voice", "wake"}
        ), extra
        if extra == "voice":
            assert {"sounddevice", "numpy"} <= selected
        elif extra == "wake":
            assert {"sherpa-onnx", "sherpa-onnx-core", "pvporcupine"} <= selected
        elif not supported:
            assert not selected, extra
    for extra in ("audio-io", "wake-sherpa", "wake-porcupine"):
        assert extras.extra_supported(extra, environment=environment,
                                      importable=lambda _: False)
        assert all(req.marker is None or req.marker.evaluate(environment)
                   for req in map(Requirement, optional[extra]))


def test_plugin_workspace_locks_with_android_and_desktop_targets(tmp_path):
    """Resolve real core extra metadata against offline, desktop-only native wheels.

    A plugin triggers a fresh universal lock even when Google Meet is not selected.
    Requiring Android wheel coverage makes this independent of the test host.
    """
    metadata = _metadata()
    optional = metadata["project"]["optional-dependencies"]
    groups = ("google-meet", "voice", "stt-whisper", "wake", "wake-openwakeword",
              "kittentts", "piper", "wake-sherpa", "wake-porcupine")
    # Keep real requirement markers; substitute local artifacts for direct URLs.
    requirements = {}
    versions = {}
    for group in groups:
        requirements[group] = []
        for req in map(Requirement, optional[group]):
            if req.url:
                requested_extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
                req = Requirement(f"{req.name}{requested_extras}==1.0; {req.marker}")
            requirements[group].append(str(req))
            versions[req.name] = next(iter(req.specifier)).version
    versions["onnxruntime"] = "1.0"
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    for name, version in versions.items():
        tag = "manylinux_2_17_x86_64" if name in {
            "playwright", "pyopen-wakeword", "onnxruntime",
        } else "any"
        dependencies = ["onnxruntime==1.0"] if name in {
            "faster-whisper", "kittentts", "piper-tts",
        } else []
        distribution = name.replace("-", "_")
        wheel = _wheel(wheels, distribution, version, requirements=dependencies, extra={
            f"{distribution}-{version}.dist-info/WHEEL":
                f"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-{tag}\n",
        })
        if tag != "any":
            # No Android artifact, matching the native admission blockers.
            wheel.rename(wheel.with_name(wheel.name.replace(
                "-any.whl", f"-{tag}.whl")))
    _wheel(wheels, "plugin_dep")
    core = tmp_path / "core"
    core.mkdir()
    (core / "pyproject.toml").write_text(tomli_w.dumps({
        "project": {
            "name": "hermes-agent", "version": "0.0.0",
            "requires-python": metadata["project"]["requires-python"],
            "optional-dependencies": requirements,
        },
        "tool": {"uv": {
            "package": False, "no-index": True, "find-links": [wheels.as_posix()],
            "environments": metadata["tool"]["uv"]["environments"],
            "required-environments": [
                "sys_platform == 'android' and platform_machine == 'aarch64'",
                "sys_platform == 'linux' and platform_machine == 'x86_64'",
            ],
        }},
    }), encoding="utf-8")
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "plugin.yaml").write_text(
        'name: admission-probe\npython_dependencies: ["plugin-dep==1.0"]\n',
        encoding="utf-8",
    )
    generated = tmp_path / "workspace"
    workspace._generate_pyproject([plugin], generated, source=core)
    uv = shutil.which("uv")
    assert uv, "workspace resolution regression requires real uv"
    environment = PythonEnvironment(
        uv=Path(uv), python=Path(sys.executable), destination=tmp_path / "unused-env",
        cache=tmp_path / "cache", env=dict(os.environ), offline=True,
    )
    environment.lock(generated)
    environment.check_lock(generated)
    locked = tomllib.loads((generated / "uv.lock").read_text(encoding="utf-8"))
    assert {"playwright", "onnxruntime", "pyopen-wakeword", "plugin-dep"} <= {
        p["name"] for p in locked["package"]
    }
    assert not (core / "uv.lock").exists()
    assert not (plugin / "pyproject.toml").exists()
