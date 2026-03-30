"""analysis upload ownership columns

Revision ID: 3e6f8c8f9f52
Revises: 69068f4312e7
Create Date: 2026-03-30 22:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3e6f8c8f9f52"
down_revision: Union[str, Sequence[str], None] = "69068f4312e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    upload_status_enum = postgresql.ENUM(
        "PENDING",
        "UPLOADING",
        "STORED",
        "FAILED",
        name="upload_status",
        create_type=False,
    )

    op.add_column("stored_artifacts", sa.Column("created_by_user_id", sa.UUID(), nullable=True))
    op.add_column(
        "stored_artifacts",
        sa.Column(
            "upload_status",
            upload_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.create_foreign_key(
        "fk_stored_artifacts_created_by_user_id_users",
        "stored_artifacts",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_stored_artifacts_user_status",
        "stored_artifacts",
        ["created_by_user_id", "upload_status"],
        unique=False,
    )
    op.alter_column("stored_artifacts", "upload_status", server_default=None)

    op.add_column("upload_sessions", sa.Column("created_by_user_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_upload_sessions_created_by_user_id_users",
        "upload_sessions",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_upload_sessions_user_status",
        "upload_sessions",
        ["created_by_user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_upload_sessions_user_status", table_name="upload_sessions")
    op.drop_constraint("fk_upload_sessions_created_by_user_id_users", "upload_sessions", type_="foreignkey")
    op.drop_column("upload_sessions", "created_by_user_id")

    op.drop_index("ix_stored_artifacts_user_status", table_name="stored_artifacts")
    op.drop_constraint("fk_stored_artifacts_created_by_user_id_users", "stored_artifacts", type_="foreignkey")
    op.drop_column("stored_artifacts", "upload_status")
    op.drop_column("stored_artifacts", "created_by_user_id")
