from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class TextPreprocessResult:
    modality: str
    normalized_text: str
    token_count_estimate: int
    sentence_count_estimate: int
    preprocessing_summary: dict
    extracted_metadata: dict


class TextPreprocessService:
    def normalize(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def estimate_sentence_count(self, text: str) -> int:
        if not text:
            return 0
        parts = re.split(r"[.!?]+", text)
        return len([p for p in parts if p.strip()])

    def estimate_token_count(self, text: str) -> int:
        if not text:
            return 0
        # Rough approximation for MVP use
        return max(1, int(len(text.split()) * 1.3))

    def preprocess(self, text: str) -> TextPreprocessResult:
        normalized = self.normalize(text)
        token_count_estimate = self.estimate_token_count(normalized)
        sentence_count_estimate = self.estimate_sentence_count(normalized)

        return TextPreprocessResult(
            modality="text",
            normalized_text=normalized,
            token_count_estimate=token_count_estimate,
            sentence_count_estimate=sentence_count_estimate,
            preprocessing_summary={
                "status": "ready",
                "pipeline_version": "text_v1",
                "normalized": True,
            },
            extracted_metadata={
                "character_count": len(normalized),
                "token_count_estimate": token_count_estimate,
                "sentence_count_estimate": sentence_count_estimate,
            },
        )