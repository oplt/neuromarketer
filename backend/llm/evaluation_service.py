from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from backend.core.config import settings
from backend.core.logging import get_logger, log_event, log_exception
from backend.schemas.evaluators import EvaluationMode, EvaluationResult

from .llm_evaluators.registry import get_evaluator
from .router import LLMRoutePreview, LLMRouter, LLMRoutingError

logger = get_logger(__name__)


class EvaluationServiceError(Exception):
    """Base error for low-level evaluation failures."""

    def __init__(self, message: str, *, telemetry: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.telemetry = telemetry or {}


class UnsupportedEvaluationModeError(EvaluationServiceError):
    """Raised when an invalid evaluation mode is requested."""


class EvaluationContextError(EvaluationServiceError):
    """Raised when the input analysis context is invalid."""


@dataclass(slots=True)
class EvaluationRequest:
    mode: EvaluationMode
    context: dict[str, Any]


@dataclass(slots=True)
class EvaluationResponse:
    result: EvaluationResult
    provider_id: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    prompt_version: str
    telemetry: dict[str, Any]


class EvaluationService:
    def __init__(self, router: LLMRouter) -> None:
        self.router = router
        self._cache: dict[str, tuple[float, EvaluationResponse]] = {}

    @classmethod
    def from_settings(cls) -> EvaluationService:
        return cls(router=LLMRouter.from_settings(settings))

    def preview_route(self, mode: EvaluationMode) -> LLMRoutePreview:
        return self.router.preview_route(mode=mode)

    def _validate_context(self, context: dict[str, Any]) -> None:
        if not isinstance(context, dict):
            raise EvaluationContextError("Evaluation context must be a dictionary.")
        if not context:
            raise EvaluationContextError("Evaluation context must not be empty.")
        required_keys = {"job_metadata", "summary_metrics", "timeline_highlights"}
        missing_keys = [key for key in required_keys if key not in context]
        if missing_keys:
            raise EvaluationContextError(
                f"Evaluation context is missing required keys: {', '.join(sorted(missing_keys))}."
            )

    async def evaluate(self, request: EvaluationRequest) -> EvaluationResponse:
        self._validate_context(request.context)
        try:
            evaluator = get_evaluator(request.mode)
        except ValueError as exc:
            raise UnsupportedEvaluationModeError(str(exc)) from exc

        prompt_payload = evaluator.build_prompt(request.context)
        cache_key = self._build_cache_key(
            mode=request.mode,
            prompt_version=evaluator.prompt_version,
            context=request.context,
        )
        cached_response = self._cache_get(cache_key)
        if cached_response is not None:
            return cached_response
        try:
            generation = await self.router.generate_structured(
                mode=request.mode,
                messages=prompt_payload["messages"],
                response_schema=prompt_payload["response_schema"],
            )
        except LLMRoutingError as exc:
            log_exception(
                logger,
                "llm_evaluation_failed",
                exc,
                mode=request.mode.value,
                provider=exc.telemetry.get("selected_provider"),
                model=exc.telemetry.get("selected_model"),
                route_id=exc.telemetry.get("selected_route_id"),
                status="failed",
            )
            raise EvaluationServiceError(
                f"LLM evaluation failed: {exc}", telemetry=exc.telemetry
            ) from exc

        try:
            validated_result = EvaluationResult.model_validate(generation.parsed_json)
        except ValidationError as exc:
            log_event(
                logger,
                "llm_evaluation_schema_mismatch",
                level="warning",
                mode=request.mode.value,
                provider=generation.metadata.get("provider"),
                model=generation.metadata.get("model"),
                route_id=generation.metadata.get("provider_id"),
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                raw_text_char_count=len(str(generation.metadata.get("raw_text") or "")),
                status="invalid",
            )
            raise EvaluationServiceError(
                f"Model JSON did not match EvaluationResult schema: {exc}",
                telemetry={
                    "route_id": generation.metadata.get("provider_id"),
                    "provider": generation.metadata.get("provider"),
                    "model": generation.metadata.get("model"),
                    "provider_attempts": generation.metadata.get("provider_attempts") or [],
                    "estimated_cost_usd": generation.metadata.get("estimated_cost_usd"),
                    "actual_cost_usd": generation.metadata.get("actual_cost_usd"),
                },
            ) from exc

        normalized_result = validated_result.model_dump(mode="json")
        normalized_result["mode"] = request.mode.value
        normalized_result["model_metadata"] = {
            "provider": generation.metadata["provider"],
            "model": generation.metadata["model"],
            "tokens_in": generation.metadata["tokens_in"],
            "tokens_out": generation.metadata["tokens_out"],
            "provider_id": generation.metadata.get("provider_id"),
            "attempts": generation.metadata.get("attempts"),
            "fallback_count": generation.metadata.get("fallback_count"),
            "latency_ms": generation.metadata.get("latency_ms"),
            "estimated_cost_usd": generation.metadata.get("estimated_cost_usd"),
            "actual_cost_usd": generation.metadata.get("actual_cost_usd"),
            "budget_usd": generation.metadata.get("budget_usd"),
        }

        try:
            final_result = EvaluationResult.model_validate(normalized_result)
        except ValidationError as exc:
            raise EvaluationServiceError(f"Final evaluation normalization failed: {exc}") from exc

        response = EvaluationResponse(
            result=final_result,
            provider_id=str(
                generation.metadata.get("provider_id") or generation.metadata["provider"]
            ),
            provider=generation.metadata["provider"],
            model=generation.metadata["model"],
            tokens_in=int(generation.metadata["tokens_in"]),
            tokens_out=int(generation.metadata["tokens_out"]),
            prompt_version=evaluator.prompt_version,
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
        self._cache_set(cache_key, response)
        return response

    def _build_cache_key(
        self,
        *,
        mode: EvaluationMode,
        prompt_version: str,
        context: dict[str, Any],
    ) -> str:
        preview = self.preview_route(mode)
        normalized_context = json.dumps(context, sort_keys=True, separators=(",", ":"), default=str)
        context_hash = hashlib.sha256(normalized_context.encode("utf-8")).hexdigest()
        key_payload = (
            f"{mode.value}:{prompt_version}:{preview.route_id}:{preview.provider}:"
            f"{preview.model}:{context_hash}"
        )
        return hashlib.sha256(key_payload.encode("utf-8")).hexdigest()

    def _cache_get(self, cache_key: str) -> EvaluationResponse | None:
        ttl_seconds = int(getattr(settings, "llm_evaluation_cache_ttl_seconds", 0) or 0)
        if ttl_seconds <= 0:
            return None
        cached = self._cache.get(cache_key)
        if cached is None:
            return None
        expires_at, response = cached
        if expires_at < time.time():
            self._cache.pop(cache_key, None)
            return None
        return response

    def _cache_set(self, cache_key: str, response: EvaluationResponse) -> None:
        ttl_seconds = int(getattr(settings, "llm_evaluation_cache_ttl_seconds", 0) or 0)
        if ttl_seconds <= 0:
            return
        self._cache[cache_key] = (time.time() + ttl_seconds, response)
