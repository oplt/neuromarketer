from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from backend.core.config import settings
from backend.core.logging import get_logger, log_event, log_exception
from backend.schemas.llm_scoring import AnalysisScoringResult

from .llm_evaluators.analysis_scoring import AnalysisScoringPromptBuilder
from .router import LLMRoutePreview, LLMRouter, LLMRoutingError

logger = get_logger(__name__)


class AnalysisScoringServiceError(Exception):
    def __init__(self, message: str, *, telemetry: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.telemetry = telemetry or {}


@dataclass(slots=True)
class AnalysisScoringResponse:
    result: AnalysisScoringResult
    provider_id: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    prompt_version: str
    telemetry: dict[str, Any]


class AnalysisScoringService:
    MODE = "analysis_scoring"
    MIN_OUTPUT_TOKENS = 1200
    MAX_OUTPUT_TOKENS = 2200

    def __init__(self, router: LLMRouter) -> None:
        self.router = router
        self.prompt_builder = AnalysisScoringPromptBuilder()

    @classmethod
    def from_settings(cls) -> AnalysisScoringService:
        return cls(router=LLMRouter.from_settings(settings))

    def preview_route(self) -> LLMRoutePreview:
        return self.router.preview_route(mode=self.MODE)

    def _resolve_max_tokens(self) -> int:
        analysis_specific = int(getattr(settings, "llm_analysis_scoring_max_tokens", 0) or 0)
        global_default = int(getattr(settings, "llm_max_tokens", 0) or 0)

        resolved = analysis_specific if analysis_specific > 0 else global_default
        if resolved <= 0:
            resolved = self.MIN_OUTPUT_TOKENS

        return min(max(resolved, self.MIN_OUTPUT_TOKENS), self.MAX_OUTPUT_TOKENS)

    def _request_options(self) -> dict[str, Any]:
        max_tokens = self._resolve_max_tokens()
        preview = self.preview_route()

        if preview.provider == "ollama":
            return {"num_predict": max_tokens}
        return {"max_tokens": max_tokens}

    async def score(self, context: dict[str, Any]) -> AnalysisScoringResponse:
        if not isinstance(context, dict) or not context:
            raise AnalysisScoringServiceError("Scoring context must be a non-empty dictionary.")

        prompt_payload = self.prompt_builder.build_prompt(context)
        try:
            generation = await self.router.generate_structured(
                mode=self.MODE,
                messages=prompt_payload["messages"],
                response_schema=prompt_payload["response_schema"],
                options=self._request_options(),
            )
        except LLMRoutingError as exc:
            log_exception(
                logger,
                "llm_scoring_failed",
                exc,
                mode=self.MODE,
                provider=exc.telemetry.get("selected_provider"),
                model=exc.telemetry.get("selected_model"),
                route_id=exc.telemetry.get("selected_route_id"),
                raw_text_preview=exc.telemetry.get("last_raw_text_preview"),
                status="failed",
            )
            raise AnalysisScoringServiceError(
                f"LLM scoring failed: {exc}",
                telemetry=exc.telemetry,
            ) from exc

        try:
            validated = AnalysisScoringResult.model_validate(generation.parsed_json)
        except ValidationError as exc:
            log_event(
                logger,
                "llm_scoring_schema_mismatch",
                level="warning",
                provider=generation.metadata.get("provider"),
                model=generation.metadata.get("model"),
                route_id=generation.metadata.get("provider_id"),
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                raw_text_char_count=len(str(generation.metadata.get("raw_text") or "")),
                raw_text_preview=str(generation.metadata.get("raw_text") or "")[:1500],
                status="invalid",
            )
            raise AnalysisScoringServiceError(
                f"Model JSON did not match AnalysisScoringResult schema: {exc}",
                telemetry={
                    "route_id": generation.metadata.get("provider_id"),
                    "provider": generation.metadata.get("provider"),
                    "model": generation.metadata.get("model"),
                    "provider_attempts": generation.metadata.get("provider_attempts") or [],
                    "estimated_cost_usd": generation.metadata.get("estimated_cost_usd"),
                    "actual_cost_usd": generation.metadata.get("actual_cost_usd"),
                    "raw_text_preview": str(generation.metadata.get("raw_text") or "")[:1500],
                },
            ) from exc

        return AnalysisScoringResponse(
            result=validated,
            provider_id=str(
                generation.metadata.get("provider_id") or generation.metadata["provider"]
            ),
            provider=generation.metadata["provider"],
            model=generation.metadata["model"],
            tokens_in=int(generation.metadata["tokens_in"]),
            tokens_out=int(generation.metadata["tokens_out"]),
            prompt_version=self.prompt_builder.prompt_version,
            telemetry={
                "route_id": generation.metadata.get("provider_id"),
                "provider": generation.metadata.get("provider"),
                "model": generation.metadata.get("model"),
                "provider_attempts": generation.metadata.get("provider_attempts") or [],
                "attempts": int(generation.metadata.get("attempts") or 1),
                "fallback_count": int(generation.metadata.get("fallback_count") or 0),
                "latency_ms": int(generation.metadata.get("latency_ms") or 0),
                "estimated_cost_usd": float(generation.metadata.get("estimated_cost_usd") or 0.0),
                "actual_cost_usd": float(generation.metadata.get("actual_cost_usd") or 0.0),
                "budget_usd": generation.metadata.get("budget_usd"),
            },
        )
