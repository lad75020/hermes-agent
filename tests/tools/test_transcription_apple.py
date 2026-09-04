"""Focused contracts for the macOS-native STT sibling.

Platform selection is tested as pure input. Calls that need Apple's frameworks
run only on a real macOS host; no test makes another host pretend to be macOS.
"""

from __future__ import annotations

import subprocess
import struct
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from tools import transcription_apple as apple


@pytest.fixture
def sample_wav(tmp_path):
    path = tmp_path / "sample.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(struct.pack("<16000h", *([0] * 16000)))
    return str(path)


def test_platform_gate_is_pure_input():
    assert apple._apple_platform_supported("Darwin", "26.0") is True
    assert apple._apple_platform_supported("Darwin", "27.1") is True
    assert apple._apple_platform_supported("Darwin", "15.7") is False
    assert apple._apple_platform_supported("Darwin", "") is False
    assert apple._apple_platform_supported("Linux", "26.0") is False
    assert apple._apple_platform_supported("Windows", "26.0") is False


@pytest.mark.parametrize(
    ("hook", "apple_language", "global_language", "env_language", "system_language", "expected"),
    [
        ("fr-CA", "de-DE", "en-US", "es-ES", "it-IT", "fr-CA"),
        (None, "de-DE", "en-US", "es-ES", "it-IT", "de-DE"),
        (None, "", "en-US", "es-ES", "it-IT", "en-US"),
        (None, None, "", "es-ES", "it-IT", "es-ES"),
        (None, None, None, None, "it-IT", "it-IT"),
    ],
)
def test_language_precedence(hook, apple_language, global_language, env_language, system_language, expected):
    assert apple._resolve_apple_language_values(
        hook, apple_language, global_language, env_language, system_language) == expected


def test_helper_timeout_is_a_failure_envelope(tmp_path, monkeypatch):
    helper = tmp_path / "helper"
    helper.touch()

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["helper"], 1)

    monkeypatch.setattr(apple, "_run", timeout)
    result = apple._helper_payload(helper, ["status"], 1)
    assert result["ok"] is False
    assert "timed out" in result["error"]


def test_helper_malformed_json_is_a_failure_envelope(tmp_path, monkeypatch):
    helper = tmp_path / "helper"
    helper.touch()
    monkeypatch.setattr(apple, "_run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "not json", ""))
    result = apple._helper_payload(helper, ["status"], 1)
    assert result == {"ok": False, "error": "Apple Speech helper returned malformed JSON"}


def test_helper_subprocess_failure_does_not_expose_a_traceback(tmp_path, monkeypatch):
    helper = tmp_path / "helper"
    helper.touch()
    monkeypatch.setattr(
        apple, "_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, ["helper"], output="", stderr="native failure"))),
    result = apple._helper_payload(helper, ["status"], 1)
    assert result == {"ok": False, "error": "native failure"}


def test_apple_is_local_for_upload_cap():
    from tools.transcription_tools import _is_local_stt_provider

    assert _is_local_stt_provider("apple", {}) is True


def test_explicit_apple_provider_is_kept_without_cloud_fallback():
    from tools.transcription_tools import _get_provider

    assert _get_provider({"provider": "apple"}) == "apple"


def test_default_config_keeps_asset_download_opt_in_disabled():
    from hermes_cli.config_defaults import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["stt"]["apple"]["download_assets"] is False


def test_oversized_apple_audio_reaches_the_local_dispatcher(tmp_path):
    """The remote-upload cap must not block the strictly local Apple backend."""
    from tools.transcription_common import MAX_FILE_SIZE
    from tools import transcription_tools as transcription

    audio = tmp_path / "oversized.wav"
    with audio.open("wb") as output:
        output.seek(MAX_FILE_SIZE)
        output.write(b"x")
    with patch.object(transcription, "_load_stt_config", return_value={"provider": "apple", "apple": {}}), \
         patch.object(transcription, "_get_provider", return_value="apple"), \
         patch.object(transcription, "_transcribe_apple", return_value={
             "success": True, "transcript": "native", "provider": "apple",
         }) as handler:
        result = transcription.transcribe_audio(str(audio))

    assert result["success"] is True
    handler.assert_called_once()


def test_explicit_apple_dispatches_without_auto_fallback(sample_wav):
    from tools import transcription_tools as transcription

    with patch.object(transcription, "_transcribe_apple", return_value={
        "success": True, "transcript": "native", "provider": "apple",
    }) as handler:
        result = transcription._dispatch_stt_provider(sample_wav, "apple", {"apple": {}}, source="gateway")

    assert result["provider"] == "apple"
    handler.assert_called_once()


@pytest.mark.macos_only
def test_apple_transcriber_returns_empty_transcript_as_success(sample_wav, monkeypatch):
    monkeypatch.setattr(apple, "_build_apple_helper", lambda: Path("/tmp/hermes-apple-stt"))
    monkeypatch.setattr(apple, "_helper_payload", lambda *_args, **_kwargs: {"ok": True, "transcript": ""})
    with patch("tools.transcription_tools._load_stt_config", return_value={"apple": {}}):
        result = apple._transcribe_apple(sample_wav, "apple-native")
    assert result == {"success": True, "transcript": "", "provider": "apple"}


@pytest.mark.macos_only
@pytest.mark.parametrize("download", [False, "false", "off", "0", None, True])
def test_asset_download_requires_opt_in_and_native_locale_is_deferred(sample_wav, monkeypatch, download):
    monkeypatch.delenv("HERMES_LOCAL_STT_LANGUAGE", raising=False)
    monkeypatch.setattr(apple, "_build_apple_helper", lambda: Path("/tmp/hermes-apple-stt"))
    with patch("tools.transcription_tools._load_stt_config", return_value={
        "language": "", "apple": {"download_assets": download},
    }), patch.object(apple, "_helper_payload", return_value={"ok": True, "transcript": "hello"}) as invoke:
        result = apple._transcribe_apple(sample_wav, "apple-native")
    assert result["success"] is True
    args = invoke.call_args.args[1]
    assert ("--download-assets" in args) is (download is True)
    # Foundation Locale.current, not Python's POSIX locale, selects the Mac's language.
    assert "--language" not in args
