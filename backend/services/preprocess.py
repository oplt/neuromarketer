from __future__ import annotations

import mimetypes
from dataclasses import dataclass

from backend.services.document_text_extractor import is_supported_text_document
from backend.services.tribe_runtime import TribeRuntime


@dataclass(slots=True)
class PreprocessResult:
    modality: str
    mime_type: str | None
    preprocessing_summary: dict
    extracted_metadata: dict


class PreprocessService:
    """
    MVP-oriented preprocessing service.

    In production:
    - image: Pillow/OpenCV
    - video: ffmpeg frame extraction + audio demux
    - audio: librosa/torchaudio
    - html/url: fetch + sanitize + DOM extract
    - text: tokenizer stats + language detection
    """

    def detect_modality(self, *, filename: str | None, mime_type: str | None) -> str:
        candidate = mime_type
        if not candidate and filename:
            candidate = mimetypes.guess_type(filename)[0]

        if not candidate:
            return "binary"

        if candidate.startswith("image/"):
            return "image"
        if candidate.startswith("video/"):
            return "video"
        if candidate.startswith("audio/"):
            return "audio"
        if is_supported_text_document(candidate, filename):
            return "text"
        if candidate in {"text/html", "application/xhtml+xml"}:
            return "html"
        return "binary"

    async def preprocess_upload(
        self,
        *,
        filename: str | None,
        mime_type: str | None,
        file_size_bytes: int | None,
    ) -> PreprocessResult:
        modality = self.detect_modality(filename=filename, mime_type=mime_type)

        summary = {
            "status": "ready",
            "pipeline_version": "v1",
            "modality": modality,
            "runtime_support": {
                "tribev2": TribeRuntime.modality_support_detail(modality),
            },
        }
        metadata = {
            "filename": filename,
            "mime_type": mime_type,
            "file_size_bytes": file_size_bytes,
        }

        if modality == "image":
            summary["steps"] = ["mime-detect", "image-ingest"]
        elif modality == "video":
            summary["steps"] = ["mime-detect", "video-ingest", "frame-sampling-pending"]
        elif modality == "audio":
            summary["steps"] = ["mime-detect", "audio-ingest"]
        elif modality == "text":
            summary["steps"] = ["mime-detect", "text-ingest"]
        elif modality == "html":
            summary["steps"] = ["mime-detect", "html-ingest"]
        else:
            summary["steps"] = ["mime-detect"]

        return PreprocessResult(
            modality=modality,
            mime_type=mime_type,
            preprocessing_summary=summary,
            extracted_metadata=metadata,
        )
