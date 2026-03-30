from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import UnauthorizedAppError
from backend.core.security import verify_session_token
from backend.db.models import Organization, Project, User
from backend.db.repositories import crud
from backend.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthenticatedRequestContext:
    user: User
    organization: Organization
    default_project: Project
    session_token: str


async def require_authenticated_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedRequestContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedAppError("Authentication is required.")

    claims = verify_session_token(credentials.credentials)
    user = await crud.get_user_by_id(db, claims.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise UnauthorizedAppError("Authentication is required.")
    if user.email.strip().lower() != claims.email:
        raise UnauthorizedAppError("Authentication is required.")

    organization = await crud.get_primary_organization_for_user(db, user.id)
    if organization is None or organization.id != claims.organization_id or not organization.is_active:
        raise UnauthorizedAppError("Authentication is required.")

    default_project = await crud.get_or_create_default_project_for_organization(
        db,
        organization_id=organization.id,
        created_by_user_id=user.id,
    )
    return AuthenticatedRequestContext(
        user=user,
        organization=organization,
        default_project=default_project,
        session_token=credentials.credentials,
    )
