from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import (
    CreativeComparison,
    CreativeComparisonItem,
    CreativeComparisonItemResult,
    CreativeComparisonResult,
)


class ComparisonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_comparison(
        self,
        *,
        project_id: UUID,
        name: str,
        creative_items: list[tuple[UUID, UUID]],
        comparison_context: dict,
    ) -> CreativeComparison:
        comparison = CreativeComparison(
            project_id=project_id,
            name=name,
            comparison_context=comparison_context,
        )
        self.session.add(comparison)
        await self.session.flush()

        for creative_id, creative_version_id in creative_items:
            self.session.add(
                CreativeComparisonItem(
                    comparison_id=comparison.id,
                    creative_id=creative_id,
                    creative_version_id=creative_version_id,
                )
            )

        await self.session.flush()
        await self.session.refresh(comparison)
        return comparison

    async def replace_result(
        self,
        *,
        comparison_id: UUID,
        winning_creative_version_id: UUID | None,
        summary_json: dict,
        items: list[dict],
    ) -> CreativeComparisonResult:
        await self.session.execute(
            delete(CreativeComparisonItemResult).where(
                CreativeComparisonItemResult.comparison_result_id.in_(
                    select(CreativeComparisonResult.id).where(CreativeComparisonResult.comparison_id == comparison_id)
                )
            )
        )
        await self.session.execute(delete(CreativeComparisonResult).where(CreativeComparisonResult.comparison_id == comparison_id))

        comparison_result = CreativeComparisonResult(
            comparison_id=comparison_id,
            winning_creative_version_id=winning_creative_version_id,
            summary_json=summary_json,
        )
        self.session.add(comparison_result)
        await self.session.flush()

        for item in items:
            self.session.add(
                CreativeComparisonItemResult(
                    comparison_result_id=comparison_result.id,
                    creative_version_id=item["creative_version_id"],
                    overall_rank=item["overall_rank"],
                    scores_json=item["scores_json"],
                    rationale=item.get("rationale"),
                )
            )

        await self.session.flush()
        await self.session.refresh(comparison_result)
        return comparison_result

    async def get_result(self, comparison_id: UUID) -> CreativeComparisonResult | None:
        result = await self.session.execute(
            select(CreativeComparisonResult)
            .options(selectinload(CreativeComparisonResult.item_results))
            .where(CreativeComparisonResult.comparison_id == comparison_id)
        )
        return result.scalar_one_or_none()
