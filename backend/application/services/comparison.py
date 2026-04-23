from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.core.log_context import bound_log_context
from backend.core.logging import get_logger, log_event
from backend.db.repositories import ComparisonRepository, CreativeRepository, InferenceRepository

logger = get_logger(__name__)


@dataclass(slots=True)
class RankedComparisonItem:
    creative_version_id: UUID
    overall_rank: int
    scores_json: dict[str, Any]
    rationale: str


class ComparisonApplicationService:
    WEIGHTS = {
        "conversion_proxy": 0.4,
        "attention": 0.22,
        "memory": 0.2,
        "emotion": 0.13,
        "cognitive_load": -0.05,
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.creatives = CreativeRepository(session)
        self.inference = InferenceRepository(session)
        self.comparisons = ComparisonRepository(session)

    async def compare(
        self,
        *,
        project_id: UUID,
        name: str,
        creative_version_ids: list[UUID],
        comparison_context: dict[str, Any],
    ):
        with bound_log_context(project_id=str(project_id)):
            log_event(
                logger,
                "comparison_requested",
                project_id=str(project_id),
                candidate_count=len(creative_version_ids),
                status="started",
            )
            creative_items: list[tuple[UUID, UUID]] = []
            for creative_version_id in creative_version_ids:
                version = await self.creatives.get_creative_version(creative_version_id)
                if version is None:
                    raise NotFoundAppError(f"Creative version {creative_version_id} not found.")
                creative = await self.creatives.get_creative(version.creative_id)
                if creative is None or creative.project_id != project_id:
                    raise ValidationAppError(
                        "All comparison candidates must belong to the same project."
                    )
                creative_items.append((creative.id, version.id))

            snapshots = await self.inference.get_latest_prediction_snapshots(creative_version_ids)
            missing = [
                str(version_id)
                for version_id in creative_version_ids
                if version_id not in snapshots
            ]
            if missing:
                raise ConflictAppError(
                    "Comparison requires an existing prediction for each creative version.",
                    code="missing_predictions",
                )

            ranked_items = self._rank_predictions(snapshots=snapshots)
            comparison = await self.comparisons.create_comparison(
                project_id=project_id,
                name=name,
                creative_items=creative_items,
                comparison_context=comparison_context,
            )
            winner_id = ranked_items[0].creative_version_id if ranked_items else None
            await self.comparisons.replace_result(
                comparison_id=comparison.id,
                winning_creative_version_id=winner_id,
                summary_json={
                    "method": "weighted_business_score",
                    "weights": self.WEIGHTS,
                    "candidate_count": len(ranked_items),
                },
                items=[
                    {
                        "creative_version_id": item.creative_version_id,
                        "overall_rank": item.overall_rank,
                        "scores_json": item.scores_json,
                        "rationale": item.rationale,
                    }
                    for item in ranked_items
                ],
            )
            await self.session.commit()
            result = await self.comparisons.get_result(comparison.id)
            if result is None:
                raise NotFoundAppError("Comparison result not found.")
            log_event(
                logger,
                "comparison_completed",
                comparison_id=str(comparison.id),
                creative_version_id=str(winner_id) if winner_id else None,
                candidate_count=len(ranked_items),
                status="succeeded",
            )
            return comparison, result

    def _rank_predictions(
        self,
        *,
        snapshots,
    ) -> list[RankedComparisonItem]:
        ranked = []
        for creative_version_id, snapshot in snapshots.items():
            composite = self._composite_score(snapshot.scores_by_type)
            ranked.append(
                {
                    "creative_version_id": creative_version_id,
                    "composite": composite,
                    "scores_json": {
                        **{key: float(value) for key, value in snapshot.scores_by_type.items()},
                        "composite": float(composite),
                    },
                    "rationale": self._build_rationale(snapshot.scores_by_type),
                }
            )

        ranked.sort(
            key=lambda item: (
                float(item["composite"]),
                float(item["scores_json"].get("conversion_proxy", 0)),
                str(item["creative_version_id"]),
            ),
            reverse=True,
        )
        return [
            RankedComparisonItem(
                creative_version_id=item["creative_version_id"],
                overall_rank=index,
                scores_json=item["scores_json"],
                rationale=item["rationale"],
            )
            for index, item in enumerate(ranked, start=1)
        ]

    def _composite_score(self, scores_by_type: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for score_name, weight in self.WEIGHTS.items():
            total += scores_by_type.get(score_name, Decimal("0")) * Decimal(str(weight))
        return total.quantize(Decimal("0.01"))

    def _build_rationale(self, scores_by_type: dict[str, Decimal]) -> str:
        ranked_scores = sorted(scores_by_type.items(), key=lambda item: item[1], reverse=True)
        strongest = ", ".join(name for name, _ in ranked_scores[:2])
        weakest = min(scores_by_type.items(), key=lambda item: item[1])[0]
        return f"Strongest predicted drivers: {strongest}. Primary risk: {weakest}."
