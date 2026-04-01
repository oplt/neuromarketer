from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import AuthenticatedRequestContext, require_authenticated_context
from backend.application.services.auth_service import AuthApplicationService, AuthClientMetadata
from backend.db.session import get_db
from backend.schemas.schemas import (
    AcceptInviteRequest,
    AuthResponse,
    InvitePreviewRead,
    MfaChallengeVerifyRequest,
    SignInRequest,
    SignUpRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def sign_up(
    payload: SignUpRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    return await AuthApplicationService(db).sign_up(
        payload=payload,
        client=_build_auth_client_metadata(request),
    )


@router.post("/signin", response_model=AuthResponse)
async def sign_in(
    payload: SignInRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    return await AuthApplicationService(db).sign_in(
        payload=payload,
        client=_build_auth_client_metadata(request),
    )


@router.post("/mfa/verify", response_model=AuthResponse)
async def verify_mfa_challenge(
    payload: MfaChallengeVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    return await AuthApplicationService(db).verify_mfa_challenge(
        payload=payload,
        client=_build_auth_client_metadata(request),
    )


@router.post("/signout")
async def sign_out(
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> dict[str, str]:
    await AuthApplicationService(db).sign_out(
        session_id=auth.session.id,
        user_id=auth.user.id,
        organization_id=auth.organization.id,
    )
    return {"message": "Signed out successfully."}


@router.get("/invites/preview", response_model=InvitePreviewRead)
async def get_invite_preview(
    token: str = Query(min_length=16),
    db: AsyncSession = Depends(get_db),
) -> InvitePreviewRead:
    return await AuthApplicationService(db).get_invite_preview(invite_token=token)


@router.post("/invites/accept", response_model=AuthResponse)
async def accept_invite(
    payload: AcceptInviteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    return await AuthApplicationService(db).accept_invite(
        payload=payload,
        client=_build_auth_client_metadata(request),
    )


def _build_auth_client_metadata(request: Request) -> AuthClientMetadata:
    return AuthClientMetadata(
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client is not None else None,
    )
