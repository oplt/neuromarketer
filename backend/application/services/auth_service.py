from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.mfa_service import MFAService
from backend.core.config import settings
from backend.core.exceptions import (
    ConflictAppError,
    ForbiddenAppError,
    NotFoundAppError,
    UnauthorizedAppError,
    ValidationAppError,
)
from backend.core.security import (
    build_token_prefix,
    create_mfa_challenge_token,
    create_session_token,
    hash_password,
    hash_token,
    seal_secret,
    verify_mfa_challenge_token,
    verify_password,
)
from backend.db.models import (
    AuditLog,
    Organization,
    OrganizationMembership,
    OrganizationSsoConfig,
    OrgRole,
    Project,
    SsoProviderType,
    User,
    UserMfaCredential,
    UserSession,
    WorkspaceInvite,
    WorkspaceInviteStatus,
)
from backend.db.repositories import crud
from backend.schemas.account import (
    AccountInviteCreateRequest,
    AccountInviteCreateResponse,
    AccountInviteRead,
    AccountMfaConfirmRequest,
    AccountMfaDisableRequest,
    AccountMfaRecoveryCodesResponse,
    AccountMfaSetupStartResponse,
    AccountMfaStatusRead,
    AccountSecurityOverviewRead,
    AccountSessionPolicyRead,
    AccountSsoConfigRead,
    AccountSsoConfigUpsertRequest,
    AccountUserSessionRead,
)
from backend.schemas.schemas import (
    AcceptInviteRequest,
    AuthResponse,
    InvitePreviewRead,
    MfaChallengeVerifyRequest,
    SignInRequest,
    SignUpRequest,
)

ADMIN_ROLES = {OrgRole.OWNER, OrgRole.ADMIN}
AVAILABLE_MFA_METHODS = ["totp", "recovery_code"]
AVAILABLE_SSO_PROVIDERS = ["oidc", "saml"]


@dataclass(slots=True)
class AuthClientMetadata:
    user_agent: str | None = None
    ip_address: str | None = None


class AuthApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._mfa = MFAService(session)

    async def sign_up(self, *, payload: SignUpRequest, client: AuthClientMetadata) -> AuthResponse:
        existing_user = await crud.get_user_by_email(self.session, payload.email)
        if existing_user is not None:
            raise ConflictAppError("An account with this email already exists.")

        user, organization, default_project = await crud.create_user_with_workspace(
            self.session,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
        )
        session_record, session_token = await self._issue_session(
            user=user,
            organization=organization,
            client=client,
            source="signup",
        )
        await self._append_audit_log(
            organization_id=organization.id,
            actor_user_id=user.id,
            action="auth.signup",
            entity_type="user",
            entity_id=user.id,
            payload_json={"email": user.email, "session_id": str(session_record.id)},
        )
        await self.session.commit()
        return self._build_auth_response(
            message="Account created successfully.",
            user=user,
            organization=organization,
            default_project=default_project,
            session_token=session_token,
        )

    async def sign_in(self, *, payload: SignInRequest, client: AuthClientMetadata) -> AuthResponse:
        user = await crud.get_user_by_email(self.session, payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise UnauthorizedAppError("Invalid email or password.")
        if not user.is_active or user.deleted_at is not None:
            raise UnauthorizedAppError("Your account is disabled.")

        organization = await crud.get_primary_organization_for_user(self.session, user.id)
        if organization is None:
            raise UnauthorizedAppError("No workspace is available for this account.")
        default_project = await crud.get_or_create_default_project_for_organization(
            self.session,
            organization_id=organization.id,
            created_by_user_id=user.id,
        )
        base_response = self._build_auth_response(
            message="",
            user=user,
            organization=organization,
            default_project=default_project,
        )

        mfa_credential = await self._get_mfa_credential(user_id=user.id)
        if mfa_credential and mfa_credential.is_enabled and mfa_credential.secret_ciphertext:
            challenge_token = create_mfa_challenge_token(
                user_id=user.id,
                organization_id=organization.id,
                email=user.email,
                expires_at_epoch=int(
                    (
                        self._now() + timedelta(minutes=max(1, settings.mfa_challenge_ttl_minutes))
                    ).timestamp()
                ),
            )
            return AuthResponse(
                message="Multi-factor authentication is required.",
                user=base_response.user,
                organization=base_response.organization,
                default_project=base_response.default_project,
                requires_mfa=True,
                mfa_challenge_token=challenge_token,
                available_mfa_methods=list(AVAILABLE_MFA_METHODS),
            )

        session_record, session_token = await self._issue_session(
            user=user,
            organization=organization,
            client=client,
            source="signin",
        )
        await self._append_audit_log(
            organization_id=organization.id,
            actor_user_id=user.id,
            action="auth.signin",
            entity_type="user_session",
            entity_id=session_record.id,
            payload_json={"user_id": str(user.id)},
        )
        await self.session.commit()
        return self._build_auth_response(
            message="Signed in successfully.",
            user=user,
            organization=organization,
            default_project=default_project,
            session_token=session_token,
        )

    async def verify_mfa_challenge(
        self,
        *,
        payload: MfaChallengeVerifyRequest,
        client: AuthClientMetadata,
    ) -> AuthResponse:
        claims = verify_mfa_challenge_token(payload.challenge_token)
        user = await crud.get_user_by_id(self.session, claims.user_id)
        if user is None or user.email.strip().lower() != claims.email:
            raise UnauthorizedAppError("The MFA challenge is invalid or has expired.")
        organization = await crud.get_organization_for_user(
            self.session,
            user_id=user.id,
            organization_id=claims.organization_id,
        )
        if organization is None or not organization.is_active:
            raise UnauthorizedAppError("The MFA challenge is invalid or has expired.")

        credential = await self._get_mfa_credential(user_id=user.id)
        if credential is None or not credential.is_enabled or not credential.secret_ciphertext:
            raise UnauthorizedAppError(
                "Multi-factor authentication is not configured for this account."
            )

        await self._verify_mfa_assertion(
            credential=credential, code=payload.code, recovery_code=payload.recovery_code
        )
        credential.last_used_at = self._now()
        default_project = await crud.get_or_create_default_project_for_organization(
            self.session,
            organization_id=organization.id,
            created_by_user_id=user.id,
        )
        session_record, session_token = await self._issue_session(
            user=user,
            organization=organization,
            client=client,
            source="mfa_signin",
        )
        await self._append_audit_log(
            organization_id=organization.id,
            actor_user_id=user.id,
            action="auth.signin.mfa_verified",
            entity_type="user_session",
            entity_id=session_record.id,
            payload_json={"user_id": str(user.id)},
        )
        await self.session.commit()
        return self._build_auth_response(
            message="Signed in successfully.",
            user=user,
            organization=organization,
            default_project=default_project,
            session_token=session_token,
        )

    async def sign_out(self, *, session_id: UUID, user_id: UUID, organization_id: UUID) -> None:
        session_record = await self.session.get(UserSession, session_id)
        if (
            session_record is None
            or session_record.user_id != user_id
            or session_record.organization_id != organization_id
        ):
            return
        if session_record.revoked_at is None:
            session_record.revoked_at = self._now()
            session_record.revoked_reason = "signed_out"
            await self._append_audit_log(
                organization_id=organization_id,
                actor_user_id=user_id,
                action="auth.signout",
                entity_type="user_session",
                entity_id=session_record.id,
                payload_json={"token_prefix": session_record.token_prefix},
            )
            await self.session.commit()

    async def get_invite_preview(self, *, invite_token: str) -> InvitePreviewRead:
        invite, organization = await self._resolve_invite(
            invite_token=invite_token, require_pending=True
        )
        return InvitePreviewRead(
            workspace_name=organization.name,
            workspace_slug=organization.slug,
            email=invite.email,
            role=invite.role.value,
            expires_at=invite.expires_at,
        )

    async def accept_invite(
        self, *, payload: AcceptInviteRequest, client: AuthClientMetadata
    ) -> AuthResponse:
        invite, organization = await self._resolve_invite(
            invite_token=payload.invite_token, require_pending=True
        )
        existing_user = await crud.get_user_by_email(self.session, invite.email)
        if existing_user is not None:
            if not verify_password(payload.password, existing_user.password_hash):
                raise UnauthorizedAppError("The password does not match the invited account.")
            user = existing_user
        else:
            cleaned_name = payload.full_name.strip()
            name_parts = cleaned_name.split(maxsplit=1)
            user = User(
                email=invite.email,
                first_name=name_parts[0] if name_parts else None,
                last_name=name_parts[1] if len(name_parts) > 1 else None,
                password_hash=hash_password(payload.password),
                is_active=True,
                is_verified=False,
            )
            self.session.add(user)
            await self.session.flush()

        membership = await crud.get_membership_for_user(
            self.session,
            user_id=user.id,
            organization_id=organization.id,
        )
        if membership is None:
            membership = OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=invite.role,
            )
            self.session.add(membership)
            await self.session.flush()

        invite.status = WorkspaceInviteStatus.ACCEPTED
        invite.accepted_at = self._now()
        invite.accepted_by_user_id = user.id
        default_project = await crud.get_or_create_default_project_for_organization(
            self.session,
            organization_id=organization.id,
            created_by_user_id=user.id,
        )
        base_response = self._build_auth_response(
            message="",
            user=user,
            organization=organization,
            default_project=default_project,
        )
        mfa_credential = await self._get_mfa_credential(user_id=user.id)
        if mfa_credential and mfa_credential.is_enabled and mfa_credential.secret_ciphertext:
            await self._append_audit_log(
                organization_id=organization.id,
                actor_user_id=user.id,
                action="auth.invite.accepted",
                entity_type="workspace_invite",
                entity_id=invite.id,
                payload_json={"email": invite.email, "mfa_required": True},
            )
            await self.session.commit()
            return AuthResponse(
                message="Invite accepted. Verify your MFA code to continue.",
                user=base_response.user,
                organization=base_response.organization,
                default_project=base_response.default_project,
                requires_mfa=True,
                mfa_challenge_token=create_mfa_challenge_token(
                    user_id=user.id,
                    organization_id=organization.id,
                    email=user.email,
                    expires_at_epoch=int(
                        (
                            self._now()
                            + timedelta(minutes=max(1, settings.mfa_challenge_ttl_minutes))
                        ).timestamp()
                    ),
                ),
                available_mfa_methods=list(AVAILABLE_MFA_METHODS),
            )
        session_record, session_token = await self._issue_session(
            user=user,
            organization=organization,
            client=client,
            source="invite_accept",
        )
        await self._append_audit_log(
            organization_id=organization.id,
            actor_user_id=user.id,
            action="auth.invite.accepted",
            entity_type="workspace_invite",
            entity_id=invite.id,
            payload_json={"email": invite.email, "session_id": str(session_record.id)},
        )
        await self.session.commit()
        return self._build_auth_response(
            message="Invite accepted successfully.",
            user=user,
            organization=organization,
            default_project=default_project,
            session_token=session_token,
        )

    async def get_security_overview(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        current_session_id: UUID | None,
    ) -> AccountSecurityOverviewRead:
        membership = await self._get_membership(organization_id=organization_id, user_id=user_id)
        sessions = await self._list_user_sessions(
            organization_id=organization_id,
            user_id=user_id,
            current_session_id=current_session_id,
        )
        mfa = await self._build_mfa_status(user_id=user_id)
        invites = (
            await self._list_invites(organization_id=organization_id)
            if membership.role in ADMIN_ROLES
            else []
        )
        sso = await self._get_sso_config(organization_id=organization_id)
        return AccountSecurityOverviewRead(
            session_policy=AccountSessionPolicyRead(
                absolute_ttl_minutes=settings.session_ttl_minutes,
                idle_ttl_minutes=settings.session_idle_ttl_minutes,
                touch_interval_seconds=settings.session_touch_interval_seconds,
            ),
            current_session_id=current_session_id,
            sessions=sessions,
            mfa=mfa,
            invites=invites,
            sso=sso,
            available_sso_providers=list(AVAILABLE_SSO_PROVIDERS),
        )

    async def start_mfa_setup(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        email: str,
    ) -> AccountMfaSetupStartResponse:
        return await self._mfa.start_mfa_setup(
            organization_id=organization_id, user_id=user_id, email=email
        )

    async def confirm_mfa_setup(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        payload: AccountMfaConfirmRequest,
    ) -> AccountMfaRecoveryCodesResponse:
        return await self._mfa.confirm_mfa_setup(
            organization_id=organization_id, user_id=user_id, payload=payload
        )

    async def disable_mfa(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        payload: AccountMfaDisableRequest,
    ) -> AccountMfaStatusRead:
        return await self._mfa.disable_mfa(
            organization_id=organization_id, user_id=user_id, payload=payload
        )

    async def regenerate_mfa_recovery_codes(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        payload: AccountMfaDisableRequest,
    ) -> AccountMfaRecoveryCodesResponse:
        return await self._mfa.regenerate_mfa_recovery_codes(
            organization_id=organization_id, user_id=user_id, payload=payload
        )

    async def revoke_session(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        session_id: UUID,
    ) -> AccountUserSessionRead:
        await self._get_membership(organization_id=organization_id, user_id=user_id)
        session_record = await self.session.get(UserSession, session_id)
        if (
            session_record is None
            or session_record.organization_id != organization_id
            or session_record.user_id != user_id
        ):
            raise NotFoundAppError("Session not found.")
        if session_record.revoked_at is None:
            session_record.revoked_at = self._now()
            session_record.revoked_reason = "user_revoked"
            await self._append_audit_log(
                organization_id=organization_id,
                actor_user_id=user_id,
                action="auth.session.revoked",
                entity_type="user_session",
                entity_id=session_record.id,
                payload_json={"token_prefix": session_record.token_prefix},
            )
            await self.session.commit()
        return self._build_session_read(session_record=session_record, current_session_id=None)

    async def create_invite(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        payload: AccountInviteCreateRequest,
    ) -> AccountInviteCreateResponse:
        membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_admin_role(membership.role, "create invites")
        normalized_email = payload.email.strip().lower()

        existing_pending = await self.session.execute(
            select(WorkspaceInvite)
            .where(
                WorkspaceInvite.organization_id == organization_id,
                WorkspaceInvite.email == normalized_email,
                WorkspaceInvite.status == WorkspaceInviteStatus.PENDING,
            )
            .order_by(desc(WorkspaceInvite.created_at))
            .limit(1)
        )
        current_pending = existing_pending.scalar_one_or_none()
        if current_pending is not None and current_pending.expires_at > self._now():
            raise ValidationAppError("There is already a pending invite for this email.")

        raw_token = f"nmi_{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"
        expires_at = self._now() + timedelta(
            hours=payload.expires_in_hours or settings.invite_ttl_hours
        )
        invite = WorkspaceInvite(
            organization_id=organization_id,
            invited_by_user_id=actor_user_id,
            email=normalized_email,
            role=OrgRole(payload.role),
            token_prefix=build_token_prefix(raw_token),
            token_hash=hash_token(raw_token),
            status=WorkspaceInviteStatus.PENDING,
            expires_at=expires_at,
            metadata_json={},
        )
        self.session.add(invite)
        await self.session.flush()
        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="auth.invite.created",
            entity_type="workspace_invite",
            entity_id=invite.id,
            payload_json={
                "email": normalized_email,
                "role": payload.role,
                "expires_at": expires_at.isoformat(),
            },
        )
        await self.session.commit()
        return AccountInviteCreateResponse(
            invite=await self._build_invite_read(invite),
            invite_token=raw_token,
            invite_url=f"/?invite={raw_token}",
        )

    async def revoke_invite(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        invite_id: UUID,
    ) -> AccountInviteRead:
        membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_admin_role(membership.role, "revoke invites")
        invite = await self.session.get(WorkspaceInvite, invite_id)
        if invite is None or invite.organization_id != organization_id:
            raise NotFoundAppError("Invite not found.")
        if invite.status == WorkspaceInviteStatus.PENDING:
            invite.status = WorkspaceInviteStatus.REVOKED
            invite.revoked_at = self._now()
            await self._append_audit_log(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="auth.invite.revoked",
                entity_type="workspace_invite",
                entity_id=invite.id,
                payload_json={"email": invite.email},
            )
            await self.session.commit()
        return await self._build_invite_read(invite)

    async def upsert_sso_config(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        payload: AccountSsoConfigUpsertRequest,
    ) -> AccountSsoConfigRead:
        membership = await self._get_membership(
            organization_id=organization_id, user_id=actor_user_id
        )
        self._require_admin_role(membership.role, "manage SSO configuration")

        result = await self.session.execute(
            select(OrganizationSsoConfig)
            .where(OrganizationSsoConfig.organization_id == organization_id)
            .limit(1)
        )
        config = result.scalar_one_or_none()
        if config is None:
            config = OrganizationSsoConfig(
                organization_id=organization_id, updated_by_user_id=actor_user_id
            )
            self.session.add(config)
            await self.session.flush()

        config.provider_type = SsoProviderType(payload.provider_type)
        config.is_enabled = payload.is_enabled
        config.issuer_url = self._clean_optional(payload.issuer_url)
        config.entrypoint_url = self._clean_optional(payload.entrypoint_url)
        config.metadata_url = self._clean_optional(payload.metadata_url)
        config.audience = self._clean_optional(payload.audience)
        config.client_id = self._clean_optional(payload.client_id)
        if "client_secret" in payload.model_fields_set:
            cleaned_secret = self._clean_optional(payload.client_secret)
            config.client_secret_ciphertext = (
                seal_secret(cleaned_secret) if cleaned_secret else None
            )
        config.scopes_json = sorted({item.strip() for item in payload.scopes if item.strip()})
        config.attribute_mapping_json = dict(payload.attribute_mapping or {})
        config.certificate_pem = self._clean_optional(payload.certificate_pem)
        config.login_hint_domain = self._clean_optional(payload.login_hint_domain)
        config.updated_by_user_id = actor_user_id

        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="auth.sso.updated",
            entity_type="organization_sso_config",
            entity_id=config.id,
            payload_json={
                "provider_type": config.provider_type.value,
                "is_enabled": config.is_enabled,
                "login_hint_domain": config.login_hint_domain,
            },
        )
        await self.session.commit()
        return await self._get_sso_config(organization_id=organization_id)

    async def validate_session_token(
        self,
        *,
        session_id: UUID,
        token: str,
        user_id: UUID,
        organization_id: UUID,
    ) -> UserSession:
        session_record = await self.session.get(UserSession, session_id)
        if session_record is None:
            raise UnauthorizedAppError("Authentication is required.")
        if session_record.user_id != user_id or session_record.organization_id != organization_id:
            raise UnauthorizedAppError("Authentication is required.")
        if session_record.revoked_at is not None:
            raise UnauthorizedAppError("Your session is no longer active. Sign in again.")
        if session_record.token_hash != hash_token(token):
            raise UnauthorizedAppError("Authentication is required.")

        now = self._now()
        if session_record.expires_at <= now:
            session_record.revoked_at = now
            session_record.revoked_reason = "expired"
            await self.session.commit()
            raise UnauthorizedAppError("Your session has expired. Sign in again.")
        if session_record.idle_expires_at <= now:
            session_record.revoked_at = now
            session_record.revoked_reason = "idle_timeout"
            await self.session.commit()
            raise UnauthorizedAppError("Your session expired due to inactivity. Sign in again.")

        touch_cutoff = now - timedelta(seconds=max(1, settings.session_touch_interval_seconds))
        if session_record.last_seen_at <= touch_cutoff:
            session_record.last_seen_at = now
            session_record.idle_expires_at = now + timedelta(
                minutes=max(1, settings.session_idle_ttl_minutes)
            )
            await self.session.commit()
        return session_record

    async def _issue_session(
        self,
        *,
        user: User,
        organization: Organization,
        client: AuthClientMetadata,
        source: str,
    ) -> tuple[UserSession, str]:
        issued_at = self._now()
        expires_at = issued_at + timedelta(minutes=max(1, settings.session_ttl_minutes))
        idle_expires_at = issued_at + timedelta(minutes=max(1, settings.session_idle_ttl_minutes))
        session_id = uuid.uuid4()
        session_token = create_session_token(
            user_id=user.id,
            organization_id=organization.id,
            email=user.email,
            session_id=session_id,
            expires_at_epoch=int(expires_at.timestamp()),
        )
        session_record = UserSession(
            id=session_id,
            organization_id=organization.id,
            user_id=user.id,
            session_family_id=uuid.uuid4(),
            token_prefix=build_token_prefix(session_token),
            token_hash=hash_token(session_token),
            user_agent=self._clean_optional(client.user_agent),
            ip_address=self._clean_optional(client.ip_address),
            last_seen_at=issued_at,
            expires_at=expires_at,
            idle_expires_at=idle_expires_at,
            metadata_json={"source": source},
        )
        self.session.add(session_record)
        await self.session.flush()
        return session_record, session_token

    async def _verify_mfa_assertion(
        self,
        *,
        credential: UserMfaCredential,
        code: str | None,
        recovery_code: str | None,
    ) -> None:
        await self._mfa.verify_mfa_assertion_for_credential(
            credential=credential, code=code, recovery_code=recovery_code
        )

    async def _resolve_invite(
        self,
        *,
        invite_token: str,
        require_pending: bool,
    ) -> tuple[WorkspaceInvite, Organization]:
        invite_hash = hash_token(invite_token)
        result = await self.session.execute(
            select(WorkspaceInvite, Organization)
            .join(Organization, Organization.id == WorkspaceInvite.organization_id)
            .where(WorkspaceInvite.token_hash == invite_hash)
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            raise NotFoundAppError("Invite not found.")
        invite, organization = row
        if invite.status == WorkspaceInviteStatus.PENDING and invite.expires_at <= self._now():
            invite.status = WorkspaceInviteStatus.EXPIRED
            await self.session.commit()
        if require_pending and invite.status != WorkspaceInviteStatus.PENDING:
            raise ValidationAppError("This invite is no longer active.")
        if require_pending and invite.expires_at <= self._now():
            raise ValidationAppError("This invite has expired.")
        return invite, organization

    async def _get_membership(
        self, *, organization_id: UUID, user_id: UUID
    ) -> OrganizationMembership:
        membership = await crud.get_membership_for_user(
            self.session,
            user_id=user_id,
            organization_id=organization_id,
        )
        if membership is None:
            raise NotFoundAppError("Workspace membership not found.")
        return membership

    async def _get_mfa_credential(self, *, user_id: UUID) -> UserMfaCredential | None:
        return await self._mfa.get_mfa_credential(user_id=user_id)

    async def _list_user_sessions(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        current_session_id: UUID | None,
    ) -> list[AccountUserSessionRead]:
        result = await self.session.execute(
            select(UserSession)
            .where(
                UserSession.organization_id == organization_id,
                UserSession.user_id == user_id,
            )
            .order_by(desc(UserSession.last_seen_at), desc(UserSession.created_at))
            .limit(16)
        )
        return [
            self._build_session_read(session_record=item, current_session_id=current_session_id)
            for item in result.scalars().all()
        ]

    async def _build_mfa_status(self, *, user_id: UUID) -> AccountMfaStatusRead:
        return await self._mfa.build_mfa_status(user_id=user_id)

    async def _list_invites(self, *, organization_id: UUID) -> list[AccountInviteRead]:
        result = await self.session.execute(
            select(WorkspaceInvite)
            .where(WorkspaceInvite.organization_id == organization_id)
            .order_by(desc(WorkspaceInvite.created_at))
            .limit(24)
        )
        invites = result.scalars().all()
        now = self._now()
        did_update = False
        for invite in invites:
            if invite.status == WorkspaceInviteStatus.PENDING and invite.expires_at <= now:
                invite.status = WorkspaceInviteStatus.EXPIRED
                did_update = True
        if did_update:
            await self.session.commit()
        related_user_ids = [
            user_id
            for invite in invites
            for user_id in (invite.invited_by_user_id, invite.accepted_by_user_id)
            if user_id is not None
        ]
        users_by_id = await crud.get_users_by_ids(self.session, related_user_ids)
        items: list[AccountInviteRead] = []
        for invite in invites:
            items.append(await self._build_invite_read(invite, users_by_id=users_by_id))
        return items

    async def _build_invite_read(
        self,
        invite: WorkspaceInvite,
        *,
        users_by_id: dict[UUID, User] | None = None,
    ) -> AccountInviteRead:
        invited_by = None
        accepted_by = None
        if users_by_id is not None:
            invited_by = users_by_id.get(invite.invited_by_user_id)
            accepted_by = (
                users_by_id.get(invite.accepted_by_user_id) if invite.accepted_by_user_id else None
            )
        else:
            invited_by = await crud.get_user_by_id(self.session, invite.invited_by_user_id)
            accepted_by = (
                await crud.get_user_by_id(self.session, invite.accepted_by_user_id)
                if invite.accepted_by_user_id
                else None
            )
        return AccountInviteRead(
            id=invite.id,
            email=invite.email,
            role=invite.role.value,
            status=invite.status.value,
            token_prefix=invite.token_prefix,
            expires_at=invite.expires_at,
            accepted_at=invite.accepted_at,
            revoked_at=invite.revoked_at,
            invited_by_email=invited_by.email if invited_by is not None else None,
            invited_by_full_name=invited_by.full_name if invited_by is not None else None,
            accepted_by_email=accepted_by.email if accepted_by is not None else None,
            accepted_by_full_name=accepted_by.full_name if accepted_by is not None else None,
            created_at=invite.created_at,
            updated_at=invite.updated_at,
        )

    async def _get_sso_config(self, *, organization_id: UUID) -> AccountSsoConfigRead:
        result = await self.session.execute(
            select(OrganizationSsoConfig)
            .where(OrganizationSsoConfig.organization_id == organization_id)
            .limit(1)
        )
        config = result.scalar_one_or_none()
        if config is None:
            return AccountSsoConfigRead(readiness_checks=["Workspace SSO is not configured yet."])
        readiness_checks = self._build_sso_readiness_checks(config)
        return AccountSsoConfigRead(
            provider_type=config.provider_type.value,
            is_enabled=config.is_enabled,
            issuer_url=config.issuer_url,
            entrypoint_url=config.entrypoint_url,
            metadata_url=config.metadata_url,
            audience=config.audience,
            client_id=config.client_id,
            has_client_secret=bool(config.client_secret_ciphertext),
            scopes=list(config.scopes_json or []),
            attribute_mapping=dict(config.attribute_mapping_json or {}),
            certificate_pem=config.certificate_pem,
            login_hint_domain=config.login_hint_domain,
            readiness_checks=readiness_checks,
            updated_at=config.updated_at,
        )

    def _build_sso_readiness_checks(self, config: OrganizationSsoConfig) -> list[str]:
        checks: list[str] = []
        if config.provider_type == SsoProviderType.OIDC:
            if not config.issuer_url:
                checks.append("OIDC issuer URL is missing.")
            if not config.client_id:
                checks.append("OIDC client ID is missing.")
            if not config.client_secret_ciphertext:
                checks.append("OIDC client secret is missing.")
        if config.provider_type == SsoProviderType.SAML:
            if not config.entrypoint_url:
                checks.append("SAML entrypoint URL is missing.")
            if not config.certificate_pem:
                checks.append("SAML certificate is missing.")
            if not config.audience:
                checks.append("SAML audience is missing.")
        if not checks:
            checks.append(
                "Configuration is structurally complete. IdP handshake wiring can be added on top of this."
            )
        return checks

    def _build_session_read(
        self,
        *,
        session_record: UserSession,
        current_session_id: UUID | None,
    ) -> AccountUserSessionRead:
        return AccountUserSessionRead(
            id=session_record.id,
            token_prefix=session_record.token_prefix,
            user_agent=session_record.user_agent,
            ip_address=session_record.ip_address,
            last_seen_at=session_record.last_seen_at,
            expires_at=session_record.expires_at,
            idle_expires_at=session_record.idle_expires_at,
            revoked_at=session_record.revoked_at,
            revoked_reason=session_record.revoked_reason,
            is_current=current_session_id == session_record.id,
            created_at=session_record.created_at,
            updated_at=session_record.updated_at,
        )

    def _build_auth_response(
        self,
        *,
        message: str,
        user: User,
        organization: Organization | None,
        default_project: Project | None,
        session_token: str | None = None,
    ) -> AuthResponse:
        return AuthResponse.from_user_and_org(
            message=message,
            user=user,
            organization=organization,
            default_project=default_project,
            session_token=session_token,
        )

    async def _append_audit_log(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        payload_json: dict[str, Any],
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

    def _require_admin_role(self, role: OrgRole, action: str) -> None:
        if role not in ADMIN_ROLES:
            raise ForbiddenAppError(f"You do not have permission to {action} in this workspace.")

    def _clean_optional(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    def _now(self) -> datetime:
        return datetime.now(UTC)
