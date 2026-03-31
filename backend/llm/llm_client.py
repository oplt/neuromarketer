from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.core.logging import get_logger, log_event

logger = get_logger(__name__)


class LLMClientError(Exception):
    """Base exception for LLM client failures."""


class LLMTransportError(LLMClientError):
    """Raised when the HTTP request to the LLM provider fails."""


class LLMResponseFormatError(LLMClientError):
    """Raised when the LLM response cannot be parsed into the expected format."""

    def __init__(self, message: str, *, raw_text: str | None = None) -> None:
        super().__init__(message)
        self.raw_text = raw_text


@dataclass(slots=True)
class LLMClientConfig:
    provider: str
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: int = 120
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 2_000
    think: bool | None = None
    default_headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class StructuredGeneration:
    parsed_json: dict[str, Any]
    metadata: dict[str, Any]


def _summarize_error_response(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]

    return response.text.strip()[:500]


def _describe_http_error(exc: httpx.HTTPError) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def _strip_markdown_fences(raw_text: str) -> str:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    return cleaned


def parse_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = _strip_markdown_fences(raw_text)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise LLMResponseFormatError("Model output is not valid JSON.", raw_text=cleaned)
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMResponseFormatError(f"Model output is not valid JSON: {exc}", raw_text=cleaned) from exc

    if not isinstance(parsed, dict):
        raise LLMResponseFormatError("Model output JSON must be an object.", raw_text=cleaned)
    return parsed


class BaseLLMClient(ABC):
    def __init__(self, config: LLMClientConfig):
        self.config = config

    @abstractmethod
    async def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> StructuredGeneration:
        raise NotImplementedError

    async def generate_structured_with_repair(
        self,
        *,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> StructuredGeneration:
        try:
            return await self.generate_structured(
                messages=messages,
                response_schema=response_schema,
                options=options,
            )
        except LLMResponseFormatError as first_exc:
            log_event(
                logger,
                "llm_json_repair_retry",
                level="warning",
                provider=self.config.provider,
                model=self.config.model,
                error_type=first_exc.__class__.__name__,
                error_message=str(first_exc),
                status="retrying",
            )
            repair_content = (
                "Your previous answer was malformed. Return exactly one valid JSON object "
                "that matches the required schema. Do not include markdown, comments, or extra text."
            )
            if first_exc.raw_text:
                repair_content += "\nMalformed JSON to repair:\n" + first_exc.raw_text[:4_000]
            repair_messages = messages + [
                {
                    "role": "user",
                    "content": repair_content,
                }
            ]
            return await self.generate_structured(
                messages=repair_messages,
                response_schema=response_schema,
                options=options,
            )


class OllamaLLMClient(BaseLLMClient):
    def _chat_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/api/chat"

    async def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> StructuredGeneration:
        request_options = {
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "num_predict": self.config.max_tokens,
        }
        request_options.update(options or {})
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "format": response_schema or "json",
            "options": request_options,
        }
        if self.config.think is not None:
            payload["think"] = self.config.think
        headers = {"Accept": "application/json", **self.config.default_headers}

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(self._chat_url(), json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _summarize_error_response(exc.response)
            suffix = f"; response: {detail}" if detail else ""
            raise LLMTransportError(f"Failed to call Ollama endpoint: {_describe_http_error(exc)}{suffix}") from exc
        except httpx.HTTPError as exc:
            raise LLMTransportError(f"Failed to call Ollama endpoint: {_describe_http_error(exc)}") from exc

        try:
            response_json = response.json()
        except ValueError as exc:
            raise LLMResponseFormatError("Ollama response is not valid JSON.") from exc

        message = response_json.get("message")
        if not isinstance(message, dict):
            raise LLMResponseFormatError("Missing or invalid 'message' field in Ollama response.")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseFormatError("Missing or empty Ollama response content.")

        parsed_json = parse_json_object(content)
        metadata = {
            "provider": self.config.provider,
            "model": self.config.model,
            "tokens_in": int(response_json.get("prompt_eval_count") or 0),
            "tokens_out": int(response_json.get("eval_count") or 0),
            "raw_text": content,
        }
        return StructuredGeneration(parsed_json=parsed_json, metadata=metadata)


class OpenAICompatibleLLMClient(BaseLLMClient):
    def _chat_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/chat/completions"

    def _extract_content(self, response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMResponseFormatError("OpenAI-compatible response is missing choices.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise LLMResponseFormatError("OpenAI-compatible response is missing message content.")
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            combined = "".join(text_parts).strip()
            if combined:
                return combined
        raise LLMResponseFormatError("OpenAI-compatible response content is empty.")

    async def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> StructuredGeneration:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        if options:
            payload.update(options)
        _ = response_schema

        headers = {
            "Accept": "application/json",
            **self.config.default_headers,
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(self._chat_url(), json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _summarize_error_response(exc.response)
            suffix = f"; response: {detail}" if detail else ""
            raise LLMTransportError(
                f"Failed to call OpenAI-compatible endpoint: {_describe_http_error(exc)}{suffix}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMTransportError(f"Failed to call OpenAI-compatible endpoint: {_describe_http_error(exc)}") from exc

        try:
            response_json = response.json()
        except ValueError as exc:
            raise LLMResponseFormatError("OpenAI-compatible response is not valid JSON.") from exc

        content = self._extract_content(response_json)
        parsed_json = parse_json_object(content)
        usage = response_json.get("usage") if isinstance(response_json.get("usage"), dict) else {}
        metadata = {
            "provider": self.config.provider,
            "model": self.config.model,
            "tokens_in": int(usage.get("prompt_tokens") or 0),
            "tokens_out": int(usage.get("completion_tokens") or 0),
            "raw_text": content,
        }
        return StructuredGeneration(parsed_json=parsed_json, metadata=metadata)


def create_llm_client(config: LLMClientConfig) -> BaseLLMClient:
    if config.provider == "ollama":
        return OllamaLLMClient(config)
    if config.provider in {"openai_compatible", "vllm", "lm_studio"}:
        return OpenAICompatibleLLMClient(config)
    raise ValueError(f"Unsupported LLM provider '{config.provider}'.")
