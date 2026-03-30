"""analysis results table

Revision ID: 9c5a6d6f4d21
Revises: 3e6f8c8f9f52
Create Date: 2026-03-30 23:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9c5a6d6f4d21"
down_revision: Union[str, Sequence[str], None] = "3e6f8c8f9f52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_results",
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("timeline_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("segments_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("visualizations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recommendations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["inference_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_analysis_result_job"),
    )
    op.create_index(
        "ix_analysis_results_job_created_at",
        "analysis_results",
        ["job_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_results_job_created_at", table_name="analysis_results")
    op.drop_table("analysis_results")
