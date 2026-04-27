"""Add inference_jobs columns/index if missing (legacy DBs).

Revision ID: e4a8f1c2b3d4
Revises: d6705766ce0f
Create Date: 2026-04-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4a8f1c2b3d4"
down_revision: Union[str, Sequence[str], None] = "d6705766ce0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE inference_jobs ADD COLUMN IF NOT EXISTS analysis_surface VARCHAR(64)"
        )
    )
    op.execute(
        sa.text("ALTER TABLE inference_jobs ADD COLUMN IF NOT EXISTS media_type VARCHAR(40)")
    )
    op.execute(
        sa.text(
            "ALTER TABLE inference_jobs ADD COLUMN IF NOT EXISTS execution_phase VARCHAR(40)"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE inference_jobs ADD COLUMN IF NOT EXISTS "
            "execution_phase_updated_at TIMESTAMPTZ"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_inference_jobs_execution_phase "
            "ON inference_jobs (execution_phase)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_inference_jobs_project_user_surface_media_created "
            "ON inference_jobs (project_id, created_by_user_id, analysis_surface, "
            "media_type, created_at)"
        )
    )


def downgrade() -> None:
    pass
