"""llm evaluation metadata

Revision ID: a91e7b55d2c3
Revises: 6a7f0d2c1a55
Create Date: 2026-03-31 21:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a91e7b55d2c3"
down_revision: Union[str, Sequence[str], None] = "6a7f0d2c1a55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_evaluations",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("llm_evaluations", "metadata_json", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_evaluations", "metadata_json")
