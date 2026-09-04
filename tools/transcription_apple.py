"""macOS 26+ on-device SpeechAnalyzer transcription backend.

The bundled Swift source is compiled into the active profile cache on demand.
It deliberately has no Python dependency and never asks macOS to download speech
assets unless ``stt.apple.download_assets`` is explicitly enabled.
"""

from __future__ import annotations

import hashlib
import json

import os
import platform
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from hermes_constants import get_hermes_home
from tools.transcription_common import _config_number, _error_result, _ok_result
from utils import is_truthy_value

_APPLE_SOURCE = Path(__file__).parent / "apple_stt" / "hermes_apple_stt.swift"
_APPLE_CACHE_DIRNAME = "apple-stt"
_APPLE_BUILD_TIMEOUT_SECONDS = 90
_APPLE_TRANSCRIBE_TIMEOUT_SECONDS = 180
_APPLE_NATIVE_FORMATS = frozenset({".wav", ".aif", ".aiff", ".caf", ".m4a", ".mp3", ".aac"})


def _apple_platform_supported(system_name: str, version: str) -> bool:
    """Pure platform gate kept testable without pretending the host is another OS."""
    major = version.split(".", 1)[0]
    return system_name == "Darwin" and major.isdigit() and int(major) >= 26


def _clean_language(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _resolve_apple_language_values(
    hook_language: Any, apple_language: Any, global_language: Any, env_language: Any, system_language: Any,
) -> Optional[str]:
    """Resolve the documented precedence without describing the fallback as auto-detection."""
    for candidate in (hook_language, apple_language, global_language, env_language, system_language):
        resolved = _clean_language(candidate)
        if resolved:
            return resolved
    return None


def _resolve_apple_language(hook_language: Optional[str], stt_config: Dict[str, Any]) -> Optional[str]:
    apple = stt_config.get("apple") if isinstance(stt_config.get("apple"), dict) else {}
    return _resolve_apple_language_values(
        hook_language, apple.get("language"), stt_config.get("language"),
        # Foundation Locale.current selects the Mac language, unlike Python's POSIX locale.
        os.getenv("HERMES_LOCAL_STT_LANGUAGE"), None,
    )


def _apple_cache_dir() -> Path:
    return get_hermes_home() / "cache" / _APPLE_CACHE_DIRNAME


@contextmanager
def _build_lock(cache_dir: Path) -> Iterator[None]:
    """Serialize profile-local builds; Darwin supplies flock, other hosts never build."""
    import fcntl

    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / ".build.lock"
    with lock_path.open("a+") as lock_file:
        deadline = time.monotonic() + _APPLE_BUILD_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Timed out waiting for the Apple STT helper build")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _run(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    """Bounded, shell-free child process for Xcode and the compiled helper."""
    return subprocess.run(
        argv, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, stdin=subprocess.DEVNULL,
    )


def _xcrun_value(args: list[str]) -> str:
    return _run(["xcrun", "--sdk", "macosx", *args], timeout=15).stdout.strip()


def _helper_cache_key(swiftc: str, sdk_identity: str) -> str:
    source = _APPLE_SOURCE.read_bytes()
    version = _run([swiftc, "--version"], timeout=15).stdout
    return hashlib.sha256(source + b"\0" + sdk_identity.encode() + b"\0" + version.encode()).hexdigest()[:24]


def _build_apple_helper() -> Path:
    """Return a source/SDK-hashed helper, atomically publishing one compiled binary."""
    if not _APPLE_SOURCE.is_file():
        raise RuntimeError("Bundled Apple STT helper source is missing")
    swiftc = _xcrun_value(["--find", "swiftc"])
    sdk_path = _xcrun_value(["--show-sdk-path"])
    if not swiftc or not sdk_path:
        raise RuntimeError("Xcode command-line tools could not locate swiftc or the macOS SDK")
    cache_dir = _apple_cache_dir()
    sdk_build = _xcrun_value(["--show-sdk-build-version"])
    cache_key = _helper_cache_key(swiftc, f"{sdk_path}\0{sdk_build}\0{platform.machine()}")
    helper = cache_dir / f"hermes-apple-stt-{cache_key}"
    if helper.is_file() and os.access(helper, os.X_OK):
        return helper
    with _build_lock(cache_dir):
        if helper.is_file() and os.access(helper, os.X_OK):
            return helper
        fd, temporary_name = tempfile.mkstemp(prefix=f".{helper.name}-", dir=cache_dir)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            _run([
                swiftc, "-O", "-parse-as-library", "-target", f"{platform.machine()}-apple-macosx26.0",
                "-sdk", sdk_path, "-module-cache-path", str(cache_dir / "swift-module-cache"),
                "-framework", "Speech", "-framework", "AVFAudio", str(_APPLE_SOURCE), "-o", str(temporary),
            ], timeout=_APPLE_BUILD_TIMEOUT_SECONDS)
            temporary.chmod(0o700)
            os.replace(temporary, helper)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(f"Apple STT compilation failed (requires Xcode/Command Line Tools 26+): {detail}") from exc
        finally:
            temporary.unlink(missing_ok=True)
    return helper


def _apple_timeout(apple_config: Dict[str, Any]) -> float:
    return max(1.0, min(1800.0, _config_number(
        apple_config, "timeout_seconds", _APPLE_TRANSCRIBE_TIMEOUT_SECONDS, float)))


def _prepare_apple_audio(file_path: str) -> tuple[str, Optional[str], Optional[str]]:
    """Keep AVAudioFile-native inputs intact; transcode only unsupported containers."""
    if Path(file_path).suffix.lower() in _APPLE_NATIVE_FORMATS:
        return file_path, None, None
    from tools.transcription_audio import _find_ffmpeg_binary, _run_quiet

    ffmpeg = _find_ffmpeg_binary()
    if not ffmpeg:
        return file_path, None, "Apple STT needs ffmpeg to convert this audio format, but ffmpeg was not found"
    cleanup_dir = tempfile.mkdtemp(prefix="hermes-apple-stt-")
    converted = str(Path(cleanup_dir) / "audio.wav")
    try:
        _run_quiet([ffmpeg, "-y", "-i", file_path, "-vn", "-ac", "1", "-ar", "16000", converted], timeout=120)
    except subprocess.TimeoutExpired:
        return file_path, cleanup_dir, "Apple STT audio conversion timed out"
    except (subprocess.CalledProcessError, OSError) as exc:
        return file_path, cleanup_dir, f"Apple STT could not convert audio: {exc}"
    return converted, cleanup_dir, None


def _helper_payload(helper: Path, args: list[str], timeout: float) -> Dict[str, Any]:
    try:
        completed = _run([str(helper), *args], timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Apple Speech transcription timed out"}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "error": (exc.stderr or exc.stdout or "Apple Speech helper failed").strip()}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "Apple Speech helper returned malformed JSON"}
    if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
        return {"ok": False, "error": "Apple Speech helper returned an invalid response"}
    return payload


def _transcribe_apple(
    file_path: str, _model_name: str, *, language: Optional[str] = None, prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Transcribe on macOS using SpeechTranscriber; prompts are not part of Apple's API."""
    del prompt
    if not _apple_platform_supported(platform.system(), platform.mac_ver()[0]):
        return _error_result("Apple STT is available only on macOS 26 or later", provider="apple")
    try:
        from tools.transcription_tools import _load_stt_config

        stt_config = _load_stt_config()
        apple_config = stt_config.get("apple") if isinstance(stt_config.get("apple"), dict) else {}
        resolved_language = _resolve_apple_language(language, stt_config)

        prepared, cleanup_dir, preparation_error = _prepare_apple_audio(file_path)
        if preparation_error:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)
            return _error_result(preparation_error, provider="apple")
        try:
            helper = _build_apple_helper()
            args = ["transcribe", "--input", str(Path(prepared).absolute())]
            if resolved_language:
                args.extend(["--language", resolved_language])
            if is_truthy_value(apple_config.get("download_assets", False), default=False):
                args.append("--download-assets")
            payload = _helper_payload(helper, args, _apple_timeout(apple_config))
        finally:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)
        if not payload.get("ok"):
            return _error_result(str(payload.get("error") or "Apple Speech transcription failed"), provider="apple")
        transcript = payload.get("transcript")
        if not isinstance(transcript, str):
            return _error_result("Apple Speech helper returned no transcript", provider="apple")
        return _ok_result(transcript.strip(), "apple")
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return _error_result(f"Apple STT unavailable: {exc}", provider="apple")


def apple_stt_status(language: Optional[str] = None) -> Dict[str, Any]:
    """Non-downloading diagnostics used for a local live check and support triage."""
    if not _apple_platform_supported(platform.system(), platform.mac_ver()[0]):
        return {"ok": False, "error": "Apple STT is available only on macOS 26 or later"}
    try:
        helper = _build_apple_helper()
        args = ["status"]
        if _clean_language(language):
            args.extend(["--language", language.strip()])
        return _helper_payload(helper, args, 30)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": f"Apple STT unavailable: {exc}"}
