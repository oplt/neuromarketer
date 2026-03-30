from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import verify_password
from backend.db.repositories import crud
from backend.db.session import get_db
from backend.schemas.schemas import (
    AuthResponse,
    SignInRequest,
    SignUpRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def sign_up(
    payload: SignUpRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    existing_user = await crud.get_user_by_email(db, payload.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user, organization = await crud.create_user_with_workspace(
        db,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
    )
    return AuthResponse.from_user_and_org(
        message="Account created successfully.",
        user=user,
        organization=organization,
    )


@router.post("/signin", response_model=AuthResponse)
async def sign_in(
    payload: SignInRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user = await crud.get_user_by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    organization = await crud.get_primary_organization_for_user(db, user.id)
    return AuthResponse.from_user_and_org(
        message="Signed in successfully.",
        user=user,
        organization=organization,
    )
