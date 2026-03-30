from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
from uuid import uuid4

from backend.application.services.optimization import OptimizationApplicationService
from backend.schemas.schemas import OptimizationSuggestionRead


class OptimizationApplicationServiceTests(unittest.TestCase):
    def test_optimize_filters_and_orders_suggestions(self) -> None:
        timestamp = datetime.now(timezone.utc)
        suggestions = [
            OptimizationSuggestionRead(
                id=uuid4(),
                prediction_result_id=uuid4(),
                suggestion_type="cta",
                status="proposed",
                title="CTA",
                rationale="Improve CTA clarity.",
                proposed_change_json={},
                expected_score_lift_json={"conversion_proxy": 5.0, "attention": 1.0},
                confidence=Decimal("0.80"),
                created_at=timestamp,
                updated_at=timestamp,
            ),
            OptimizationSuggestionRead(
                id=uuid4(),
                prediction_result_id=uuid4(),
                suggestion_type="copy",
                status="proposed",
                title="Copy",
                rationale="Reduce load.",
                proposed_change_json={},
                expected_score_lift_json={"cognitive_load": -4.0, "conversion_proxy": 2.0},
                confidence=Decimal("0.55"),
                created_at=timestamp,
                updated_at=timestamp,
            ),
        ]
        prediction = SimpleNamespace(suggestions=suggestions)

        optimized = OptimizationApplicationService().optimize(
            prediction=prediction,  # type: ignore[arg-type]
            max_suggestions=5,
            constraints={"min_confidence": 0.6, "focus_metrics": ["conversion_proxy"]},
        )

        self.assertEqual(len(optimized), 1)
        self.assertEqual(optimized[0].suggestion_type, "cta")


if __name__ == "__main__":
    unittest.main()
