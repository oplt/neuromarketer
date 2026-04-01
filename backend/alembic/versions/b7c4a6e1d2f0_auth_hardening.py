"""auth hardening

Revision ID: b7c4a6e1d2f0
Revises: a91e7b55d2c3
Create Date: 2026-03-31 22:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b7c4a6e1d2f0"
down_revision: Union[str, Sequence[str], None] = "a91e7b55d2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


org_role = postgresql.ENUM("owner", "admin", "member", "viewer", name="org_role", create_type=False)
workspace_invite_status = postgresql.ENUM(
    "pending",
    "accepted",
    "revoked",
    "expired",
    name="workspace_invite_status",
    create_type=False,
)
mfa_method_type = postgresql.ENUM("totp", name="mfa_method_type", create_type=False)
sso_provider_type = postgresql.ENUM("oidc", "saml", name="sso_provider_type", create_type=False)


def upgrade() -> None:
    workspace_invite_status.create(op.get_bind(), checkfirst=True)
    mfa_method_type.create(op.get_bind(), checkfirst=True)
    sso_provider_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "workspace_invites",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("invited_by_user_id", sa.UUID(), nullable=False),
        sa.Column("accepted_by_user_id", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", org_role, nullable=False),
        sa.Column("token_prefix", sa.String(length=24), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            workspace_invite_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_workspace_invites_token_hash"),
    )
    op.create_index("ix_workspace_invites_email_status", "workspace_invites", ["email", "status"], unique=False)
    op.create_index("ix_workspace_invites_org_status", "workspace_invites", ["organization_id", "status"], unique=False)
    op.alter_column("workspace_invites", "status", server_default=None)
    op.alter_column("workspace_invites", "metadata_json", server_default=None)

    op.create_table(
        "user_sessions",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_family_id", sa.UUID(), nullable=False),
        sa.Column("token_prefix", sa.String(length=24), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=120), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=255), nullable=True),
        sa.Column("replaced_by_session_id", sa.UUID(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replaced_by_session_id"], ["user_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_org_user", "user_sessions", ["organization_id", "user_id"], unique=False)
    op.create_index("ix_user_sessions_user_revoked", "user_sessions", ["user_id", "revoked_at"], unique=False)
    op.alter_column("user_sessions", "metadata_json", server_default=None)

    op.create_table(
        "user_mfa_credentials",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "method_type",
            mfa_method_type,
            nullable=False,
            server_default="totp",
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("pending_secret_ciphertext", sa.Text(), nullable=True),
        sa.Column(
            "recovery_code_hashes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "method_type", name="uq_user_mfa_credential_method"),
    )
    op.create_index(
        "ix_user_mfa_credentials_user_enabled",
        "user_mfa_credentials",
        ["user_id", "is_enabled"],
        unique=False,
    )
    op.alter_column("user_mfa_credentials", "method_type", server_default=None)
    op.alter_column("user_mfa_credentials", "is_enabled", server_default=None)
    op.alter_column("user_mfa_credentials", "recovery_code_hashes", server_default=None)
    op.alter_column("user_mfa_credentials", "metadata_json", server_default=None)

    op.create_table(
        "organization_sso_configs",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "provider_type",
            sso_provider_type,
            nullable=False,
            server_default="oidc",
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("issuer_url", sa.Text(), nullable=True),
        sa.Column("entrypoint_url", sa.Text(), nullable=True),
        sa.Column("metadata_url", sa.Text(), nullable=True),
        sa.Column("audience", sa.String(length=255), nullable=True),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("client_secret_ciphertext", sa.Text(), nullable=True),
        sa.Column(
            "scopes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "attribute_mapping_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("certificate_pem", sa.Text(), nullable=True),
        sa.Column("login_hint_domain", sa.String(length=255), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_organization_sso_config_org"),
    )
    op.alter_column("organization_sso_configs", "provider_type", server_default=None)
    op.alter_column("organization_sso_configs", "is_enabled", server_default=None)
    op.alter_column("organization_sso_configs", "scopes_json", server_default=None)
    op.alter_column("organization_sso_configs", "attribute_mapping_json", server_default=None)
    op.alter_column("organization_sso_configs", "metadata_json", server_default=None)


def downgrade() -> None:
    op.drop_table("organization_sso_configs")

    op.drop_index("ix_user_mfa_credentials_user_enabled", table_name="user_mfa_credentials")
    op.drop_table("user_mfa_credentials")

    op.drop_index("ix_user_sessions_user_revoked", table_name="user_sessions")
    op.drop_index("ix_user_sessions_org_user", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_workspace_invites_org_status", table_name="workspace_invites")
    op.drop_index("ix_workspace_invites_email_status", table_name="workspace_invites")
    op.drop_table("workspace_invites")

    sso_provider_type.drop(op.get_bind(), checkfirst=True)
    mfa_method_type.drop(op.get_bind(), checkfirst=True)
    workspace_invite_status.drop(op.get_bind(), checkfirst=True)
