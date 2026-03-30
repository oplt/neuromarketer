from __future__ import annotations

import unittest

from backend.application.services.analysis import AnalysisApplicationService
from backend.core.exceptions import ValidationAppError
from backend.schemas.analysis import AnalysisUploadCreateRequest


class AnalysisApplicationServiceTests(unittest.TestCase):
    def test_validate_payload_rejects_wrong_video_mime_type(self) -> None:
        service = AnalysisApplicationService(session=object())

        with self.assertRaises(ValidationAppError):
            service._validate_payload(
                AnalysisUploadCreateRequest(
                    media_type="video",
                    original_filename="voiceover.mp3",
                    mime_type="audio/mpeg",
                    size_bytes=1_024,
                )
            )

    def test_validate_payload_accepts_plain_text(self) -> None:
        service = AnalysisApplicationService(session=object())

        service._validate_payload(
            AnalysisUploadCreateRequest(
                media_type="text",
                original_filename="script.txt",
                mime_type="text/plain",
                size_bytes=1_024,
            )
        )


if __name__ == "__main__":
    unittest.main()
