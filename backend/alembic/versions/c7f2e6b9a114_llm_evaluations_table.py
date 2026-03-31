"""llm evaluations table

Revision ID: c7f2e6b9a114
Revises: 9c5a6d6f4d21
Create Date: 2026-03-31 10:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c7f2e6b9a114"
down_revision: Union[str, Sequence[str], None] = "9c5a6d6f4d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_evaluations",
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("model_provider", sa.String(length=120), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("input_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evaluation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["inference_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "mode", name="uq_llm_evaluations_job_mode"),
    )
    op.create_index("ix_llm_evaluations_job_status", "llm_evaluations", ["job_id", "status"], unique=False)
    op.create_index(
        "ix_llm_evaluations_user_created_at",
        "llm_evaluations",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_llm_evaluations_user_created_at", table_name="llm_evaluations")
    op.drop_index("ix_llm_evaluations_job_status", table_name="llm_evaluations")
    op.drop_table("llm_evaluations")
