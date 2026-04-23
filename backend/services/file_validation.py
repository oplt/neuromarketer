from __future__ import annotations

"""Server-side magic-byte file validation.

Uses python-magic (libmagic) to detect the actual content type of uploaded bytes
independently of whatever Content-Type header the client sent.  Only the first
4 KB are read so the file pointer is always reset to 0 before returning.
"""

from typing import BinaryIO

try:
    import magic as _magic

    _MAGIC_AVAILABLE = True
except ImportError:
    _MAGIC_AVAILABLE = False

from backend.core.logging import get_logger

logger = get_logger(__name__)

# Map detected magic MIME types to allowed upload MIME prefixes.
# These are the prefixes configured in settings.allowed_upload_mime_prefixes.
_ALLOWED_MAGIC_PREFIXES: tuple[str, ...] = (
    "image/",
    "video/",
    "audio/",
    "text/",
    "application/json",
    # python-magic may return these for valid text assets
    "application/xml",
)

# Explicitly blocked types regardless of file extension or Content-Type.
_BLOCKED_MAGIC_TYPES: frozenset[str] = frozenset(
    {
        "application/x-executable",
        "application/x-sharedlib",
        "application/x-dosexec",
        "application/x-mach-binary",
        "application/x-elf",
        "application/x-msdownload",
        "application/x-sh",
        "application/x-shellscript",
    }
)

_HEADER_BYTES = 4096


def detect_mime_type(fileobj: BinaryIO) -> str | None:
    """Read the first bytes of *fileobj* and return the detected MIME type.

    The file pointer is always reset to 0 before returning.  Returns ``None``
    when python-magic is not installed (graceful degradation).
    """
    try:
        fileobj.seek(0)
    except Exception:
        pass

    if not _MAGIC_AVAILABLE:
        return None

    try:
        header = fileobj.read(_HEADER_BYTES)
        fileobj.seek(0)
    except Exception:
        try:
            fileobj.seek(0)
        except Exception:
            pass
        return None

    try:
        mime = _magic.from_buffer(header, mime=True)
        return mime
    except Exception as exc:
        logger.warning("magic_detection_failed", exc_info=exc)
        return None


def validate_file_content(
    fileobj: BinaryIO,
    *,
    declared_mime_type: str | None,
) -> tuple[bool, str | None]:
    """Validate file content via magic bytes.

    Returns ``(is_valid, detected_mime_type)``.

    - Always resets the file pointer to 0.
    - If python-magic is unavailable, returns ``(True, None)`` — the MIME
      header check in ObjectStorageService is the last line of defence.
    - Blocks explicitly dangerous content types.
    - Rejects content where the detected type is incompatible with the
      declared type (e.g. an EXE declared as video/mp4).
    """
    detected = detect_mime_type(fileobj)

    if detected is None:
        # python-magic not installed or read failed — degrade gracefully
        return True, None

    if detected in _BLOCKED_MAGIC_TYPES:
        return False, detected

    allowed_by_content = any(detected.startswith(p) for p in _ALLOWED_MAGIC_PREFIXES)
    if not allowed_by_content:
        return False, detected

    # If a declared type was provided, the detected family must match.
    # e.g. declared "video/mp4" but magic says "application/x-executable" → rejected above.
    # We allow minor mismatches (e.g. text/plain vs text/html) but block cross-family mismatches.
    if declared_mime_type:
        declared_family = declared_mime_type.split("/")[0]
        detected_family = detected.split("/")[0]
        # Special case: "application" can legitimately be declared as "text" (JSON, XML, etc.)
        cross_family_ok = {("application", "text"), ("text", "application")}
        if (
            declared_family != detected_family
            and (declared_family, detected_family) not in cross_family_ok
        ):
            return False, detected

    return True, detected
