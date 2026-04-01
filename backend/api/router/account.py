from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import AuthenticatedRequestContext, require_authenticated_context
from backend.application.services.account_admin import AccountAdminApplicationService
from backend.application.services.auth_service import AuthApplicationService
from backend.db.session import get_db
from backend.schemas.account import (
    AccountApiKeyRead,
    AccountControlCenterRead,
    AccountInviteCreateRequest,
    AccountInviteCreateResponse,
    AccountInviteRead,
    AccountMfaConfirmRequest,
    AccountMfaDisableRequest,
    AccountMfaRecoveryCodesResponse,
    AccountMfaSetupStartResponse,
    AccountMfaStatusRead,
    AccountMemberRead,
    AccountSecurityOverviewRead,
    AccountSsoConfigRead,
    AccountSsoConfigUpsertRequest,
    AccountUserSessionRead,
    AccountWebhookRead,
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyRotateResponse,
    MemberRoleUpdateRequest,
    WebhookCreateRequest,
    WebhookSecretResponse,
    WebhookUpdateRequest,
)

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/control-center", response_model=AccountControlCenterRead)
async def get_account_control_center(
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountControlCenterRead:
    return await AccountAdminApplicationService(db).get_control_center(
        organization_id=auth.organization.id,
        user_id=auth.user.id,
    )


@router.get("/security/overview", response_model=AccountSecurityOverviewRead)
async def get_account_security_overview(
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountSecurityOverviewRead:
    return await AuthApplicationService(db).get_security_overview(
        organization_id=auth.organization.id,
        user_id=auth.user.id,
        current_session_id=auth.session.id,
    )


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> ApiKeyCreateResponse:
    return await AccountAdminApplicationService(db).create_api_key(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        payload=payload,
    )


@router.post("/api-keys/{api_key_id}/revoke", response_model=AccountApiKeyRead)
async def revoke_api_key(
    api_key_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountApiKeyRead:
    return await AccountAdminApplicationService(db).revoke_api_key(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        api_key_id=api_key_id,
    )


@router.post("/api-keys/{api_key_id}/rotate", response_model=ApiKeyRotateResponse)
async def rotate_api_key(
    api_key_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> ApiKeyRotateResponse:
    return await AccountAdminApplicationService(db).rotate_api_key(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        api_key_id=api_key_id,
    )


@router.post("/webhooks", response_model=WebhookSecretResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> WebhookSecretResponse:
    return await AccountAdminApplicationService(db).create_webhook(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        payload=payload,
    )


@router.put("/webhooks/{webhook_id}", response_model=AccountWebhookRead)
async def update_webhook(
    webhook_id: UUID,
    payload: WebhookUpdateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountWebhookRead:
    return await AccountAdminApplicationService(db).update_webhook(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        webhook_id=webhook_id,
        payload=payload,
    )


@router.post("/webhooks/{webhook_id}/rotate-secret", response_model=WebhookSecretResponse)
async def rotate_webhook_secret(
    webhook_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> WebhookSecretResponse:
    return await AccountAdminApplicationService(db).rotate_webhook_secret(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        webhook_id=webhook_id,
    )


@router.put("/members/{membership_id}", response_model=AccountMemberRead)
async def update_member_role(
    membership_id: UUID,
    payload: MemberRoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountMemberRead:
    return await AccountAdminApplicationService(db).update_member_role(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        membership_id=membership_id,
        payload=payload,
    )


@router.post("/invites", response_model=AccountInviteCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace_invite(
    payload: AccountInviteCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountInviteCreateResponse:
    return await AuthApplicationService(db).create_invite(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        payload=payload,
    )


@router.post("/invites/{invite_id}/revoke", response_model=AccountInviteRead)
async def revoke_workspace_invite(
    invite_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountInviteRead:
    return await AuthApplicationService(db).revoke_invite(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        invite_id=invite_id,
    )


@router.post("/sessions/{session_id}/revoke", response_model=AccountUserSessionRead)
async def revoke_account_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountUserSessionRead:
    return await AuthApplicationService(db).revoke_session(
        organization_id=auth.organization.id,
        user_id=auth.user.id,
        session_id=session_id,
    )


@router.post("/mfa/setup", response_model=AccountMfaSetupStartResponse, status_code=status.HTTP_201_CREATED)
async def start_mfa_setup(
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountMfaSetupStartResponse:
    return await AuthApplicationService(db).start_mfa_setup(
        organization_id=auth.organization.id,
        user_id=auth.user.id,
        email=auth.user.email,
    )


@router.post("/mfa/confirm", response_model=AccountMfaRecoveryCodesResponse)
async def confirm_mfa_setup(
    payload: AccountMfaConfirmRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountMfaRecoveryCodesResponse:
    return await AuthApplicationService(db).confirm_mfa_setup(
        organization_id=auth.organization.id,
        user_id=auth.user.id,
        payload=payload,
    )


@router.post("/mfa/disable", response_model=AccountMfaStatusRead)
async def disable_mfa(
    payload: AccountMfaDisableRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountMfaStatusRead:
    return await AuthApplicationService(db).disable_mfa(
        organization_id=auth.organization.id,
        user_id=auth.user.id,
        payload=payload,
    )


@router.post("/mfa/recovery-codes/regenerate", response_model=AccountMfaRecoveryCodesResponse)
async def regenerate_mfa_recovery_codes(
    payload: AccountMfaDisableRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountMfaRecoveryCodesResponse:
    return await AuthApplicationService(db).regenerate_mfa_recovery_codes(
        organization_id=auth.organization.id,
        user_id=auth.user.id,
        payload=payload,
    )


@router.put("/sso", response_model=AccountSsoConfigRead)
async def upsert_sso_config(
    payload: AccountSsoConfigUpsertRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AccountSsoConfigRead:
    return await AuthApplicationService(db).upsert_sso_config(
        organization_id=auth.organization.id,
        actor_user_id=auth.user.id,
        payload=payload,
    )
