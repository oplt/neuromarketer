from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import unittest
from uuid import uuid4

from backend.application.services.comparison import ComparisonApplicationService
from backend.db.repositories.inference import PredictionSnapshot


class ComparisonApplicationServiceTests(unittest.TestCase):
    def test_rank_predictions_prefers_higher_business_composite(self) -> None:
        service = ComparisonApplicationService(session=object())  # type: ignore[arg-type]
        first_version_id = uuid4()
        second_version_id = uuid4()

        ranked = service._rank_predictions(
            snapshots={
                first_version_id: PredictionSnapshot(
                    creative_version_id=first_version_id,
                    prediction_result_id=uuid4(),
                    created_at=datetime.now(timezone.utc),
                    scores_by_type={
                        "attention": Decimal("70"),
                        "emotion": Decimal("65"),
                        "memory": Decimal("68"),
                        "cognitive_load": Decimal("48"),
                        "conversion_proxy": Decimal("72"),
                    },
                ),
                second_version_id: PredictionSnapshot(
                    creative_version_id=second_version_id,
                    prediction_result_id=uuid4(),
                    created_at=datetime.now(timezone.utc),
                    scores_by_type={
                        "attention": Decimal("62"),
                        "emotion": Decimal("61"),
                        "memory": Decimal("59"),
                        "cognitive_load": Decimal("53"),
                        "conversion_proxy": Decimal("60"),
                    },
                ),
            }
        )

        self.assertEqual(ranked[0].creative_version_id, first_version_id)
        self.assertEqual(ranked[0].overall_rank, 1)
        self.assertGreater(ranked[0].scores_json["composite"], ranked[1].scores_json["composite"])


if __name__ == "__main__":
    unittest.main()
