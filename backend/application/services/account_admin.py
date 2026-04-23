from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import ForbiddenAppError, NotFoundAppError, ValidationAppError
from backend.db.models import (
    ApiKey,
    ApiKeyStatus,
    AuditLog,
    InferenceJob,
    JobStatus,
    Organization,
    OrganizationMembership,
    OrgRole,
    Project,
    User,
    WebhookEndpoint,
)
from backend.schemas.account import (
    AccountApiKeyRead,
    AccountAuditLogRead,
    AccountControlCenterRead,
    AccountMemberRead,
    AccountPermissionsRead,
    AccountWebhookRead,
    AccountWorkspaceStatsRead,
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyRotateResponse,
    MemberRoleUpdateRequest,
    WebhookCreateRequest,
    WebhookSecretResponse,
    WebhookUpdateRequest,
)

AVAILABLE_API_KEY_SCOPES = [
    "analysis.read",
    "analysis.write",
    "comparison.read",
    "comparison.write",
    "settings.read",
    "settings.write",
    "webhooks.write",
    "admin",
]
AVAILABLE_WEBHOOK_EVENTS = [
    "analysis.job.completed",
    "analysis.job.failed",
    "analysis.comparison.created",
    "analysis.outcomes.imported",
    "settings.updated",
]
ADMIN_ROLES = {OrgRole.OWNER, OrgRole.ADMIN}


class AccountAdminApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_control_center(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
    ) -> AccountControlCenterRead:
        membership = await self._get_membership(organization_id=organization_id, user_id=user_id)
        organization = await self.session.get(Organization, organization_id)
        if organization is None:
            raise NotFoundAppError("Workspace not found.")

        permissions = self._build_permissions(membership.role)
        stats = await self._build_stats(organization_id=organization_id)
        api_keys = await self._list_api_keys(organization_id=organization_id)
        webhooks = await self._list_webhooks(organization_id=organization_id)
        members = await self._list_members(organization_id=organization_id, current_user_id=user_id)
        audit_logs = (
            await self._list_audit_logs(organization_id=organization_id)
            if permissions.can_view_audit_logs
            else []
        )

        return AccountControlCenterRead(
            workspace_name=organization.name,
            workspace_slug=organization.slug,
            billing_email=organization.billing_email,
            current_user_role=membership.role.value,
            permissions=permissions,
            stats=stats,
            available_api_key_scopes=AVAILABLE_API_KEY_SCOPES,
            available_webhook_events=AVAILABLE_WEBHOOK_EVENTS,
            api_keys=api_keys,
            webhooks=webhooks,
            members=members,
            audit_logs=audit_logs,
        )

    async def create_api_key(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        payload: ApiKeyCreateRequest,
    ) -> ApiKeyCreateResponse:
        membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_admin_role(membership.role, "create API keys")
        scopes = self._normalize_scopes(payload.scopes)
        token, key_prefix, key_hash = await self._generate_api_key_material()
        expires_at = (
            datetime.now(UTC) + timedelta(days=payload.expires_in_days)
            if payload.expires_in_days
            else None
        )

        api_key = ApiKey(
            organization_id=organization_id,
            name=payload.name.strip(),
            key_prefix=key_prefix,
            key_hash=key_hash,
            status=ApiKeyStatus.ACTIVE,
            last_used_at=None,
            expires_at=expires_at,
            scopes=scopes,
        )
        self.session.add(api_key)
        await self.session.flush()
        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="account.api_key.created",
            entity_type="api_key",
            entity_id=api_key.id,
            payload_json={
                "name": api_key.name,
                "key_prefix": api_key.key_prefix,
                "scopes": scopes,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        await self.session.commit()
        await self.session.refresh(api_key)
        return ApiKeyCreateResponse(api_key=self._build_api_key_read(api_key), token=token)

    async def revoke_api_key(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        api_key_id: UUID,
    ) -> AccountApiKeyRead:
        membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_admin_role(membership.role, "revoke API keys")
        api_key = await self._get_api_key(organization_id=organization_id, api_key_id=api_key_id)
        if api_key.status != ApiKeyStatus.REVOKED:
            api_key.status = ApiKeyStatus.REVOKED
            await self._append_audit_log(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="account.api_key.revoked",
                entity_type="api_key",
                entity_id=api_key.id,
                payload_json={"name": api_key.name, "key_prefix": api_key.key_prefix},
            )
            await self.session.commit()
            await self.session.refresh(api_key)
        return self._build_api_key_read(api_key)

    async def rotate_api_key(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        api_key_id: UUID,
    ) -> ApiKeyRotateResponse:
        membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_admin_role(membership.role, "rotate API keys")
        existing_key = await self._get_api_key(
            organization_id=organization_id, api_key_id=api_key_id
        )
        token, key_prefix, key_hash = await self._generate_api_key_material()

        existing_key.status = ApiKeyStatus.REVOKED
        new_key = ApiKey(
            organization_id=organization_id,
            name=existing_key.name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            status=ApiKeyStatus.ACTIVE,
            last_used_at=None,
            expires_at=existing_key.expires_at,
            scopes=list(existing_key.scopes or []),
        )
        self.session.add(new_key)
        await self.session.flush()
        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="account.api_key.rotated",
            entity_type="api_key",
            entity_id=new_key.id,
            payload_json={
                "rotated_from_id": str(existing_key.id),
                "name": new_key.name,
                "key_prefix": new_key.key_prefix,
                "scopes": list(new_key.scopes or []),
            },
        )
        await self.session.commit()
        await self.session.refresh(existing_key)
        await self.session.refresh(new_key)
        return ApiKeyRotateResponse(
            rotated_from=self._build_api_key_read(existing_key),
            api_key=self._build_api_key_read(new_key),
            token=token,
        )

    async def create_webhook(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        payload: WebhookCreateRequest,
    ) -> WebhookSecretResponse:
        membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_admin_role(membership.role, "create webhook endpoints")
        subscribed_events = self._normalize_webhook_events(payload.subscribed_events)
        signing_secret, secret_hash = self._generate_webhook_secret_material()

        webhook = WebhookEndpoint(
            organization_id=organization_id,
            url=str(payload.url),
            secret_hash=secret_hash,
            subscribed_events=subscribed_events,
            is_active=payload.is_active,
        )
        self.session.add(webhook)
        await self.session.flush()
        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="account.webhook.created",
            entity_type="webhook_endpoint",
            entity_id=webhook.id,
            payload_json={
                "url": webhook.url,
                "subscribed_events": subscribed_events,
                "is_active": webhook.is_active,
            },
        )
        await self.session.commit()
        await self.session.refresh(webhook)
        return WebhookSecretResponse(
            webhook=self._build_webhook_read(webhook),
            signing_secret=signing_secret,
        )

    async def update_webhook(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        webhook_id: UUID,
        payload: WebhookUpdateRequest,
    ) -> AccountWebhookRead:
        membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_admin_role(membership.role, "update webhook endpoints")
        webhook = await self._get_webhook(organization_id=organization_id, webhook_id=webhook_id)

        if "url" in payload.model_fields_set and payload.url is not None:
            webhook.url = str(payload.url)
        if (
            "subscribed_events" in payload.model_fields_set
            and payload.subscribed_events is not None
        ):
            webhook.subscribed_events = self._normalize_webhook_events(payload.subscribed_events)
        if "is_active" in payload.model_fields_set and payload.is_active is not None:
            webhook.is_active = payload.is_active

        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="account.webhook.updated",
            entity_type="webhook_endpoint",
            entity_id=webhook.id,
            payload_json={
                "url": webhook.url,
                "subscribed_events": list(webhook.subscribed_events or []),
                "is_active": webhook.is_active,
            },
        )
        await self.session.commit()
        await self.session.refresh(webhook)
        return self._build_webhook_read(webhook)

    async def rotate_webhook_secret(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        webhook_id: UUID,
    ) -> WebhookSecretResponse:
        membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_admin_role(membership.role, "rotate webhook secrets")
        webhook = await self._get_webhook(organization_id=organization_id, webhook_id=webhook_id)
        signing_secret, secret_hash = self._generate_webhook_secret_material()
        webhook.secret_hash = secret_hash

        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="account.webhook.secret_rotated",
            entity_type="webhook_endpoint",
            entity_id=webhook.id,
            payload_json={"url": webhook.url},
        )
        await self.session.commit()
        await self.session.refresh(webhook)
        return WebhookSecretResponse(
            webhook=self._build_webhook_read(webhook),
            signing_secret=signing_secret,
        )

    async def update_member_role(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        membership_id: UUID,
        payload: MemberRoleUpdateRequest,
    ) -> AccountMemberRead:
        actor_membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_owner_role(actor_membership.role, "change member roles")

        result = await self.session.execute(
            select(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.id == membership_id,
                OrganizationMembership.organization_id == organization_id,
            )
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            raise NotFoundAppError("Workspace member not found.")
        membership, user = row
        next_role = OrgRole(payload.role)
        if membership.role == OrgRole.OWNER and next_role != OrgRole.OWNER:
            owner_count = await self.session.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.role == OrgRole.OWNER,
                )
            )
            if int(owner_count or 0) <= 1:
                raise ValidationAppError("At least one workspace owner must remain assigned.")

        previous_role = membership.role
        membership.role = next_role
        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="account.membership.role_updated",
            entity_type="organization_membership",
            entity_id=membership.id,
            payload_json={
                "user_id": str(user.id),
                "email": user.email,
                "previous_role": previous_role.value,
                "next_role": next_role.value,
            },
        )
        await self.session.commit()
        await self.session.refresh(membership)
        return self._build_member_read(
            membership=membership, user=user, current_user_id=actor_user_id
        )

    async def _get_membership(
        self, *, organization_id: UUID, user_id: UUID
    ) -> OrganizationMembership:
        result = await self.session.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
            )
            .limit(1)
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            raise NotFoundAppError("Workspace membership not found.")
        return membership

    async def _get_api_key(self, *, organization_id: UUID, api_key_id: UUID) -> ApiKey:
        result = await self.session.execute(
            select(ApiKey)
            .where(ApiKey.id == api_key_id, ApiKey.organization_id == organization_id)
            .limit(1)
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            raise NotFoundAppError("API key not found.")
        return api_key

    async def _get_webhook(self, *, organization_id: UUID, webhook_id: UUID) -> WebhookEndpoint:
        result = await self.session.execute(
            select(WebhookEndpoint)
            .where(
                WebhookEndpoint.id == webhook_id, WebhookEndpoint.organization_id == organization_id
            )
            .limit(1)
        )
        webhook = result.scalar_one_or_none()
        if webhook is None:
            raise NotFoundAppError("Webhook endpoint not found.")
        return webhook

    async def _build_stats(self, *, organization_id: UUID) -> AccountWorkspaceStatsRead:
        member_count = int(
            await self.session.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id == organization_id
                )
            )
            or 0
        )
        project_count = int(
            await self.session.scalar(
                select(func.count(Project.id)).where(Project.organization_id == organization_id)
            )
            or 0
        )
        active_api_key_count = int(
            await self.session.scalar(
                select(func.count(ApiKey.id)).where(
                    ApiKey.organization_id == organization_id,
                    ApiKey.status == ApiKeyStatus.ACTIVE,
                )
            )
            or 0
        )
        active_webhook_count = int(
            await self.session.scalar(
                select(func.count(WebhookEndpoint.id)).where(
                    WebhookEndpoint.organization_id == organization_id,
                    WebhookEndpoint.is_active.is_(True),
                )
            )
            or 0
        )
        completed_analysis_count = int(
            await self.session.scalar(
                select(func.count(InferenceJob.id))
                .join(Project, Project.id == InferenceJob.project_id)
                .where(
                    Project.organization_id == organization_id,
                    InferenceJob.status == JobStatus.SUCCEEDED,
                )
            )
            or 0
        )
        return AccountWorkspaceStatsRead(
            member_count=member_count,
            project_count=project_count,
            active_api_key_count=active_api_key_count,
            active_webhook_count=active_webhook_count,
            completed_analysis_count=completed_analysis_count,
        )

    async def _list_api_keys(self, *, organization_id: UUID) -> list[AccountApiKeyRead]:
        result = await self.session.execute(
            select(ApiKey)
            .where(ApiKey.organization_id == organization_id)
            .order_by(desc(ApiKey.created_at))
        )
        return [self._build_api_key_read(item) for item in result.scalars().all()]

    async def _list_webhooks(self, *, organization_id: UUID) -> list[AccountWebhookRead]:
        result = await self.session.execute(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.organization_id == organization_id)
            .order_by(desc(WebhookEndpoint.created_at))
        )
        return [self._build_webhook_read(item) for item in result.scalars().all()]

    async def _list_members(
        self,
        *,
        organization_id: UUID,
        current_user_id: UUID,
    ) -> list[AccountMemberRead]:
        result = await self.session.execute(
            select(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(OrganizationMembership.organization_id == organization_id)
            .order_by(OrganizationMembership.created_at.asc(), User.email.asc())
        )
        return [
            self._build_member_read(
                membership=membership, user=user, current_user_id=current_user_id
            )
            for membership, user in result.all()
        ]

    async def _list_audit_logs(
        self, *, organization_id: UUID, limit: int = 24
    ) -> list[AccountAuditLogRead]:
        result = await self.session.execute(
            select(AuditLog, User)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .where(AuditLog.organization_id == organization_id)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        return [
            AccountAuditLogRead(
                id=audit_log.id,
                created_at=audit_log.created_at,
                action=audit_log.action,
                entity_type=audit_log.entity_type,
                entity_id=audit_log.entity_id,
                actor_email=user.email if user is not None else None,
                actor_full_name=user.full_name if user is not None else None,
                payload_json=dict(audit_log.payload_json or {}),
            )
            for audit_log, user in result.all()
        ]

    async def _append_audit_log(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        payload_json: dict,
    ) -> None:
        self.session.add(
            AuditLog(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )

    def _build_permissions(self, role: OrgRole) -> AccountPermissionsRead:
        return AccountPermissionsRead(
            can_manage_api_keys=role in ADMIN_ROLES,
            can_manage_webhooks=role in ADMIN_ROLES,
            can_manage_members=role == OrgRole.OWNER,
            can_view_audit_logs=role in ADMIN_ROLES,
            can_manage_invites=role in ADMIN_ROLES,
            can_manage_sso=role in ADMIN_ROLES,
        )

    def _build_api_key_read(self, api_key: ApiKey) -> AccountApiKeyRead:
        return AccountApiKeyRead(
            id=api_key.id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            status=api_key.status.value,
            last_used_at=api_key.last_used_at,
            expires_at=api_key.expires_at,
            scopes=list(api_key.scopes or []),
            created_at=api_key.created_at,
            updated_at=api_key.updated_at,
        )

    def _build_webhook_read(self, webhook: WebhookEndpoint) -> AccountWebhookRead:
        return AccountWebhookRead(
            id=webhook.id,
            url=webhook.url,
            subscribed_events=list(webhook.subscribed_events or []),
            is_active=webhook.is_active,
            created_at=webhook.created_at,
            updated_at=webhook.updated_at,
        )

    def _build_member_read(
        self,
        *,
        membership: OrganizationMembership,
        user: User,
        current_user_id: UUID,
    ) -> AccountMemberRead:
        return AccountMemberRead(
            membership_id=membership.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role.value,
            joined_at=membership.created_at,
            is_current_user=user.id == current_user_id,
        )

    async def _generate_api_key_material(self) -> tuple[str, str, str]:
        while True:
            token = f"nmk_{secrets.token_urlsafe(24)}"
            key_prefix = token[:14]
            key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            exists = await self.session.scalar(
                select(func.count(ApiKey.id)).where(
                    (ApiKey.key_prefix == key_prefix) | (ApiKey.key_hash == key_hash)
                )
            )
            if int(exists or 0) == 0:
                return token, key_prefix, key_hash

    def _generate_webhook_secret_material(self) -> tuple[str, str]:
        signing_secret = f"whsec_{secrets.token_urlsafe(32)}"
        secret_hash = hashlib.sha256(signing_secret.encode("utf-8")).hexdigest()
        return signing_secret, secret_hash

    def _normalize_scopes(self, scopes: list[str]) -> list[str]:
        cleaned_scopes = sorted({scope.strip() for scope in scopes if scope.strip()})
        if not cleaned_scopes:
            return ["analysis.read"]
        unsupported = [scope for scope in cleaned_scopes if scope not in AVAILABLE_API_KEY_SCOPES]
        if unsupported:
            raise ValidationAppError(f"Unsupported API key scopes: {', '.join(unsupported)}")
        return cleaned_scopes

    def _normalize_webhook_events(self, subscribed_events: list[str]) -> list[str]:
        cleaned_events = sorted({event.strip() for event in subscribed_events if event.strip()})
        if not cleaned_events:
            return ["analysis.job.completed"]
        unsupported = [event for event in cleaned_events if event not in AVAILABLE_WEBHOOK_EVENTS]
        if unsupported:
            raise ValidationAppError(f"Unsupported webhook events: {', '.join(unsupported)}")
        return cleaned_events

    def _require_admin_role(self, role: OrgRole, action: str) -> None:
        if role not in ADMIN_ROLES:
            raise ForbiddenAppError(f"You do not have permission to {action} in this workspace.")

    def _require_owner_role(self, role: OrgRole, action: str) -> None:
        if role != OrgRole.OWNER:
            raise ForbiddenAppError(f"Only workspace owners can {action}.")
