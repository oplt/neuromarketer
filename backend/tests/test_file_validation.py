"""Tests for backend.services.file_validation and the MIME-type guard."""

from __future__ import annotations

import io
import unittest

from backend.services.file_validation import validate_file_content
from backend.services.storage import ObjectStorageService

# Minimal valid JPEG magic bytes (FFD8FF)
_JPEG_MAGIC = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 100

# Minimal ELF (Linux executable) magic bytes
_ELF_MAGIC = b"\x7fELF" + b"\x00" * 100

# Plain ASCII text
_TEXT_CONTENT = b"Hello, this is plain text content.\n" * 20


class TestMimeTypeGuard(unittest.TestCase):
    """Unit tests for ObjectStorageService.is_allowed_mime_type."""

    def test_none_is_rejected(self):
        self.assertFalse(ObjectStorageService.is_allowed_mime_type(None))

    def test_empty_string_is_rejected(self):
        self.assertFalse(ObjectStorageService.is_allowed_mime_type(""))

    def test_allowed_video_prefix(self):
        self.assertTrue(ObjectStorageService.is_allowed_mime_type("video/mp4"))

    def test_allowed_audio_prefix(self):
        self.assertTrue(ObjectStorageService.is_allowed_mime_type("audio/mpeg"))

    def test_allowed_image_prefix(self):
        self.assertTrue(ObjectStorageService.is_allowed_mime_type("image/jpeg"))

    def test_allowed_text_prefix(self):
        self.assertTrue(ObjectStorageService.is_allowed_mime_type("text/plain"))

    def test_disallowed_type(self):
        self.assertFalse(ObjectStorageService.is_allowed_mime_type("application/x-executable"))

    def test_disallowed_type_with_valid_prefix_substring(self):
        # "application/vnd.video-something" should NOT match "video/"
        self.assertFalse(
            ObjectStorageService.is_allowed_mime_type("application/vnd.video-something")
        )


class TestFileContentValidation(unittest.TestCase):
    """Unit tests for validate_file_content.

    When python-magic is not installed, validate_file_content returns
    (True, None) — these tests handle that gracefully.
    """

    def _run(self, data: bytes, declared: str | None):
        return validate_file_content(io.BytesIO(data), declared_mime_type=declared)

    def test_file_pointer_reset(self):
        """After validation the file pointer should be at 0."""
        f = io.BytesIO(_TEXT_CONTENT)
        f.read(10)  # advance pointer
        validate_file_content(f, declared_mime_type="text/plain")
        self.assertEqual(f.tell(), 0)

    def test_valid_text_no_declared(self):
        is_valid, detected = self._run(_TEXT_CONTENT, None)
        # Either detected as text/* (valid) or None (magic unavailable)
        self.assertTrue(is_valid)

    def test_valid_text_with_matching_declared(self):
        is_valid, _ = self._run(_TEXT_CONTENT, "text/plain")
        self.assertTrue(is_valid)

    def test_elf_binary_rejected_when_magic_available(self):
        is_valid, detected = self._run(_ELF_MAGIC, "video/mp4")
        # If magic is available the ELF should be blocked.
        # If magic is NOT available, is_valid will be True (graceful degradation).
        if detected is not None:
            self.assertFalse(is_valid)

    def test_cross_family_mismatch_rejected_when_magic_available(self):
        """Declaring video/* but uploading a JPEG image should fail when magic is available."""
        is_valid, detected = self._run(_JPEG_MAGIC, "video/mp4")
        if detected is not None:
            # image/* vs video/* is a cross-family mismatch
            self.assertFalse(is_valid)


if __name__ == "__main__":
    unittest.main()
