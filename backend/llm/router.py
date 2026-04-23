from __future__ import annotations

import asyncio
import copy
import math
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from backend.core.config import Settings, settings
from backend.core.logging import get_logger, log_event
from backend.core.metrics import metrics
from backend.schemas.evaluators import EvaluationMode

from .llm_client import (
    BaseLLMClient,
    LLMClientConfig,
    LLMClientError,
    LLMResponseFormatError,
    LLMTransportError,
    StructuredGeneration,
    create_llm_client,
)

logger = get_logger(__name__)

ModeKey = EvaluationMode | str


class LLMRoutingError(Exception):
    def __init__(self, message: str, *, telemetry: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.telemetry = telemetry or {}


@dataclass(slots=True)
class LLMRouteConfig:
    route_id: str
    provider: str
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: int = 120
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 2_000
    think: bool | None = None
    request_budget_usd: float | None = None
    max_attempts: int = 2
    retry_backoff_seconds: float = 1.0
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_reset_seconds: int = 300
    cost_input_per_1k_tokens: float = 0.0
    cost_output_per_1k_tokens: float = 0.0
    default_headers: dict[str, str] = field(default_factory=dict)

    def build_client(self) -> BaseLLMClient:
        return create_llm_client(
            LLMClientConfig(
                provider_id=self.route_id,
                provider=self.provider,
                base_url=self.base_url,
                model=self.model,
                api_key=self.api_key,
                timeout_seconds=self.timeout_seconds,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                think=self.think,
                default_headers=self.default_headers,
            )
        )

    def estimate_cost_usd(self, *, tokens_in: int, tokens_out: int) -> float:
        return round(
            (max(tokens_in, 0) / 1_000.0) * self.cost_input_per_1k_tokens
            + (max(tokens_out, 0) / 1_000.0) * self.cost_output_per_1k_tokens,
            6,
        )


@dataclass(slots=True)
class LLMRoutePreview:
    route_id: str
    provider: str
    model: str
    candidate_order: list[str]


@dataclass(slots=True)
class _CircuitState:
    consecutive_failures: int = 0
    opened_until_monotonic: float | None = None


class _CircuitBreakerRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._states: dict[str, _CircuitState] = {}

    def is_open(self, route_id: str) -> bool:
        with self._lock:
            state = self._states.get(route_id)
            if state is None or state.opened_until_monotonic is None:
                return False
            if state.opened_until_monotonic <= time.monotonic():
                state.opened_until_monotonic = None
                state.consecutive_failures = 0
                return False
            return True

    def snapshot(self, route_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._states.get(route_id) or _CircuitState()
            is_open = (
                state.opened_until_monotonic is not None
                and state.opened_until_monotonic > time.monotonic()
            )
            remaining_seconds = (
                max(state.opened_until_monotonic - time.monotonic(), 0.0)
                if is_open and state.opened_until_monotonic is not None
                else 0.0
            )
            return {
                "is_open": is_open,
                "consecutive_failures": state.consecutive_failures,
                "retry_after_seconds": round(remaining_seconds, 2),
            }

    def record_success(self, route_id: str) -> None:
        with self._lock:
            state = self._states.setdefault(route_id, _CircuitState())
            state.consecutive_failures = 0
            state.opened_until_monotonic = None

    def record_failure(self, route_id: str, *, threshold: int, reset_seconds: int) -> bool:
        with self._lock:
            state = self._states.setdefault(route_id, _CircuitState())
            state.consecutive_failures += 1
            if state.consecutive_failures >= max(threshold, 1):
                state.opened_until_monotonic = time.monotonic() + max(reset_seconds, 1)
                return True
            return False


_circuit_breakers = _CircuitBreakerRegistry()


class LLMRouter:
    def __init__(
        self,
        *,
        routes: list[LLMRouteConfig],
        mode_preferences: dict[str, list[str]] | None = None,
        mode_budgets: dict[str, float] | None = None,
    ) -> None:
        if not routes:
            raise ValueError("At least one LLM route is required.")
        self.routes = {route.route_id: route for route in routes}
        self.clients = {route.route_id: route.build_client() for route in routes}
        self.route_order = [route.route_id for route in routes]
        self.mode_preferences = {
            key: [str(item) for item in value if str(item) in self.routes]
            for key, value in (mode_preferences or {}).items()
            if isinstance(value, list)
        }
        self.mode_budgets = {key: float(value) for key, value in (mode_budgets or {}).items()}

    @classmethod
    def from_settings(cls, app_settings: Settings = settings) -> LLMRouter:
        routes: list[LLMRouteConfig] = []
        raw_routes = app_settings.llm_router_providers_json or []
        if not raw_routes:
            routes.append(
                LLMRouteConfig(
                    route_id="primary",
                    provider=app_settings.llm_provider,
                    base_url=app_settings.llm_base_url,
                    model=app_settings.llm_model,
                    api_key=app_settings.llm_api_key,
                    timeout_seconds=app_settings.llm_timeout_seconds,
                    temperature=app_settings.llm_temperature,
                    top_p=app_settings.llm_top_p,
                    max_tokens=app_settings.llm_max_tokens,
                    think=app_settings.llm_ollama_think,
                    request_budget_usd=app_settings.llm_request_budget_usd,
                    max_attempts=app_settings.llm_retry_max_attempts,
                    retry_backoff_seconds=app_settings.llm_retry_backoff_seconds,
                    circuit_breaker_failure_threshold=app_settings.llm_circuit_breaker_failure_threshold,
                    circuit_breaker_reset_seconds=app_settings.llm_circuit_breaker_reset_seconds,
                    cost_input_per_1k_tokens=app_settings.llm_cost_input_per_1k_tokens,
                    cost_output_per_1k_tokens=app_settings.llm_cost_output_per_1k_tokens,
                )
            )
        else:
            for index, raw_route in enumerate(raw_routes):
                route_id = str(
                    raw_route.get("id") or raw_route.get("route_id") or f"route_{index + 1}"
                ).strip()
                provider = str(raw_route.get("provider") or app_settings.llm_provider).strip()
                base_url = str(raw_route.get("base_url") or app_settings.llm_base_url).strip()
                model = str(raw_route.get("model") or app_settings.llm_model).strip()
                if not route_id or not provider or not base_url or not model:
                    continue
                routes.append(
                    LLMRouteConfig(
                        route_id=route_id,
                        provider=provider,
                        base_url=base_url,
                        model=model,
                        api_key=cast_or_none(raw_route.get("api_key")) or app_settings.llm_api_key,
                        timeout_seconds=int(
                            raw_route.get("timeout_seconds") or app_settings.llm_timeout_seconds
                        ),
                        temperature=float(
                            raw_route.get("temperature") or app_settings.llm_temperature
                        ),
                        top_p=float(raw_route.get("top_p") or app_settings.llm_top_p),
                        max_tokens=int(raw_route.get("max_tokens") or app_settings.llm_max_tokens),
                        think=raw_route.get("think", app_settings.llm_ollama_think),
                        request_budget_usd=_float_or_none(
                            raw_route.get("request_budget_usd"),
                            fallback=app_settings.llm_request_budget_usd,
                        ),
                        max_attempts=int(
                            raw_route.get("max_attempts") or app_settings.llm_retry_max_attempts
                        ),
                        retry_backoff_seconds=float(
                            raw_route.get("retry_backoff_seconds")
                            or app_settings.llm_retry_backoff_seconds
                        ),
                        circuit_breaker_failure_threshold=int(
                            raw_route.get("circuit_breaker_failure_threshold")
                            or app_settings.llm_circuit_breaker_failure_threshold
                        ),
                        circuit_breaker_reset_seconds=int(
                            raw_route.get("circuit_breaker_reset_seconds")
                            or app_settings.llm_circuit_breaker_reset_seconds
                        ),
                        cost_input_per_1k_tokens=float(
                            raw_route.get("cost_input_per_1k_tokens")
                            or app_settings.llm_cost_input_per_1k_tokens
                        ),
                        cost_output_per_1k_tokens=float(
                            raw_route.get("cost_output_per_1k_tokens")
                            or app_settings.llm_cost_output_per_1k_tokens
                        ),
                    )
                )
        if not routes:
            routes.append(
                LLMRouteConfig(
                    route_id="primary",
                    provider=app_settings.llm_provider,
                    base_url=app_settings.llm_base_url,
                    model=app_settings.llm_model,
                    api_key=app_settings.llm_api_key,
                    timeout_seconds=app_settings.llm_timeout_seconds,
                    temperature=app_settings.llm_temperature,
                    top_p=app_settings.llm_top_p,
                    max_tokens=app_settings.llm_max_tokens,
                    think=app_settings.llm_ollama_think,
                    request_budget_usd=app_settings.llm_request_budget_usd,
                    max_attempts=app_settings.llm_retry_max_attempts,
                    retry_backoff_seconds=app_settings.llm_retry_backoff_seconds,
                    circuit_breaker_failure_threshold=app_settings.llm_circuit_breaker_failure_threshold,
                    circuit_breaker_reset_seconds=app_settings.llm_circuit_breaker_reset_seconds,
                    cost_input_per_1k_tokens=app_settings.llm_cost_input_per_1k_tokens,
                    cost_output_per_1k_tokens=app_settings.llm_cost_output_per_1k_tokens,
                )
            )

        return cls(
            routes=routes,
            mode_preferences=app_settings.llm_routing_modes_json,
            mode_budgets={
                key: float(value)
                for key, value in app_settings.llm_mode_request_budgets_json.items()
            },
        )

    def preview_route(self, *, mode: ModeKey) -> LLMRoutePreview:
        candidate_order = self._candidate_order(mode)
        for route_id in candidate_order:
            if _circuit_breakers.is_open(route_id):
                continue
            route = self.routes[route_id]
            return LLMRoutePreview(
                route_id=route.route_id,
                provider=route.provider,
                model=route.model,
                candidate_order=candidate_order,
            )
        fallback_id = candidate_order[0]
        fallback = self.routes[fallback_id]
        return LLMRoutePreview(
            route_id=fallback.route_id,
            provider=fallback.provider,
            model=fallback.model,
            candidate_order=candidate_order,
        )

    def _request_options_for_attempt(
        self,
        *,
        route: LLMRouteConfig,
        options: dict[str, Any] | None,
        attempt: int,
    ) -> dict[str, Any]:
        resolved = copy.deepcopy(options or {})

        token_key: str | None = None
        if "num_predict" in resolved:
            token_key = "num_predict"
        elif "max_tokens" in resolved:
            token_key = "max_tokens"

        if token_key is None:
            return resolved

        base_value = int(resolved.get(token_key) or 0)
        if base_value <= 0:
            base_value = route.max_tokens

        # Retry with a materially larger cap so malformed/truncated JSON
        # does not repeat with the same output limit.
        retry_floor = 1200
        scaled_value = (
            base_value if attempt == 1 else max(base_value * (2 ** (attempt - 1)), retry_floor)
        )
        resolved[token_key] = max(scaled_value, base_value)
        return resolved

    async def generate_structured(
        self,
        *,
        mode: ModeKey,
        messages: list[dict[str, str]],
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> StructuredGeneration:
        mode_key = _mode_key(mode)
        candidate_order = self._candidate_order(mode)
        estimated_prompt_tokens = estimate_prompt_tokens(messages)
        budget_usd = self._resolve_budget(mode)
        telemetry: dict[str, Any] = {
            "mode": mode_key,
            "candidate_order": candidate_order,
            "estimated_prompt_tokens": estimated_prompt_tokens,
            "budget_usd": budget_usd,
            "provider_attempts": [],
        }
        last_error: str | None = None

        for fallback_index, route_id in enumerate(candidate_order):
            route = self.routes[route_id]
            circuit_state = _circuit_breakers.snapshot(route_id)
            route_budget = budget_usd if budget_usd is not None else route.request_budget_usd
            estimated_cost = route.estimate_cost_usd(
                tokens_in=estimated_prompt_tokens,
                tokens_out=route.max_tokens,
            )
            if circuit_state["is_open"]:
                telemetry["provider_attempts"].append(
                    {
                        "route_id": route.route_id,
                        "provider": route.provider,
                        "model": route.model,
                        "status": "skipped_circuit_open",
                        "fallback_index": fallback_index,
                        "circuit_state": circuit_state,
                    }
                )
                metrics.increment(
                    "llm_provider_requests_total",
                    labels={
                        "route_id": route.route_id,
                        "provider": route.provider,
                        "status": "skipped_circuit_open",
                        "mode": mode_key,
                    },
                )
                continue

            if route_budget is not None and route_budget > 0 and estimated_cost > route_budget:
                telemetry["provider_attempts"].append(
                    {
                        "route_id": route.route_id,
                        "provider": route.provider,
                        "model": route.model,
                        "status": "skipped_budget",
                        "fallback_index": fallback_index,
                        "estimated_cost_usd": estimated_cost,
                        "budget_usd": route_budget,
                    }
                )
                metrics.increment(
                    "llm_provider_requests_total",
                    labels={
                        "route_id": route.route_id,
                        "provider": route.provider,
                        "status": "skipped_budget",
                        "mode": mode_key,
                    },
                )
                last_error = f"Route {route.route_id} estimated ${estimated_cost:.4f}, exceeding the ${route_budget:.4f} budget."
                continue

            for attempt in range(1, max(route.max_attempts, 1) + 1):
                started_at = time.perf_counter()
                attempt_options = self._request_options_for_attempt(
                    route=route,
                    options=options,
                    attempt=attempt,
                )

                try:
                    generation = await self.clients[route_id].generate_structured_with_repair(
                        messages=messages,
                        response_schema=response_schema,
                        options=attempt_options,
                    )
                    latency_ms = int((time.perf_counter() - started_at) * 1_000)
                    actual_cost = route.estimate_cost_usd(
                        tokens_in=int(generation.metadata.get("tokens_in") or 0),
                        tokens_out=int(generation.metadata.get("tokens_out") or 0),
                    )
                    _circuit_breakers.record_success(route_id)
                    attempt_payload = {
                        "route_id": route.route_id,
                        "provider": route.provider,
                        "model": route.model,
                        "status": "succeeded",
                        "attempt": attempt,
                        "fallback_index": fallback_index,
                        "latency_ms": latency_ms,
                        "request_options": attempt_options,
                        "estimated_cost_usd": estimated_cost,
                        "actual_cost_usd": actual_cost,
                    }
                    telemetry["provider_attempts"].append(attempt_payload)
                    telemetry.update(
                        {
                            "selected_route_id": route.route_id,
                            "selected_provider": route.provider,
                            "selected_model": route.model,
                            "fallback_count": fallback_index,
                            "attempts": attempt,
                            "estimated_cost_usd": estimated_cost,
                            "actual_cost_usd": actual_cost,
                            "latency_ms": latency_ms,
                            "budget_usd": route_budget,
                        }
                    )
                    generation.metadata.update(
                        {
                            "provider_id": route.route_id,
                            "provider": route.provider,
                            "model": route.model,
                            "attempts": attempt,
                            "fallback_count": fallback_index,
                            "estimated_cost_usd": estimated_cost,
                            "actual_cost_usd": actual_cost,
                            "budget_usd": route_budget,
                            "latency_ms": latency_ms,
                            "provider_attempts": telemetry["provider_attempts"],
                            "request_options": attempt_options,
                        }
                    )
                    log_event(
                        logger,
                        "llm_provider_request_succeeded",
                        route_id=route.route_id,
                        provider=route.provider,
                        model=route.model,
                        mode=mode_key,
                        attempt=attempt,
                        fallback_index=fallback_index,
                        latency_ms=latency_ms,
                        estimated_cost_usd=estimated_cost,
                        actual_cost_usd=actual_cost,
                        status="succeeded",
                    )
                    metrics.increment(
                        "llm_provider_requests_total",
                        labels={
                            "route_id": route.route_id,
                            "provider": route.provider,
                            "status": "succeeded",
                            "mode": mode_key,
                        },
                    )
                    metrics.observe(
                        "llm_provider_latency_seconds",
                        latency_ms / 1_000,
                        labels={
                            "route_id": route.route_id,
                            "provider": route.provider,
                            "mode": mode_key,
                        },
                    )
                    metrics.observe(
                        "llm_provider_cost_usd",
                        actual_cost,
                        labels={
                            "route_id": route.route_id,
                            "provider": route.provider,
                            "mode": mode_key,
                        },
                    )
                    return generation
                except (LLMTransportError, LLMResponseFormatError, LLMClientError) as exc:
                    latency_ms = int((time.perf_counter() - started_at) * 1_000)
                    last_error = str(exc)

                    raw_text = getattr(exc, "raw_text", None)
                    if raw_text:
                        telemetry["last_raw_text_preview"] = str(raw_text)[:1500]

                    is_retry = attempt < max(route.max_attempts, 1)
                    status = "retrying" if is_retry else "failed"
                    opened = False
                    if not is_retry:
                        opened = _circuit_breakers.record_failure(
                            route_id,
                            threshold=route.circuit_breaker_failure_threshold,
                            reset_seconds=route.circuit_breaker_reset_seconds,
                        )
                    telemetry["provider_attempts"].append(
                        {
                            "route_id": route.route_id,
                            "provider": route.provider,
                            "model": route.model,
                            "status": status,
                            "attempt": attempt,
                            "fallback_index": fallback_index,
                            "latency_ms": latency_ms,
                            "request_options": attempt_options,
                            "estimated_cost_usd": estimated_cost,
                            "error_message": last_error,
                            "circuit_opened": opened,
                        }
                    )
                    log_event(
                        logger,
                        "llm_provider_request_failed",
                        level="warning",
                        route_id=route.route_id,
                        provider=route.provider,
                        model=route.model,
                        mode=mode_key,
                        attempt=attempt,
                        fallback_index=fallback_index,
                        latency_ms=latency_ms,
                        estimated_cost_usd=estimated_cost,
                        circuit_opened=opened,
                        error_type=exc.__class__.__name__,
                        raw_text_preview=(str(raw_text)[:1500] if raw_text else None),
                        error_message=last_error,
                        status=status,
                    )
                    metrics.increment(
                        "llm_provider_requests_total",
                        labels={
                            "route_id": route.route_id,
                            "provider": route.provider,
                            "status": status,
                            "mode": mode_key,
                        },
                    )
                    if opened:
                        metrics.increment(
                            "llm_provider_circuit_open_total",
                            labels={
                                "route_id": route.route_id,
                                "provider": route.provider,
                                "mode": mode_key,
                            },
                        )
                    if is_retry:
                        metrics.increment(
                            "llm_provider_retries_total",
                            labels={
                                "route_id": route.route_id,
                                "provider": route.provider,
                                "mode": mode_key,
                            },
                        )
                        await asyncio.sleep(route.retry_backoff_seconds * attempt)

        telemetry["error_message"] = last_error or "No healthy LLM routes were available."
        raise LLMRoutingError(
            last_error or "No healthy LLM routes were available.",
            telemetry=telemetry,
        )

    def _candidate_order(self, mode: ModeKey) -> list[str]:
        mode_key = _mode_key(mode)
        configured = (
            self.mode_preferences.get(mode_key) or self.mode_preferences.get("default") or []
        )
        deduplicated = [route_id for route_id in configured if route_id in self.routes]
        if not deduplicated:
            deduplicated = list(self.route_order)
        return deduplicated

    def _resolve_budget(self, mode: ModeKey) -> float | None:
        mode_key = _mode_key(mode)
        if mode_key in self.mode_budgets:
            budget = float(self.mode_budgets[mode_key])
            return budget if budget > 0 else None
        default_route = self.routes[self.route_order[0]]
        budget = default_route.request_budget_usd
        return budget if budget is not None and budget > 0 else None


def estimate_prompt_tokens(messages: list[dict[str, str]]) -> int:
    total_chars = 0
    for message in messages:
        total_chars += len(str(message.get("content") or ""))
        total_chars += len(str(message.get("role") or "")) * 2
    return max(int(math.ceil(total_chars / 4.0)), 1)


def cast_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any, *, fallback: float | None) -> float | None:
    if value in (None, ""):
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _mode_key(mode: ModeKey) -> str:
    if isinstance(mode, EvaluationMode):
        return mode.value
    return str(mode).strip()
