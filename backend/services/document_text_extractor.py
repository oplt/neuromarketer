from __future__ import annotations

import mimetypes
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from backend.core.exceptions import DependencyAppError, ValidationAppError

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - exercised when deps are missing in runtime
    PdfReader = None

try:
    from striprtf.striprtf import rtf_to_text
except ImportError:  # pragma: no cover - exercised when deps are missing in runtime
    rtf_to_text = None

_CUSTOM_TEXT_DOCUMENT_MIME_TYPES = {
    ".csv": "text/csv",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".htm": "text/html",
    ".html": "text/html",
    ".json": "application/json",
    ".markdown": "text/markdown",
    ".md": "text/markdown",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".pdf": "application/pdf",
    ".rtf": "application/rtf",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".xml": "application/xml",
}

PLAIN_TEXT_MIME_TYPES = frozenset(
    {
        "application/json",
        "text/csv",
        "text/markdown",
        "text/plain",
        "text/tab-separated-values",
    }
)
HTML_MIME_TYPES = frozenset({"text/html"})
XML_MIME_TYPES = frozenset({"application/xml", "text/xml"})
PDF_MIME_TYPES = frozenset({"application/pdf"})
DOC_MIME_TYPES = frozenset({"application/msword"})
DOCX_MIME_TYPES = frozenset(
    {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
)
ODT_MIME_TYPES = frozenset({"application/vnd.oasis.opendocument.text"})
RTF_MIME_TYPES = frozenset({"application/rtf", "text/rtf"})

DEFAULT_ANALYSIS_ALLOWED_TEXT_MIME_TYPES = list(
    dict.fromkeys(
        [
            "text/plain",
            "text/markdown",
            "text/csv",
            "text/tab-separated-values",
            "application/json",
            "text/html",
            "application/xml",
            "text/xml",
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.oasis.opendocument.text",
            "application/rtf",
            "text/rtf",
        ]
    )
)
SUPPORTED_TEXT_DOCUMENT_MIME_TYPES = frozenset(DEFAULT_ANALYSIS_ALLOWED_TEXT_MIME_TYPES)

_DOCX_TEXT_MEMBERS = (
    "word/document.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
)


def infer_text_document_mime_type(filename: str | None) -> str | None:
    if not filename:
        return None
    suffix = Path(filename).suffix.lower()
    if suffix in _CUSTOM_TEXT_DOCUMENT_MIME_TYPES:
        return _CUSTOM_TEXT_DOCUMENT_MIME_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed


def resolve_text_document_mime_type(mime_type: str | None, filename: str | None) -> str | None:
    return mime_type or infer_text_document_mime_type(filename)


def is_supported_text_document(mime_type: str | None, filename: str | None = None) -> bool:
    resolved = resolve_text_document_mime_type(mime_type, filename)
    return resolved in SUPPORTED_TEXT_DOCUMENT_MIME_TYPES


@dataclass(slots=True)
class ExtractedDocumentText:
    text: str
    parser: str
    mime_type: str | None
    character_count: int
    line_count: int


class _HtmlTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if normalized_tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
            return
        if normalized_tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._ignored_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


class DocumentTextExtractor:
    def extract(
        self,
        *,
        local_path: str,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> ExtractedDocumentText:
        path = Path(local_path)
        if not path.exists():
            raise ValidationAppError(f"Document not found: {path}")

        resolved_mime_type = resolve_text_document_mime_type(mime_type, filename or path.name)
        if not is_supported_text_document(resolved_mime_type, filename or path.name):
            raise ValidationAppError(
                f"Unsupported text document type: {resolved_mime_type or infer_text_document_mime_type(path.name) or 'unknown'}"
            )

        if resolved_mime_type in PDF_MIME_TYPES:
            text = self._extract_pdf(path)
            parser = "pypdf"
        elif resolved_mime_type in DOC_MIME_TYPES:
            text, parser = self._extract_doc(path)
        elif resolved_mime_type in DOCX_MIME_TYPES:
            text = self._extract_docx(path)
            parser = "docx_xml"
        elif resolved_mime_type in ODT_MIME_TYPES:
            text = self._extract_odt(path)
            parser = "odt_xml"
        elif resolved_mime_type in RTF_MIME_TYPES:
            text = self._extract_rtf(path)
            parser = "striprtf"
        elif resolved_mime_type in HTML_MIME_TYPES:
            text = self._extract_html(path)
            parser = "html_parser"
        elif resolved_mime_type in XML_MIME_TYPES:
            text = self._extract_xml(path)
            parser = "xml_parser"
        else:
            text = self._extract_plain_text(path)
            parser = "plain_text"

        normalized_text = self._normalize_text(text)
        if not normalized_text:
            raise ValidationAppError(
                "No readable text could be extracted from the uploaded document. "
                "If this is a scanned PDF or image-based document, convert it to selectable text first."
            )

        return ExtractedDocumentText(
            text=normalized_text,
            parser=parser,
            mime_type=resolved_mime_type,
            character_count=len(normalized_text),
            line_count=normalized_text.count("\n") + 1,
        )

    def _extract_plain_text(self, path: Path) -> str:
        raw_bytes = path.read_bytes()
        return self._decode_text_bytes(raw_bytes)

    def _extract_html(self, path: Path) -> str:
        parser = _HtmlTextExtractor()
        parser.feed(self._decode_text_bytes(path.read_bytes()))
        parser.close()
        return parser.get_text()

    def _extract_xml(self, path: Path) -> str:
        try:
            root = ElementTree.fromstring(path.read_bytes())
        except ElementTree.ParseError as exc:
            raise ValidationAppError("The uploaded XML document could not be parsed.") from exc
        return "\n".join(fragment.strip() for fragment in root.itertext() if fragment.strip())

    def _extract_pdf(self, path: Path) -> str:
        if PdfReader is None:
            raise DependencyAppError("PDF extraction requires the `pypdf` package on the server.")

        try:
            reader = PdfReader(str(path))
        except Exception as exc:  # pragma: no cover - library-specific failure path
            raise ValidationAppError(
                "The uploaded PDF could not be opened for text extraction."
            ) from exc

        return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    def _extract_docx(self, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                members = [
                    member
                    for member in archive.namelist()
                    if member in _DOCX_TEXT_MEMBERS
                    or member.startswith("word/header")
                    or member.startswith("word/footer")
                ]
                fragments = [self._extract_xml_fragment(archive.read(member)) for member in members]
        except zipfile.BadZipFile as exc:
            raise ValidationAppError(
                "The uploaded DOCX document is not a valid Office archive."
            ) from exc

        return "\n\n".join(fragment for fragment in fragments if fragment)

    def _extract_odt(self, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                content_xml = archive.read("content.xml")
        except KeyError as exc:
            raise ValidationAppError(
                "The uploaded ODT document does not contain a readable content.xml file."
            ) from exc
        except zipfile.BadZipFile as exc:
            raise ValidationAppError(
                "The uploaded ODT document is not a valid OpenDocument archive."
            ) from exc

        return self._extract_xml_fragment(content_xml)

    def _extract_rtf(self, path: Path) -> str:
        if rtf_to_text is None:
            raise DependencyAppError(
                "RTF extraction requires the `striprtf` package on the server."
            )
        return rtf_to_text(self._decode_text_bytes(path.read_bytes()))

    def _extract_doc(self, path: Path) -> tuple[str, str]:
        antiword_binary = shutil.which("antiword")
        if antiword_binary:
            completed = subprocess.run(
                [antiword_binary, str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.stdout.strip():
                return completed.stdout, "antiword"

        soffice_binary = shutil.which("soffice")
        if soffice_binary:
            return self._extract_via_soffice(path, soffice_binary), "libreoffice"

        raise DependencyAppError(
            "Legacy DOC extraction requires `antiword` or LibreOffice on the server."
        )

    def _extract_via_soffice(self, path: Path, soffice_binary: str) -> str:
        with tempfile.TemporaryDirectory(prefix="doc_extract_") as temp_dir:
            temp_root = Path(temp_dir)
            out_dir = temp_root / "out"
            out_dir.mkdir(parents=True, exist_ok=True)
            profile_dir = temp_root / "profile"
            profile_dir.mkdir(parents=True, exist_ok=True)

            completed = subprocess.run(
                [
                    soffice_binary,
                    "--headless",
                    f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
                    "--convert-to",
                    "txt:Text",
                    "--outdir",
                    str(out_dir),
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise ValidationAppError(
                    "LibreOffice could not convert the uploaded DOC document to text."
                )

            converted_files = sorted(out_dir.glob("*.txt"))
            if not converted_files:
                raise ValidationAppError(
                    "LibreOffice did not produce a readable text export for the DOC document."
                )
            return converted_files[0].read_text(encoding="utf-8", errors="ignore")

    def _extract_xml_fragment(self, raw_bytes: bytes) -> str:
        try:
            root = ElementTree.fromstring(raw_bytes)
        except ElementTree.ParseError as exc:
            raise ValidationAppError(
                "The uploaded document contains malformed XML content."
            ) from exc
        return "\n".join(fragment.strip() for fragment in root.itertext() if fragment.strip())

    def _decode_text_bytes(self, raw_bytes: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-16", "utf-16le", "utf-16be"):
            try:
                return raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode("utf-8", errors="ignore")

    def _normalize_text(self, value: str) -> str:
        normalized = value.replace("\x00", "")
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]+\n", "\n", normalized)
        normalized = re.sub(r"[ \t]{2,}", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()
