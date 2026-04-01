from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


CollaborationEntityTypeValue = Literal["analysis_job", "analysis_comparison"]
ReviewStatusValue = Literal["draft", "in_review", "changes_requested", "approved"]


class WorkspaceMemberRead(BaseModel):
    id: UUID
    email: str
    full_name: str | None = None
    role: str


class WorkspaceMemberListResponse(BaseModel):
    items: list[WorkspaceMemberRead] = Field(default_factory=list)


class CollaborationCommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5_000)
    timestamp_ms: int | None = Field(default=None, ge=0)
    segment_label: str | None = Field(default=None, max_length=255)


class CollaborationReviewUpdateRequest(BaseModel):
    status: ReviewStatusValue | None = None
    assignee_user_id: UUID | None = None
    review_summary: str | None = Field(default=None, max_length=2_000)


class CollaborationCommentRead(BaseModel):
    id: UUID
    body: str
    timestamp_ms: int | None = None
    segment_label: str | None = None
    author: WorkspaceMemberRead | None = None
    created_at: datetime


class CollaborationReviewRead(BaseModel):
    id: UUID | None = None
    entity_type: CollaborationEntityTypeValue
    entity_id: UUID
    status: ReviewStatusValue
    review_summary: str | None = None
    created_by: WorkspaceMemberRead | None = None
    assignee: WorkspaceMemberRead | None = None
    approved_by: WorkspaceMemberRead | None = None
    approved_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    comments: list[CollaborationCommentRead] = Field(default_factory=list)
