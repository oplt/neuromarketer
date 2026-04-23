from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.services.document_text_extractor import (
    DocumentTextExtractor,
    infer_text_document_mime_type,
    is_supported_text_document,
)
from backend.services.preprocess import PreprocessService


class TestTextDocumentSupport(unittest.TestCase):
    def test_infers_mime_type_from_filename(self):
        self.assertEqual(infer_text_document_mime_type("brief.pdf"), "application/pdf")
        self.assertEqual(
            infer_text_document_mime_type("script.docx"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual(infer_text_document_mime_type("notes.md"), "text/markdown")

    def test_supported_text_document_detection_accepts_documents(self):
        self.assertTrue(is_supported_text_document("application/pdf", "brief.pdf"))
        self.assertTrue(
            is_supported_text_document(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "script.docx",
            )
        )
        self.assertTrue(is_supported_text_document(None, "summary.rtf"))
        self.assertFalse(is_supported_text_document("application/octet-stream", "archive.bin"))

    def test_preprocess_detects_document_uploads_as_text(self):
        service = PreprocessService()
        self.assertEqual(
            service.detect_modality(filename="brief.pdf", mime_type="application/pdf"), "text"
        )
        self.assertEqual(
            service.detect_modality(
                filename="script.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "text",
        )


class TestDocumentTextExtractor(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = DocumentTextExtractor()

    def test_extracts_plain_text_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "brief.txt"
            path.write_text("Hello world\n\nThis is the analysis input.", encoding="utf-8")

            result = self.extractor.extract(
                local_path=str(path), mime_type="text/plain", filename=path.name
            )

        self.assertEqual(result.text, "Hello world\n\nThis is the analysis input.")
        self.assertEqual(result.parser, "plain_text")

    def test_extracts_html_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "landing.html"
            path.write_text(
                "<html><body><h1>Headline</h1><p>Primary promise.</p><script>ignored()</script></body></html>",
                encoding="utf-8",
            )

            result = self.extractor.extract(
                local_path=str(path), mime_type="text/html", filename=path.name
            )

        self.assertIn("Headline", result.text)
        self.assertIn("Primary promise.", result.text)
        self.assertNotIn("ignored()", result.text)

    def test_extracts_docx_archives(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "script.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "word/document.xml",
                    (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        "<w:body><w:p><w:r><w:t>Opening line</w:t></w:r></w:p>"
                        "<w:p><w:r><w:t>Call to action</w:t></w:r></w:p></w:body></w:document>"
                    ),
                )

            result = self.extractor.extract(
                local_path=str(path),
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=path.name,
            )

        self.assertIn("Opening line", result.text)
        self.assertIn("Call to action", result.text)
        self.assertEqual(result.parser, "docx_xml")

    def test_extracts_rtf_documents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "brief.rtf"
            path.write_text(
                r"{\rtf1\ansi Hello \b world\b0\par Product narrative}", encoding="utf-8"
            )

            result = self.extractor.extract(
                local_path=str(path), mime_type="application/rtf", filename=path.name
            )

        self.assertIn("Hello world", result.text)
        self.assertIn("Product narrative", result.text)
        self.assertEqual(result.parser, "striprtf")


if __name__ == "__main__":
    unittest.main()
