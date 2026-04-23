from __future__ import annotations

"""MFA (multi-factor authentication) application service.

Extracted from AuthApplicationService to keep that class focused.
All public method signatures are identical to the originals so callers
do not need to change.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import NotFoundAppError, ValidationAppError
from backend.core.security import (
    build_totp_uri,
    create_totp_secret,
    generate_recovery_codes,
    hash_recovery_code,
    normalize_recovery_code,
    seal_secret,
    unseal_secret,
    verify_totp_code,
)
from backend.db.models import (
    AuditLog,
    MfaMethodType,
    OrganizationMembership,
    OrgRole,
    UserMfaCredential,
)
from backend.db.repositories import crud
from backend.schemas.account import (
    AccountMfaConfirmRequest,
    AccountMfaDisableRequest,
    AccountMfaRecoveryCodesResponse,
    AccountMfaSetupStartResponse,
    AccountMfaStatusRead,
)

ADMIN_ROLES = {OrgRole.OWNER, OrgRole.ADMIN}


class MFAService:
    """Handles TOTP setup, confirmation, disabling, and recovery-code management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_mfa_setup(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        email: str,
    ) -> AccountMfaSetupStartResponse:
        await self._get_membership(organization_id=organization_id, user_id=user_id)
        credential = await self._get_or_create_mfa_credential(user_id=user_id)
        secret = create_totp_secret()
        credential.pending_secret_ciphertext = seal_secret(secret)
        await self.session.flush()
        await self.session.commit()
        issuer = settings.app_name
        return AccountMfaSetupStartResponse(
            secret=secret,
            otpauth_uri=build_totp_uri(secret=secret, email=email, issuer=issuer),
            issuer=issuer,
        )

    async def confirm_mfa_setup(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        payload: AccountMfaConfirmRequest,
    ) -> AccountMfaRecoveryCodesResponse:
        await self._get_membership(organization_id=organization_id, user_id=user_id)
        credential = await self._get_or_create_mfa_credential(user_id=user_id)
        pending_secret = unseal_secret(credential.pending_secret_ciphertext)
        if not pending_secret:
            raise ValidationAppError("Start MFA setup before confirming a code.")
        if not verify_totp_code(payload.code, pending_secret):
            raise ValidationAppError("The verification code is invalid.")

        recovery_codes = generate_recovery_codes()
        credential.secret_ciphertext = seal_secret(pending_secret)
        credential.pending_secret_ciphertext = None
        credential.is_enabled = True
        credential.recovery_code_hashes = [hash_recovery_code(item) for item in recovery_codes]
        credential.last_used_at = self._now()
        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=user_id,
            action="auth.mfa.enabled",
            entity_type="user_mfa_credential",
            entity_id=credential.id,
            payload_json={"method_type": credential.method_type.value},
        )
        await self.session.commit()
        return AccountMfaRecoveryCodesResponse(
            recovery_codes=recovery_codes,
            status=await self.build_mfa_status(user_id=user_id),
        )

    async def disable_mfa(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        payload: AccountMfaDisableRequest,
    ) -> AccountMfaStatusRead:
        await self._get_membership(organization_id=organization_id, user_id=user_id)
        credential = await self._get_mfa_credential(user_id=user_id)
        if credential is None or not credential.is_enabled:
            raise ValidationAppError("Multi-factor authentication is not enabled.")
        await self._verify_mfa_assertion(
            credential=credential, code=payload.code, recovery_code=payload.recovery_code
        )
        credential.is_enabled = False
        credential.secret_ciphertext = None
        credential.pending_secret_ciphertext = None
        credential.recovery_code_hashes = []
        credential.last_used_at = self._now()
        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=user_id,
            action="auth.mfa.disabled",
            entity_type="user_mfa_credential",
            entity_id=credential.id,
            payload_json={"method_type": credential.method_type.value},
        )
        await self.session.commit()
        return await self.build_mfa_status(user_id=user_id)

    async def regenerate_mfa_recovery_codes(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        payload: AccountMfaDisableRequest,
    ) -> AccountMfaRecoveryCodesResponse:
        await self._get_membership(organization_id=organization_id, user_id=user_id)
        credential = await self._get_mfa_credential(user_id=user_id)
        if credential is None or not credential.is_enabled:
            raise ValidationAppError("Multi-factor authentication is not enabled.")
        await self._verify_mfa_assertion(
            credential=credential, code=payload.code, recovery_code=payload.recovery_code
        )
        recovery_codes = generate_recovery_codes()
        credential.recovery_code_hashes = [hash_recovery_code(item) for item in recovery_codes]
        credential.last_used_at = self._now()
        await self._append_audit_log(
            organization_id=organization_id,
            actor_user_id=user_id,
            action="auth.mfa.recovery_codes_regenerated",
            entity_type="user_mfa_credential",
            entity_id=credential.id,
            payload_json={"remaining_codes": len(recovery_codes)},
        )
        await self.session.commit()
        return AccountMfaRecoveryCodesResponse(
            recovery_codes=recovery_codes,
            status=await self.build_mfa_status(user_id=user_id),
        )

    async def build_mfa_status(self, *, user_id: UUID) -> AccountMfaStatusRead:
        credential = await self._get_mfa_credential(user_id=user_id)
        if credential is None:
            return AccountMfaStatusRead(
                is_enabled=False,
                method_type="totp",
                pending_setup=False,
                recovery_codes_remaining=0,
            )
        return AccountMfaStatusRead(
            is_enabled=credential.is_enabled,
            method_type=credential.method_type.value,
            recovery_codes_remaining=len(credential.recovery_code_hashes or []),
            pending_setup=bool(credential.pending_secret_ciphertext),
            last_used_at=credential.last_used_at,
        )

    # ------------------------------------------------------------------
    # Internal helpers (also used by AuthApplicationService via delegation)
    # ------------------------------------------------------------------

    async def verify_mfa_assertion_for_credential(
        self,
        *,
        credential: UserMfaCredential,
        code: str | None,
        recovery_code: str | None,
    ) -> None:
        """Public entry point for callers that already hold the credential."""
        await self._verify_mfa_assertion(
            credential=credential, code=code, recovery_code=recovery_code
        )

    async def get_mfa_credential(self, *, user_id: UUID) -> UserMfaCredential | None:
        return await self._get_mfa_credential(user_id=user_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _verify_mfa_assertion(
        self,
        *,
        credential: UserMfaCredential,
        code: str | None,
        recovery_code: str | None,
    ) -> None:
        if code:
            secret = unseal_secret(credential.secret_ciphertext)
            if not secret or not verify_totp_code(code, secret):
                raise ValidationAppError("The verification code is invalid.")
            return
        if recovery_code:
            normalized = normalize_recovery_code(recovery_code)
            hashed = hash_recovery_code(normalized)
            existing = list(credential.recovery_code_hashes or [])
            if hashed not in existing:
                raise ValidationAppError("The recovery code is invalid.")
            existing.remove(hashed)
            credential.recovery_code_hashes = existing
            credential.last_used_at = self._now()
            await self.session.flush()
            return
        raise ValidationAppError("A verification code or recovery code is required.")

    async def _get_or_create_mfa_credential(self, *, user_id: UUID) -> UserMfaCredential:
        credential = await self._get_mfa_credential(user_id=user_id)
        if credential is not None:
            return credential
        credential = UserMfaCredential(
            user_id=user_id,
            method_type=MfaMethodType.TOTP,
            is_enabled=False,
            recovery_code_hashes=[],
            metadata_json={},
        )
        self.session.add(credential)
        await self.session.flush()
        return credential

    async def _get_mfa_credential(self, *, user_id: UUID) -> UserMfaCredential | None:
        result = await self.session.execute(
            select(UserMfaCredential)
            .where(
                UserMfaCredential.user_id == user_id,
                UserMfaCredential.method_type == MfaMethodType.TOTP,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

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

    async def _append_audit_log(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID | None,
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

    def _now(self) -> datetime:
        return datetime.now(UTC)
