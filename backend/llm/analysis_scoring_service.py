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
        token_key = self.router.output_token_option_key_for_mode(mode=self.MODE)
        if token_key == "num_predict":
            return {"num_predict": max_tokens}
        return {"max_tokens": max_tokens}

    @staticmethod
    def _clamp_score(value: Any, *, default: int = 50) -> int:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        if 0.0 <= numeric <= 1.0:
            numeric *= 100.0
        return max(0, min(100, int(round(numeric))))

    @staticmethod
    def _clamp_confidence(value: Any, *, default: float = 0.5) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, numeric))

    @staticmethod
    def _normalize_int(value: Any, *, default: int) -> int:
        try:
            numeric = int(float(value))
        except (TypeError, ValueError):
            numeric = default
        return max(0, numeric)

    @staticmethod
    def _first_non_empty_str(source: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _normalize_notes(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        notes: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                notes.append(text)
            if len(notes) >= 6:
                break
        return notes

    def _coerce_metric(
        self,
        *,
        source: dict[str, Any],
        metric_name: str,
        aliases: tuple[str, ...],
        default_reason: str,
    ) -> dict[str, Any]:
        raw_metric: Any = None
        for key in (metric_name, *aliases):
            if key in source:
                raw_metric = source[key]
                break

        if isinstance(raw_metric, dict):
            score = self._clamp_score(
                raw_metric.get("score", raw_metric.get("value")),
                default=50,
            )
            confidence = self._clamp_confidence(raw_metric.get("confidence"), default=0.5)
            reason = str(raw_metric.get("reason") or default_reason).strip() or default_reason
            reason = reason[:1000]
            raw_evidence = raw_metric.get("evidence")
            evidence = []
            if isinstance(raw_evidence, list):
                for item in raw_evidence:
                    text = str(item or "").strip()
                    if text:
                        evidence.append(text)
                    if len(evidence) >= 4:
                        break
        else:
            score = self._clamp_score(raw_metric, default=50)
            confidence = 0.5
            reason = default_reason
            evidence = []

        return {
            "score": score,
            "confidence": confidence,
            "reason": reason,
            "evidence": evidence,
        }

    def _coerce_timeline_points(
        self,
        *,
        raw_timeline: Any,
        fallback_scores: dict[str, int],
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_timeline, list):
            return []

        timeline_points: list[dict[str, Any]] = []
        for index, item in enumerate(raw_timeline):
            if isinstance(item, str):
                rationale = item.strip()[:500] or None
                timeline_points.append(
                    {
                        "segment_index": index,
                        "timestamp_ms": index * 1000,
                        "attention_score": fallback_scores["attention"],
                        "emotion_score": fallback_scores["emotion"],
                        "memory_score": fallback_scores["memory"],
                        "cognitive_load_score": fallback_scores["cognitive_load"],
                        "conversion_proxy_score": fallback_scores["conversion_proxy"],
                        "rationale": rationale,
                    }
                )
                continue

            if not isinstance(item, dict):
                continue

            timeline_points.append(
                {
                    "segment_index": self._normalize_int(
                        item.get("segment_index", index),
                        default=index,
                    ),
                    "timestamp_ms": self._normalize_int(
                        item.get("timestamp_ms", item.get("timestamp", index * 1000)),
                        default=index * 1000,
                    ),
                    "attention_score": self._clamp_score(
                        item.get(
                            "attention_score",
                            item.get("attention", item.get("engagement_score")),
                        ),
                        default=fallback_scores["attention"],
                    ),
                    "emotion_score": self._clamp_score(
                        item.get("emotion_score", item.get("emotion")),
                        default=fallback_scores["emotion"],
                    ),
                    "memory_score": self._clamp_score(
                        item.get("memory_score", item.get("memory")),
                        default=fallback_scores["memory"],
                    ),
                    "cognitive_load_score": self._clamp_score(
                        item.get(
                            "cognitive_load_score",
                            item.get("cognitive_load", item.get("friction_score")),
                        ),
                        default=fallback_scores["cognitive_load"],
                    ),
                    "conversion_proxy_score": self._clamp_score(
                        item.get(
                            "conversion_proxy_score",
                            item.get("conversion_proxy", item.get("cta_score")),
                        ),
                        default=fallback_scores["conversion_proxy"],
                    ),
                    "rationale": (
                        str(
                            item.get("rationale")
                            or item.get("explanation")
                            or item.get("detail")
                            or item.get("recommendation")
                            or ""
                        ).strip()[:500]
                        or None
                    ),
                }
            )

        return timeline_points

    def _coerce_suggestions(self, raw_suggestions: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_suggestions, list):
            return []

        allowed_suggestion_types = {
            "copy",
            "layout",
            "color",
            "cta",
            "framing",
            "pacing",
            "thumbnail",
            "branding",
        }
        allowed_lift_keys = {
            "attention",
            "emotion",
            "memory",
            "cognitive_load",
            "conversion_proxy",
        }

        suggestions: list[dict[str, Any]] = []
        for index, item in enumerate(raw_suggestions):
            if isinstance(item, str):
                text = item.strip()
                if not text:
                    continue
                suggestions.append(
                    {
                        "suggestion_type": "copy",
                        "title": text[:180],
                        "rationale": text[:1000],
                        "proposed_change_json": {},
                        "expected_score_lift_json": {},
                        "confidence": 0.5,
                        "timestamp_ms": None,
                    }
                )
            elif isinstance(item, dict):
                raw_type = str(
                    item.get("suggestion_type")
                    or item.get("type")
                    or item.get("category")
                    or "copy"
                ).strip()
                suggestion_type = raw_type if raw_type in allowed_suggestion_types else "copy"
                title = str(
                    item.get("title")
                    or item.get("recommendation")
                    or item.get("action")
                    or f"Suggested optimization {index + 1}"
                ).strip()
                if not title:
                    title = f"Suggested optimization {index + 1}"
                rationale = str(
                    item.get("rationale")
                    or item.get("detail")
                    or item.get("explanation")
                    or title
                ).strip()
                if not rationale:
                    rationale = title

                raw_lift = item.get("expected_score_lift_json", item.get("expected_lift"))
                expected_lift: dict[str, float] = {}
                if isinstance(raw_lift, dict):
                    for key, value in raw_lift.items():
                        if key not in allowed_lift_keys:
                            continue
                        try:
                            expected_lift[key] = float(value)
                        except (TypeError, ValueError):
                            continue

                proposed_change_json = item.get("proposed_change_json")
                if not isinstance(proposed_change_json, dict):
                    proposed_change_json = {}
                    for key in ("recommendation", "action", "segment_index", "timestamp_ms"):
                        if key in item:
                            proposed_change_json[key] = item[key]

                suggestions.append(
                    {
                        "suggestion_type": suggestion_type,
                        "title": title[:180],
                        "rationale": rationale[:1000],
                        "proposed_change_json": proposed_change_json,
                        "expected_score_lift_json": expected_lift,
                        "confidence": self._clamp_confidence(item.get("confidence"), default=0.5),
                        "timestamp_ms": (
                            self._normalize_int(
                                item.get("timestamp_ms", item.get("timestamp")),
                                default=0,
                            )
                            if item.get("timestamp_ms", item.get("timestamp")) is not None
                            else None
                        ),
                    }
                )

            if len(suggestions) >= 6:
                break

        return suggestions

    def _coerce_schema_mismatch_payload(
        self,
        *,
        raw_payload: Any,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(raw_payload, dict):
            return None

        score_source = raw_payload.get("scores")
        if not isinstance(score_source, dict):
            score_source = raw_payload.get("scorecard")
        if not isinstance(score_source, dict):
            score_source = raw_payload

        scores = {
            "attention": self._coerce_metric(
                source=score_source,
                metric_name="attention",
                aliases=("overall_attention", "overall_attention_score"),
                default_reason=(
                    "Recovered from a non-standard model payload; score uses fallback interpretation."
                ),
            ),
            "emotion": self._coerce_metric(
                source=score_source,
                metric_name="emotion",
                aliases=(),
                default_reason=(
                    "Recovered from a non-standard model payload; score uses fallback interpretation."
                ),
            ),
            "memory": self._coerce_metric(
                source=score_source,
                metric_name="memory",
                aliases=("memory_proxy", "memory_proxy_score"),
                default_reason=(
                    "Recovered from a non-standard model payload; score uses fallback interpretation."
                ),
            ),
            "cognitive_load": self._coerce_metric(
                source=score_source,
                metric_name="cognitive_load",
                aliases=("cognitive_load_proxy",),
                default_reason=(
                    "Recovered from a non-standard model payload; score uses fallback interpretation."
                ),
            ),
            "conversion_proxy": self._coerce_metric(
                source=score_source,
                metric_name="conversion_proxy",
                aliases=("conversion", "conversion_proxy_score"),
                default_reason=(
                    "Recovered from a non-standard model payload; score uses fallback interpretation."
                ),
            ),
        }

        fallback_score_values = {
            metric_name: int(metric_payload["score"])
            for metric_name, metric_payload in scores.items()
        }
        raw_timeline = raw_payload.get("timeline_points", raw_payload.get("timeline"))
        timeline_points = self._coerce_timeline_points(
            raw_timeline=raw_timeline,
            fallback_scores=fallback_score_values,
        )
        if not timeline_points:
            segment_features = context.get("segment_features")
            if isinstance(segment_features, list) and segment_features:
                for index, segment in enumerate(segment_features):
                    if not isinstance(segment, dict):
                        continue
                    timestamp_ms = self._normalize_int(
                        segment.get("start_ms", index * 1000),
                        default=index * 1000,
                    )
                    timeline_points.append(
                        {
                            "segment_index": self._normalize_int(
                                segment.get("segment_index", index), default=index
                            ),
                            "timestamp_ms": timestamp_ms,
                            "attention_score": fallback_score_values["attention"],
                            "emotion_score": fallback_score_values["emotion"],
                            "memory_score": fallback_score_values["memory"],
                            "cognitive_load_score": fallback_score_values["cognitive_load"],
                            "conversion_proxy_score": fallback_score_values["conversion_proxy"],
                            "rationale": "Fallback timeline point generated from segment context.",
                        }
                    )
            else:
                timeline_points.append(
                    {
                        "segment_index": 0,
                        "timestamp_ms": 0,
                        "attention_score": fallback_score_values["attention"],
                        "emotion_score": fallback_score_values["emotion"],
                        "memory_score": fallback_score_values["memory"],
                        "cognitive_load_score": fallback_score_values["cognitive_load"],
                        "conversion_proxy_score": fallback_score_values["conversion_proxy"],
                        "rationale": "Fallback timeline point generated from normalized output.",
                    }
                )

        overall_summary = self._first_non_empty_str(
            raw_payload,
            "overall_summary",
            "summary",
            "executive_summary",
            "overall_verdict",
        )
        if overall_summary is None:
            overall_summary = (
                "Scoring output was normalized from a non-standard provider payload."
            )
        overall_summary = overall_summary[:2000]

        notes = self._normalize_notes(raw_payload.get("notes"))
        if not notes:
            notes = [
                "Provider response did not match the strict schema; normalized fallback was used."
            ]

        suggestions = self._coerce_suggestions(
            raw_payload.get("suggestions", raw_payload.get("recommendations"))
        )

        return {
            "overall_summary": overall_summary,
            "notes": notes,
            "scores": scores,
            "timeline_points": timeline_points,
            "suggestions": suggestions,
        }

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
            normalized_payload = self._coerce_schema_mismatch_payload(
                raw_payload=generation.parsed_json,
                context=context,
            )
            validated = None
            if normalized_payload is not None:
                try:
                    validated = AnalysisScoringResult.model_validate(normalized_payload)
                except ValidationError:
                    validated = None
                else:
                    log_event(
                        logger,
                        "llm_scoring_schema_mismatch_recovered",
                        level="warning",
                        provider=generation.metadata.get("provider"),
                        model=generation.metadata.get("model"),
                        route_id=generation.metadata.get("provider_id"),
                        original_error_type=exc.__class__.__name__,
                        original_error_message=str(exc),
                        status="recovered",
                    )

            if validated is None:
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
