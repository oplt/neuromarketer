from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.core.logging import get_logger, log_event, log_exception
from backend.db.models import PredictionResult
from backend.schemas.schemas import OptimizationSuggestionRead

logger = get_logger(__name__)


class OptimizationApplicationService:
    def optimize(
        self,
        *,
        prediction: PredictionResult,
        max_suggestions: int,
        constraints: dict[str, Any],
    ) -> list[OptimizationSuggestionRead]:
        try:
            log_event(
                logger,
                "optimization_requested",
                prediction_result_id=str(prediction.id),
                status="started",
                max_suggestions=max_suggestions,
                focus_metrics=sorted(constraints.get("focus_metrics", [])),
                exclude_types=sorted(constraints.get("exclude_types", [])),
                min_confidence=float(Decimal(str(constraints.get("min_confidence", 0)))),
            )
            suggestions = [
                OptimizationSuggestionRead.model_validate(item) for item in prediction.suggestions
            ]
            if not suggestions:
                log_event(
                    logger,
                    "optimization_generated",
                    prediction_result_id=str(prediction.id),
                    status="succeeded",
                    suggestion_count=0,
                )
                return []

            excluded_types = {value for value in constraints.get("exclude_types", [])}
            min_confidence = Decimal(str(constraints.get("min_confidence", 0)))
            focus_metrics = set(constraints.get("focus_metrics", []))

            filtered = [
                suggestion
                for suggestion in suggestions
                if suggestion.suggestion_type not in excluded_types
                and Decimal(suggestion.confidence or 0) >= min_confidence
            ]
            filtered.sort(
                key=lambda suggestion: self._suggestion_priority(
                    suggestion.expected_score_lift_json,
                    suggestion.confidence,
                    focus_metrics,
                ),
                reverse=True,
            )
            generated = filtered[:max_suggestions]
            log_event(
                logger,
                "optimization_generated",
                prediction_result_id=str(prediction.id),
                status="succeeded",
                suggestion_count=len(generated),
            )
            return generated
        except Exception as exc:
            log_exception(
                logger,
                "optimization_failed",
                exc,
                prediction_result_id=str(prediction.id),
                status="failed",
            )
            raise

    def _suggestion_priority(
        self,
        expected_lift: dict[str, Any],
        confidence: Decimal | None,
        focus_metrics: set[str],
    ) -> float:
        if focus_metrics:
            weighted_lift = sum(float(expected_lift.get(metric, 0)) for metric in focus_metrics)
        else:
            weighted_lift = sum(
                float(value) for value in expected_lift.values() if isinstance(value, (int, float))
            )
        return weighted_lift + float(confidence or 0)
