from __future__ import annotations

import json
from abc import ABC
from typing import Any

from backend.schemas.evaluators import EvaluationMode, evaluation_json_schema

BASE_SYSTEM_PROMPT = """You are an evidence-bound evaluation engine for media analysis.

Rules:
1. Use only provided structured context as evidence.
2. No invented visuals, transcript text, or performance claims.
3. Keep inferences conservative and traceable to explicit evidence.
4. Keep wording calibrated, concise, and actionable.
5. Keep timestamps in milliseconds and aligned to provided context.
6. If evidence is missing, state limitation explicitly.
7. Return strict JSON only, matching schema exactly.
"""

BASE_DEVELOPER_PROMPT = """Context inputs:
- job metadata, summary metrics, metric rows
- timeline highlights, best/worst segments
- existing recommendations, excerpt text, keyframe hints

Output constraints:
- evidence-only scoring and rationale
- non-redundant strengths/risks
- prioritized recommendations with action + reason
- fill only mode-relevant domain fields
- leave irrelevant domain fields null/empty
- JSON object only, no markdown/commentary
"""


class BaseEvaluator(ABC):
    mode: EvaluationMode
    prompt_version: str = "v2"
    identity: str
    mission: str
    critical_rules: tuple[str, ...]
    evaluation_workflow: tuple[str, ...]
    domain_rubric: tuple[str, ...]
    output_requirements: tuple[str, ...]
    success_criteria: tuple[str, ...]

    def get_response_schema(self) -> dict[str, Any]:
        return evaluation_json_schema(self.mode)

    def normalize_context(self, context: dict[str, Any]) -> dict[str, Any]:
        return context

    def build_domain_prompt(self) -> str:
        sections = [
            f"Identity:\n{self.identity}",
            f"Mission:\n{self.mission}",
            "Critical rules:\n"
            + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(self.critical_rules)),
            "Evaluation workflow:\n"
            + "\n".join(
                f"{index + 1}. {item}" for index, item in enumerate(self.evaluation_workflow)
            ),
            "Domain rubric:\n" + "\n".join(f"- {item}" for item in self.domain_rubric),
            "Output contract:\n" + "\n".join(f"- {item}" for item in self.output_requirements),
            "Success criteria:\n" + "\n".join(f"- {item}" for item in self.success_criteria),
        ]
        return "\n\n".join(sections)

    def build_messages(self, context: dict[str, Any]) -> list[dict[str, str]]:
        normalized = self.normalize_context(context)
        context_json = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))
        user_prompt = (
            f"Active evaluation mode: {self.mode.value}\n"
            f"Prompt version: {self.prompt_version}\n"
            "The structured response schema is provided separately by the caller. "
            "Follow it exactly.\n\n"
            "Structured analysis context:\n"
            f"{context_json}"
        )

        return [
            {"role": "system", "content": BASE_SYSTEM_PROMPT},
            {"role": "system", "content": self.build_domain_prompt()},
            {"role": "system", "content": BASE_DEVELOPER_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    def build_prompt(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "prompt_version": self.prompt_version,
            "response_schema": self.get_response_schema(),
            "messages": self.build_messages(context),
        }
