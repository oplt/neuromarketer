from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

OrgRoleValue = Literal["owner", "admin", "member", "viewer"]
ApiKeyStatusValue = Literal["active", "revoked"]
WorkspaceInviteStatusValue = Literal["pending", "accepted", "revoked", "expired"]
SsoProviderValue = Literal["oidc", "saml"]


class AccountPermissionsRead(BaseModel):
    can_manage_api_keys: bool
    can_manage_webhooks: bool
    can_manage_members: bool
    can_view_audit_logs: bool
    can_manage_invites: bool
    can_manage_sso: bool


class AccountWorkspaceStatsRead(BaseModel):
    member_count: int = 0
    project_count: int = 0
    active_api_key_count: int = 0
    active_webhook_count: int = 0
    completed_analysis_count: int = 0


class AccountApiKeyRead(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    status: ApiKeyStatusValue
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    scopes: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AccountWebhookRead(BaseModel):
    id: UUID
    url: str
    subscribed_events: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AccountMemberRead(BaseModel):
    membership_id: UUID
    user_id: UUID
    email: str
    full_name: str | None = None
    role: OrgRoleValue
    joined_at: datetime
    is_current_user: bool = False


class AccountAuditLogRead(BaseModel):
    id: UUID
    created_at: datetime
    action: str
    entity_type: str
    entity_id: UUID | None = None
    actor_email: str | None = None
    actor_full_name: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


class AccountInviteRead(BaseModel):
    id: UUID
    email: str
    role: OrgRoleValue
    status: WorkspaceInviteStatusValue
    token_prefix: str
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    invited_by_email: str | None = None
    invited_by_full_name: str | None = None
    accepted_by_email: str | None = None
    accepted_by_full_name: str | None = None
    created_at: datetime
    updated_at: datetime


class AccountUserSessionRead(BaseModel):
    id: UUID
    token_prefix: str
    user_agent: str | None = None
    ip_address: str | None = None
    last_seen_at: datetime
    expires_at: datetime
    idle_expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    is_current: bool = False
    created_at: datetime
    updated_at: datetime


class AccountSessionPolicyRead(BaseModel):
    absolute_ttl_minutes: int
    idle_ttl_minutes: int
    touch_interval_seconds: int


class AccountMfaStatusRead(BaseModel):
    is_enabled: bool = False
    method_type: str | None = None
    recovery_codes_remaining: int = 0
    pending_setup: bool = False
    last_used_at: datetime | None = None


class AccountSsoConfigRead(BaseModel):
    provider_type: SsoProviderValue = "oidc"
    is_enabled: bool = False
    issuer_url: str | None = None
    entrypoint_url: str | None = None
    metadata_url: str | None = None
    audience: str | None = None
    client_id: str | None = None
    has_client_secret: bool = False
    scopes: list[str] = Field(default_factory=list)
    attribute_mapping: dict[str, Any] = Field(default_factory=dict)
    certificate_pem: str | None = None
    login_hint_domain: str | None = None
    readiness_checks: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class AccountSecurityOverviewRead(BaseModel):
    session_policy: AccountSessionPolicyRead
    current_session_id: UUID | None = None
    sessions: list[AccountUserSessionRead] = Field(default_factory=list)
    mfa: AccountMfaStatusRead = Field(default_factory=AccountMfaStatusRead)
    invites: list[AccountInviteRead] = Field(default_factory=list)
    sso: AccountSsoConfigRead = Field(default_factory=AccountSsoConfigRead)
    available_sso_providers: list[SsoProviderValue] = Field(
        default_factory=lambda: ["oidc", "saml"]
    )


class AccountControlCenterRead(BaseModel):
    workspace_name: str
    workspace_slug: str
    billing_email: str | None = None
    current_user_role: OrgRoleValue
    permissions: AccountPermissionsRead
    stats: AccountWorkspaceStatsRead
    available_api_key_scopes: list[str] = Field(default_factory=list)
    available_webhook_events: list[str] = Field(default_factory=list)
    api_keys: list[AccountApiKeyRead] = Field(default_factory=list)
    webhooks: list[AccountWebhookRead] = Field(default_factory=list)
    members: list[AccountMemberRead] = Field(default_factory=list)
    audit_logs: list[AccountAuditLogRead] = Field(default_factory=list)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list, max_length=16)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyCreateResponse(BaseModel):
    api_key: AccountApiKeyRead
    token: str


class ApiKeyRotateResponse(BaseModel):
    rotated_from: AccountApiKeyRead
    api_key: AccountApiKeyRead
    token: str


class WebhookCreateRequest(BaseModel):
    url: HttpUrl
    subscribed_events: list[str] = Field(default_factory=list, max_length=16)
    is_active: bool = True


class WebhookUpdateRequest(BaseModel):
    url: HttpUrl | None = None
    subscribed_events: list[str] | None = Field(default=None, max_length=16)
    is_active: bool | None = None


class WebhookSecretResponse(BaseModel):
    webhook: AccountWebhookRead
    signing_secret: str


class MemberRoleUpdateRequest(BaseModel):
    role: OrgRoleValue


class AccountInviteCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: OrgRoleValue = "viewer"
    expires_in_hours: int | None = Field(default=None, ge=1, le=24 * 90)


class AccountInviteCreateResponse(BaseModel):
    invite: AccountInviteRead
    invite_token: str
    invite_url: str


class AccountMfaSetupStartResponse(BaseModel):
    method_type: Literal["totp"] = "totp"
    secret: str
    otpauth_uri: str
    issuer: str


class AccountMfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)


class AccountMfaDisableRequest(BaseModel):
    code: str | None = Field(default=None, min_length=6, max_length=32)
    recovery_code: str | None = Field(default=None, min_length=6, max_length=32)


class AccountMfaRecoveryCodesResponse(BaseModel):
    recovery_codes: list[str] = Field(default_factory=list)
    status: AccountMfaStatusRead


class AccountSsoConfigUpsertRequest(BaseModel):
    provider_type: SsoProviderValue = "oidc"
    is_enabled: bool = False
    issuer_url: str | None = Field(default=None, max_length=2000)
    entrypoint_url: str | None = Field(default=None, max_length=2000)
    metadata_url: str | None = Field(default=None, max_length=2000)
    audience: str | None = Field(default=None, max_length=255)
    client_id: str | None = Field(default=None, max_length=255)
    client_secret: str | None = Field(default=None, max_length=2000)
    scopes: list[str] = Field(default_factory=list, max_length=16)
    attribute_mapping: dict[str, Any] = Field(default_factory=dict)
    certificate_pem: str | None = None
    login_hint_domain: str | None = Field(default=None, max_length=255)
