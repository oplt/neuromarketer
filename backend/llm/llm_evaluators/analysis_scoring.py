from __future__ import annotations

import json
from typing import Any

from backend.schemas.llm_scoring import AnalysisScoringResult


class AnalysisScoringPromptBuilder:
    mode = "analysis_scoring"
    prompt_version = "analysis_scoring_v2"

    def build_prompt(self, context: dict[str, Any]) -> dict[str, Any]:
        context_json = json.dumps(context, ensure_ascii=True, separators=(",", ":"))
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a structured scoring engine inside a media-analysis product. "
                    "You evaluate five product proxies from TRIBE-derived evidence only: "
                    "attention, emotion, memory, cognitive_load, and conversion_proxy."
                ),
            },
            {
                "role": "system",
                "content": (
                    "Rules:\n"
                    "1. Use only the supplied structured context.\n"
                    "2. Do not invent transcript details, visuals, audience reactions, or business outcomes.\n"
                    "3. Treat all five outputs as product proxies grounded in the supplied features, not as clinical facts.\n"
                    "4. Return whole-number scores from 0 to 100.\n"
                    "5. Return confidence values from 0 to 1.\n"
                    "6. Provide concise reasons and evidence tied to supplied segment signals, timing, event density, or region summaries.\n"
                    "7. Return one timeline point per provided segment and preserve segment order. If no segments are provided, return a single point at timestamp 0.\n"
                    "8. Use only these suggestion types: copy, layout, color, cta, framing, pacing, thumbnail, branding.\n"
                    "9. `expected_score_lift_json` may only use the keys attention, emotion, memory, cognitive_load, and conversion_proxy.\n"
                    "10. Return strict JSON only, matching the provided schema exactly."
                ),
            },
            {
                "role": "system",
                "content": (
                    "Scoring guidance:\n"
                    "- attention: immediate capture, focus retention, and salience of the content over time.\n"
                    "- emotion: affective intensity or emotional contrast inferred from the provided signals.\n"
                    "- memory: likelihood of durable recall or retention inferred from coherence and reinforcement cues.\n"
                    "- cognitive_load: processing friction, message density, or decoding effort. Higher means more friction.\n"
                    "- conversion_proxy: likelihood that the content supports a clear next step or persuasive action.\n"
                    "- Base the evaluation on the supplied TRIBE-derived features, segment summaries, and region summaries only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Prompt version: {self.prompt_version}\n"
                    "The response schema is provided separately by the caller. Follow it exactly.\n\n"
                    "Structured scoring context:\n"
                    f"{context_json}"
                ),
            },
        ]
        return {
            "mode": self.mode,
            "prompt_version": self.prompt_version,
            "response_schema": AnalysisScoringResult.model_json_schema(),
            "messages": messages,
        }
