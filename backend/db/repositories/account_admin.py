from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    ApiKey,
    ApiKeyStatus,
    InferenceJob,
    JobStatus,
    OrganizationMembership,
    Project,
    WebhookEndpoint,
)


@dataclass(slots=True)
class ControlCenterStats:
    member_count: int
    project_count: int
    active_api_key_count: int
    active_webhook_count: int
    completed_analysis_count: int


class AccountAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_control_center_stats(self, *, organization_id: UUID) -> ControlCenterStats:
        member_count_subquery = (
            select(func.count(OrganizationMembership.id))
            .where(OrganizationMembership.organization_id == organization_id)
            .scalar_subquery()
        )
        project_count_subquery = (
            select(func.count(Project.id))
            .where(Project.organization_id == organization_id)
            .scalar_subquery()
        )
        active_api_key_subquery = (
            select(func.count(ApiKey.id))
            .where(
                ApiKey.organization_id == organization_id,
                ApiKey.status == ApiKeyStatus.ACTIVE,
            )
            .scalar_subquery()
        )
        active_webhook_subquery = (
            select(func.count(WebhookEndpoint.id))
            .where(
                WebhookEndpoint.organization_id == organization_id,
                WebhookEndpoint.is_active.is_(True),
            )
            .scalar_subquery()
        )
        completed_analysis_subquery = (
            select(func.count(InferenceJob.id))
            .select_from(InferenceJob)
            .join(Project, Project.id == InferenceJob.project_id)
            .where(
                Project.organization_id == organization_id,
                InferenceJob.status == JobStatus.SUCCEEDED,
            )
            .scalar_subquery()
        )
        row = (
            await self.session.execute(
                select(
                    member_count_subquery,
                    project_count_subquery,
                    active_api_key_subquery,
                    active_webhook_subquery,
                    completed_analysis_subquery,
                )
            )
        ).one()
        return ControlCenterStats(
            member_count=int(row[0] or 0),
            project_count=int(row[1] or 0),
            active_api_key_count=int(row[2] or 0),
            active_webhook_count=int(row[3] or 0),
            completed_analysis_count=int(row[4] or 0),
        )
