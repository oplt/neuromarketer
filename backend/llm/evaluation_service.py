from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.schemas.evaluators import EvaluationMode, EvaluationResult

from .llm_client import (
    BaseLLMClient,
    LLMClientConfig,
    LLMClientError,
    LLMResponseFormatError,
    LLMTransportError,
    create_llm_client,
)
from .llm_evaluators.registry import get_evaluator

logger = get_logger(__name__)


class EvaluationServiceError(Exception):
    """Base error for low-level evaluation failures."""


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
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    prompt_version: str


class EvaluationService:
    def __init__(self, llm_client: BaseLLMClient) -> None:
        self.llm_client = llm_client

    @classmethod
    def from_settings(cls) -> "EvaluationService":
        config = LLMClientConfig(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            max_tokens=settings.llm_max_tokens,
        )
        return cls(llm_client=create_llm_client(config))

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
        try:
            generation = await self.llm_client.generate_structured_with_repair(
                messages=prompt_payload["messages"],
                response_schema=prompt_payload["response_schema"],
            )
        except (LLMTransportError, LLMResponseFormatError, LLMClientError) as exc:
            logger.exception(
                "LLM evaluation transport/format failure.",
                extra={
                    "event": "llm_evaluation_failed",
                    "extra_fields": {
                        "mode": request.mode.value,
                        "provider": self.llm_client.config.provider,
                        "model": self.llm_client.config.model,
                        "error": str(exc),
                    },
                },
            )
            raise EvaluationServiceError(f"LLM evaluation failed: {exc}") from exc

        try:
            validated_result = EvaluationResult.model_validate(generation.parsed_json)
        except ValidationError as exc:
            logger.warning(
                "LLM evaluation JSON failed schema validation.",
                extra={
                    "event": "llm_evaluation_schema_mismatch",
                    "extra_fields": {
                        "mode": request.mode.value,
                        "provider": self.llm_client.config.provider,
                        "model": self.llm_client.config.model,
                        "error": str(exc),
                        "raw_text": generation.metadata.get("raw_text", "")[:2_000],
                    },
                },
            )
            raise EvaluationServiceError(f"Model JSON did not match EvaluationResult schema: {exc}") from exc

        normalized_result = validated_result.model_dump(mode="json")
        normalized_result["mode"] = request.mode.value
        normalized_result["model_metadata"] = {
            "provider": generation.metadata["provider"],
            "model": generation.metadata["model"],
            "tokens_in": generation.metadata["tokens_in"],
            "tokens_out": generation.metadata["tokens_out"],
        }

        try:
            final_result = EvaluationResult.model_validate(normalized_result)
        except ValidationError as exc:
            raise EvaluationServiceError(f"Final evaluation normalization failed: {exc}") from exc

        return EvaluationResponse(
            result=final_result,
            provider=generation.metadata["provider"],
            model=generation.metadata["model"],
            tokens_in=int(generation.metadata["tokens_in"]),
            tokens_out=int(generation.metadata["tokens_out"]),
            prompt_version=evaluator.prompt_version,
        )
