"""Extract response-embedded images and hide base64 payloads from streamed chat text."""

import base64
import json
import logging
import mimetypes
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE64_IMAGE_MAX_BYTES = 100 * 1024 * 1024
_IMAGE_B64_FIELD_RE = re.compile(
    r'(?P<prefix>"image_base64"\s*:\s*")(?P<data>[A-Za-z0-9+/=\r\n]+)(?P<suffix>")',
    re.DOTALL,
)
_DATA_IMAGE_RE = re.compile(
    r'data:(?P<mime>image/[A-Za-z0-9.+-]+);base64,(?P<data>[A-Za-z0-9+/=\r\n]+)',
    re.DOTALL,
)


def _image_ext_for_mime(mime_type: str) -> str:
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if mime == "image/jpeg":
        return ".jpg"
    guessed = mimetypes.guess_extension(mime) if mime else None
    return guessed or ".png"


def _mime_from_image_bytes(raw: bytes, fallback: str = "image/png") -> str:
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "image/gif"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    return fallback or "image/png"


def _save_response_base64_image(
    b64_data: str,
    *,
    mime_type: str = "image/png",
    filename: str | None = None,
) -> str | None:
    """Decode a response-embedded base64 image into Hermes' image cache.

    Gateway platforms can send files up to their native attachment limits, but
    they cannot send multi-megabyte base64 strings as chat text.  This helper
    moves ``image_base64`` / ``data:image`` payloads back onto disk so the
    normal native media-delivery path can attach them.
    """
    normalized = re.sub(r"\s+", "", b64_data or "")
    if not normalized:
        return None
    # Avoid decoding payloads that cannot fit the intended 100 MB attachment
    # envelope.  Base64 expands by roughly 4/3.
    if (len(normalized) * 3) // 4 > _BASE64_IMAGE_MAX_BYTES:
        logger.warning("Embedded base64 image exceeds %d bytes; skipping", _BASE64_IMAGE_MAX_BYTES)
        return None
    try:
        raw = base64.b64decode(normalized, validate=True)
    except Exception as exc:
        logger.warning("Could not decode embedded base64 image: %s", exc)
        return None
    if not raw:
        return None
    if len(raw) > _BASE64_IMAGE_MAX_BYTES:
        logger.warning("Embedded image exceeds %d bytes after decode; skipping", _BASE64_IMAGE_MAX_BYTES)
        return None
    detected_mime = _mime_from_image_bytes(raw, mime_type)
    if not detected_mime.startswith("image/"):
        logger.warning("Embedded base64 payload is not an image (%s); skipping", detected_mime)
        return None

    safe_name = ""
    if filename:
        safe_name = Path(str(filename)).name
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", safe_name).strip("._")
    from gateway.platforms.base import cache_image_from_bytes
    ext = f"_{safe_name}" if safe_name else _image_ext_for_mime(detected_mime)
    try:
        return cache_image_from_bytes(raw, ext=ext)
    except ValueError as exc:
        logger.warning("Could not cache embedded base64 image: %s", exc)
        return None


def extract_base64_images(content: str) -> tuple[list[str], str]:
    """Extract embedded base64 image payloads into local cache files.

    Handles Hermes API image JSON such as ``image_base64`` + ``mime_type``
    and data URLs such as ``data:image/png;base64,...``.  The returned
    cleaned text redacts the heavy payload so messaging platforms don't try
    to send megabytes of base64 as a chat message.
    """
    if not content or ("image_base64" not in content and "data:image/" not in content):
        return [], content

    paths: list[str] = []
    cleaned = content

    def _json_defaults() -> tuple[str, str | None]:
        mime_type = "image/png"
        filename = None
        try:
            parsed = json.loads(content)
            candidates = parsed if isinstance(parsed, list) else [parsed]
            for item in candidates:
                if not isinstance(item, dict) or "image_base64" not in item:
                    continue
                mime_type = str(
                    item.get("mime_type")
                    or item.get("original_mime_type")
                    or mime_type
                )
                filename = item.get("filename") or filename
                break
        except Exception:
            m = re.search(r'"mime_type"\s*:\s*"([^"]+)"', content)
            if m:
                mime_type = m.group(1)
            f = re.search(r'"filename"\s*:\s*"([^"]+)"', content)
            if f:
                filename = f.group(1)
        return mime_type, str(filename) if filename else None

    default_mime, default_filename = _json_defaults()

    def _replace_image_field(match: re.Match) -> str:
        path = _save_response_base64_image(
            match.group("data"),
            mime_type=default_mime,
            filename=default_filename,
        )
        if path:
            paths.append(path)
        return f'{match.group("prefix")}[omitted; sent as image attachment]{match.group("suffix")}'

    cleaned = _IMAGE_B64_FIELD_RE.sub(_replace_image_field, cleaned)

    def _replace_data_url(match: re.Match) -> str:
        path = _save_response_base64_image(
            match.group("data"),
            mime_type=match.group("mime"),
        )
        if path:
            paths.append(path)
        return f'data:{match.group("mime")};base64,[omitted; sent as image attachment]'

    cleaned = _DATA_IMAGE_RE.sub(_replace_data_url, cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return paths, cleaned


# Streaming sees incomplete payloads; match an empty body and an optional closing quote.
_STREAM_IMAGE_B64_RE = re.compile(
    r'(?P<prefix>"image_base64"\s*:\s*")(?P<data>[A-Za-z0-9+/=\r\n]*)(?P<suffix>"?)', re.DOTALL)
_STREAM_DATA_IMAGE_RE = re.compile(
    r'data:(?P<mime>image/[A-Za-z0-9.+-]+);base64,(?P<data>[A-Za-z0-9+/=\r\n]*)', re.DOTALL)


def redact_base64_images(text: str) -> str:
    """Hide complete and partial image payloads without decoding or writing files."""
    if "image_base64" not in text and "data:image/" not in text:
        return text
    text = _STREAM_IMAGE_B64_RE.sub(
        lambda m: f'{m.group("prefix")}[omitted; sent as image attachment]{m.group("suffix")}', text)
    return _STREAM_DATA_IMAGE_RE.sub(
        lambda m: f'data:{m.group("mime")};base64,[omitted; sent as image attachment]', text)
