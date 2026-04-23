from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.exceptions import NotFoundAppError, ValidationAppError
from backend.db.models import (
    CollaborationComment,
    CollaborationEntityType,
    CollaborationReview,
    CreativeComparison,
    InferenceJob,
    OrganizationMembership,
    ReviewStatus,
    User,
)
from backend.schemas.collaboration import (
    CollaborationCommentCreateRequest,
    CollaborationCommentRead,
    CollaborationReviewRead,
    CollaborationReviewUpdateRequest,
    WorkspaceMemberListResponse,
    WorkspaceMemberRead,
)


class CollaborationApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_workspace_members(self, *, organization_id: UUID) -> WorkspaceMemberListResponse:
        members = await self._load_member_map(organization_id=organization_id)
        items = sorted(
            members.values(),
            key=lambda member: ((member.full_name or "").lower(), member.email.lower()),
        )
        return WorkspaceMemberListResponse(items=items)

    async def get_review(
        self,
        *,
        project_id: UUID,
        organization_id: UUID,
        entity_type: CollaborationEntityType,
        entity_id: UUID,
    ) -> CollaborationReviewRead:
        await self._ensure_entity_exists(
            project_id=project_id, entity_type=entity_type, entity_id=entity_id
        )
        review = await self._load_review(
            project_id=project_id, entity_type=entity_type, entity_id=entity_id
        )
        members = await self._load_member_map(
            organization_id=organization_id,
            user_ids=self._collect_review_user_ids(review),
        )
        return self._build_review_read(
            review=review,
            entity_type=entity_type,
            entity_id=entity_id,
            members=members,
        )

    async def update_review(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        organization_id: UUID,
        entity_type: CollaborationEntityType,
        entity_id: UUID,
        payload: CollaborationReviewUpdateRequest,
    ) -> CollaborationReviewRead:
        await self._ensure_entity_exists(
            project_id=project_id, entity_type=entity_type, entity_id=entity_id
        )
        review = await self._get_or_create_review(
            user_id=user_id,
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        if "assignee_user_id" in payload.model_fields_set:
            if payload.assignee_user_id is not None:
                await self._ensure_user_is_member(
                    organization_id=organization_id,
                    user_id=payload.assignee_user_id,
                )
            review.assignee_user_id = payload.assignee_user_id

        if "review_summary" in payload.model_fields_set:
            review.review_summary = (payload.review_summary or "").strip() or None

        if "status" in payload.model_fields_set and payload.status is not None:
            next_status = ReviewStatus(payload.status)
            review.status = next_status
            if next_status == ReviewStatus.APPROVED:
                review.approved_by_user_id = user_id
                review.approved_at = datetime.now(UTC)
            else:
                review.approved_by_user_id = None
                review.approved_at = None

        await self.session.commit()
        return await self.get_review(
            project_id=project_id,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    async def add_comment(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        organization_id: UUID,
        entity_type: CollaborationEntityType,
        entity_id: UUID,
        payload: CollaborationCommentCreateRequest,
    ) -> CollaborationReviewRead:
        await self._ensure_entity_exists(
            project_id=project_id, entity_type=entity_type, entity_id=entity_id
        )
        review = await self._get_or_create_review(
            user_id=user_id,
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

        self.session.add(
            CollaborationComment(
                review_id=review.id,
                author_user_id=user_id,
                body=payload.body.strip(),
                timestamp_ms=payload.timestamp_ms,
                segment_label=(payload.segment_label or "").strip() or None,
                metadata_json={},
            )
        )
        await self.session.commit()
        return await self.get_review(
            project_id=project_id,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    async def _ensure_entity_exists(
        self,
        *,
        project_id: UUID,
        entity_type: CollaborationEntityType,
        entity_id: UUID,
    ) -> None:
        if entity_type == CollaborationEntityType.ANALYSIS_JOB:
            result = await self.session.execute(
                select(InferenceJob.id, InferenceJob.runtime_params)
                .where(
                    InferenceJob.id == entity_id,
                    InferenceJob.project_id == project_id,
                )
                .limit(1)
            )
            row = result.one_or_none()
            if row is None:
                raise NotFoundAppError("Analysis review target not found.")
            runtime_params = row.runtime_params or {}
            if str(runtime_params.get("analysis_surface") or "") != "analysis_dashboard":
                raise ValidationAppError("Only analysis workspace jobs support collaboration here.")
            return

        result = await self.session.execute(
            select(CreativeComparison.id, CreativeComparison.comparison_context)
            .where(
                CreativeComparison.id == entity_id,
                CreativeComparison.project_id == project_id,
            )
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            raise NotFoundAppError("Comparison review target not found.")
        comparison_context = row.comparison_context or {}
        if str(comparison_context.get("analysis_surface") or "") != "analysis_compare_workspace":
            raise ValidationAppError(
                "Only analysis compare workspace items support collaboration here."
            )

    async def _load_review(
        self,
        *,
        project_id: UUID,
        entity_type: CollaborationEntityType,
        entity_id: UUID,
    ) -> CollaborationReview | None:
        result = await self.session.execute(
            select(CollaborationReview)
            .options(selectinload(CollaborationReview.comments))
            .where(
                CollaborationReview.project_id == project_id,
                CollaborationReview.entity_type == entity_type,
                CollaborationReview.entity_id == entity_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_review(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        entity_type: CollaborationEntityType,
        entity_id: UUID,
    ) -> CollaborationReview:
        review = await self._load_review(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        if review is not None:
            return review

        review = CollaborationReview(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            created_by_user_id=user_id,
            assignee_user_id=None,
            approved_by_user_id=None,
            status=ReviewStatus.DRAFT,
            review_summary=None,
            approved_at=None,
            metadata_json={},
        )
        self.session.add(review)
        await self.session.flush()
        return review

    async def _ensure_user_is_member(self, *, organization_id: UUID, user_id: UUID) -> None:
        result = await self.session.execute(
            select(OrganizationMembership.id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is None:
            raise ValidationAppError("The selected assignee does not belong to this workspace.")

    async def _load_member_map(
        self,
        *,
        organization_id: UUID,
        user_ids: set[UUID] | None = None,
    ) -> dict[UUID, WorkspaceMemberRead]:
        if user_ids is not None and not user_ids:
            return {}

        query = (
            select(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        if user_ids is not None:
            query = query.where(User.id.in_(user_ids))

        result = await self.session.execute(query)
        members: dict[UUID, WorkspaceMemberRead] = {}
        for membership, user in result.all():
            members[user.id] = WorkspaceMemberRead(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=membership.role.value,
            )
        return members

    def _collect_review_user_ids(self, review: CollaborationReview | None) -> set[UUID]:
        if review is None:
            return set()
        user_ids: set[UUID] = {review.created_by_user_id}
        if review.assignee_user_id is not None:
            user_ids.add(review.assignee_user_id)
        if review.approved_by_user_id is not None:
            user_ids.add(review.approved_by_user_id)
        for comment in review.comments:
            user_ids.add(comment.author_user_id)
        return user_ids

    def _build_review_read(
        self,
        *,
        review: CollaborationReview | None,
        entity_type: CollaborationEntityType,
        entity_id: UUID,
        members: dict[UUID, WorkspaceMemberRead],
    ) -> CollaborationReviewRead:
        if review is None:
            return CollaborationReviewRead(
                id=None,
                entity_type=entity_type.value,
                entity_id=entity_id,
                status=ReviewStatus.DRAFT.value,
                comments=[],
            )

        comments = sorted(review.comments, key=lambda item: item.created_at)
        return CollaborationReviewRead(
            id=review.id,
            entity_type=review.entity_type.value,
            entity_id=review.entity_id,
            status=review.status.value,
            review_summary=review.review_summary,
            created_by=members.get(review.created_by_user_id),
            assignee=members.get(review.assignee_user_id)
            if review.assignee_user_id is not None
            else None,
            approved_by=members.get(review.approved_by_user_id)
            if review.approved_by_user_id is not None
            else None,
            approved_at=review.approved_at,
            created_at=review.created_at,
            updated_at=review.updated_at,
            comments=[
                CollaborationCommentRead(
                    id=comment.id,
                    body=comment.body,
                    timestamp_ms=comment.timestamp_ms,
                    segment_label=comment.segment_label,
                    author=members.get(comment.author_user_id),
                    created_at=comment.created_at,
                )
                for comment in comments
            ],
        )
