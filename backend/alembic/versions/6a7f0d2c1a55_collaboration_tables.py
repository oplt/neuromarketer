"""collaboration tables

Revision ID: 6a7f0d2c1a55
Revises: f2ab1e6d4b81
Create Date: 2026-03-31 21:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "6a7f0d2c1a55"
down_revision: Union[str, Sequence[str], None] = "f2ab1e6d4b81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


collaboration_entity_type = postgresql.ENUM(
    "analysis_job",
    "analysis_comparison",
    name="collaboration_entity_type",
    create_type=False,
)
review_status = postgresql.ENUM(
    "draft",
    "in_review",
    "changes_requested",
    "approved",
    name="review_status",
    create_type=False,
)


def upgrade() -> None:
    collaboration_entity_type.create(op.get_bind(), checkfirst=True)
    review_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "collaboration_reviews",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", collaboration_entity_type, nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("assignee_user_id", sa.UUID(), nullable=True),
        sa.Column("approved_by_user_id", sa.UUID(), nullable=True),
        sa.Column("status", review_status, nullable=False),
        sa.Column("review_summary", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "entity_type", "entity_id", name="uq_collaboration_review_entity"),
    )
    op.create_index(
        "ix_collaboration_reviews_project_status",
        "collaboration_reviews",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_collaboration_reviews_project_assignee",
        "collaboration_reviews",
        ["project_id", "assignee_user_id"],
        unique=False,
    )

    op.create_table(
        "collaboration_comments",
        sa.Column("review_id", sa.UUID(), nullable=False),
        sa.Column("author_user_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=True),
        sa.Column("segment_label", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["collaboration_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collaboration_comments_review_created_at",
        "collaboration_comments",
        ["review_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_collaboration_comments_review_created_at", table_name="collaboration_comments")
    op.drop_table("collaboration_comments")
    op.drop_index("ix_collaboration_reviews_project_assignee", table_name="collaboration_reviews")
    op.drop_index("ix_collaboration_reviews_project_status", table_name="collaboration_reviews")
    op.drop_table("collaboration_reviews")
    review_status.drop(op.get_bind(), checkfirst=True)
    collaboration_entity_type.drop(op.get_bind(), checkfirst=True)
