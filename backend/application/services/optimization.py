from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from backend.db.models import PredictionResult, SuggestionType
from backend.schemas.schemas import OptimizationSuggestionRead


class OptimizationApplicationService:
    def optimize(
        self,
        *,
        prediction: PredictionResult,
        max_suggestions: int,
        constraints: dict[str, Any],
    ) -> list[OptimizationSuggestionRead]:
        suggestions = [OptimizationSuggestionRead.model_validate(item) for item in prediction.suggestions]
        if not suggestions:
            return []

        excluded_types = {value for value in constraints.get("exclude_types", [])}
        min_confidence = Decimal(str(constraints.get("min_confidence", 0)))
        focus_metrics = set(constraints.get("focus_metrics", []))

        filtered = [
            suggestion
            for suggestion in suggestions
            if suggestion.suggestion_type not in excluded_types and Decimal(suggestion.confidence or 0) >= min_confidence
        ]
        filtered.sort(
            key=lambda suggestion: self._suggestion_priority(
                suggestion.expected_score_lift_json,
                suggestion.confidence,
                focus_metrics,
            ),
            reverse=True,
        )
        return filtered[:max_suggestions]

    def _suggestion_priority(
        self,
        expected_lift: dict[str, Any],
        confidence: Decimal | None,
        focus_metrics: set[str],
    ) -> float:
        if focus_metrics:
            weighted_lift = sum(float(expected_lift.get(metric, 0)) for metric in focus_metrics)
        else:
            weighted_lift = sum(float(value) for value in expected_lift.values() if isinstance(value, (int, float)))
        return weighted_lift + float(confidence or 0)
