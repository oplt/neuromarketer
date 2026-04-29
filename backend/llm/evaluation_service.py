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

        normalized_result = self._normalize_generation_payload(
            raw_payload=generation.parsed_json,
            mode=request.mode,
            metadata=generation.metadata,
        )

        try:
            validated_result = EvaluationResult.model_validate(normalized_result)
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

    def _normalize_generation_payload(
        self,
        *,
        raw_payload: Any,
        mode: EvaluationMode,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
        summary = self._first_text(
            payload,
            [
                "summary",
                f"{mode.value}_summary",
                "educational_summary",
                "defence_summary",
                "marketing_summary",
                "social_summary",
            ],
            fallback=f"{mode.value.replace('_', ' ').title()} evaluation completed.",
        )

        normalized = {
            **payload,
            "mode": mode.value,
            "overall_verdict": self._first_text(
                payload,
                ["overall_verdict", "verdict", "headline", "judgement", "judgment"],
                fallback=summary[:240],
            ),
            "summary": summary,
            "scores": self._normalize_scores(payload.get("scores") or payload.get("score")),
            "scorecard": self._normalize_scorecard(payload.get("scorecard")),
            "strengths": self._normalize_text_list(payload.get("strengths")),
            "weaknesses": self._normalize_text_list(payload.get("weaknesses")),
            "risks": self._normalize_risks(payload.get("risks")),
            "recommendations": self._normalize_recommendations(payload.get("recommendations")),
            "model_metadata": self._build_model_metadata(metadata),
        }
        return normalized

    def _build_model_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": str(metadata.get("provider") or "unknown"),
            "model": str(metadata.get("model") or "unknown"),
            "tokens_in": self._coerce_non_negative_int(metadata.get("tokens_in")),
            "tokens_out": self._coerce_non_negative_int(metadata.get("tokens_out")),
            "provider_id": metadata.get("provider_id"),
            "attempts": metadata.get("attempts"),
            "fallback_count": metadata.get("fallback_count"),
            "latency_ms": metadata.get("latency_ms"),
            "estimated_cost_usd": metadata.get("estimated_cost_usd"),
            "actual_cost_usd": metadata.get("actual_cost_usd"),
            "budget_usd": metadata.get("budget_usd"),
        }

    def _normalize_scores(self, value: Any) -> dict[str, int]:
        source = value if isinstance(value, dict) else {}
        return {
            "clarity": self._coerce_score(source.get("clarity"), fallback=50),
            "engagement": self._coerce_score(source.get("engagement"), fallback=50),
            "retention": self._coerce_score(source.get("retention"), fallback=50),
            "fit_for_purpose": self._coerce_score(
                source.get("fit_for_purpose") or source.get("fit"), fallback=50
            ),
            "risk": self._coerce_score(source.get("risk"), fallback=50),
        }

    def _normalize_scorecard(self, value: Any) -> dict[str, dict[str, Any]]:
        source = value if isinstance(value, dict) else {}
        return {
            "hook_or_opening": self._normalize_score_reason(
                source.get("hook_or_opening") or source.get("hook"), "Opening evidence was limited."
            ),
            "message_clarity": self._normalize_score_reason(
                source.get("message_clarity") or source.get("clarity"),
                "Message clarity evidence was limited.",
            ),
            "pacing": self._normalize_score_reason(
                source.get("pacing"),
                "Pacing evidence was limited.",
            ),
            "attention_alignment": self._normalize_score_reason(
                source.get("attention_alignment"), "Attention-alignment evidence was limited."
            ),
            "domain_effectiveness": self._normalize_score_reason(
                source.get("domain_effectiveness") or source.get("fit_for_purpose"),
                "Domain effectiveness evidence was limited.",
            ),
        }

    def _normalize_score_reason(self, value: Any, fallback_reason: str) -> dict[str, Any]:
        if isinstance(value, dict):
            return {
                "score": self._coerce_score(value.get("score"), fallback=50),
                "reason": self._coerce_text(value.get("reason"), fallback=fallback_reason),
            }
        return {
            "score": self._coerce_score(value, fallback=50),
            "reason": fallback_reason,
        }

    def _normalize_text_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:800] for item in value if str(item).strip()][:8]

    def _normalize_risks(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in value[:8]:
            if isinstance(item, dict):
                severity = (
                    item.get("severity")
                    if item.get("severity") in {"low", "medium", "high"}
                    else "medium"
                )
                normalized.append(
                    {
                        "severity": severity,
                        "label": self._coerce_text(
                            item.get("label"), fallback="Evaluation risk"
                        )[:160],
                        "description": self._coerce_text(
                            item.get("description"), fallback="Risk detail was limited."
                        ),
                        "timestamp_start": item.get("timestamp_start"),
                        "timestamp_end": item.get("timestamp_end"),
                    }
                )
            elif str(item).strip():
                normalized.append(
                    {
                        "severity": "medium",
                        "label": str(item).strip()[:160],
                        "description": str(item).strip()[:1000],
                    }
                )
        return normalized

    def _normalize_recommendations(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in value[:8]:
            if isinstance(item, dict):
                priority = (
                    item.get("priority")
                    if item.get("priority") in {"low", "medium", "high"}
                    else "medium"
                )
                normalized.append(
                    {
                        "priority": priority,
                        "action": self._coerce_text(
                            item.get("action"), fallback="Review the asset."
                        ),
                        "reason": self._coerce_text(
                            item.get("reason"), fallback="Evidence was limited."
                        ),
                        "timestamp_start": item.get("timestamp_start"),
                        "timestamp_end": item.get("timestamp_end"),
                    }
                )
            elif str(item).strip():
                normalized.append(
                    {
                        "priority": "medium",
                        "action": str(item).strip()[:300],
                        "reason": "Recommended by the evaluation model.",
                    }
                )
        return normalized

    def _first_text(self, payload: dict[str, Any], keys: list[str], *, fallback: str) -> str:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return fallback

    def _coerce_text(self, value: Any, *, fallback: str) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()[:1000]
        return fallback

    def _coerce_score(self, value: Any, *, fallback: int) -> int:
        if isinstance(value, dict):
            value = value.get("score")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return fallback
        if numeric <= 1:
            numeric *= 100
        return max(0, min(100, round(numeric)))

    def _coerce_non_negative_int(self, value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

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
