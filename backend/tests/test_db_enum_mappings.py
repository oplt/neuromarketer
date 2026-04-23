from backend.db.models import (
    CollaborationReview,
    OrganizationSsoConfig,
    UserMfaCredential,
    WorkspaceInvite,
)


def test_auth_related_enums_bind_lowercase_database_values() -> None:
    assert WorkspaceInvite.__table__.c.status.type.enums == [
        "pending",
        "accepted",
        "revoked",
        "expired",
    ]
    assert UserMfaCredential.__table__.c.method_type.type.enums == ["totp"]
    assert OrganizationSsoConfig.__table__.c.provider_type.type.enums == ["oidc", "saml"]


def test_collaboration_enums_bind_lowercase_database_values() -> None:
    assert CollaborationReview.__table__.c.entity_type.type.enums == [
        "analysis_job",
        "analysis_comparison",
    ]
    assert CollaborationReview.__table__.c.status.type.enums == [
        "draft",
        "in_review",
        "changes_requested",
        "approved",
    ]
