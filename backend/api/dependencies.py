from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.auth_service import AuthApplicationService
from backend.core.exceptions import UnauthorizedAppError
from backend.core.log_context import bind_log_context
from backend.core.security import verify_session_token
from backend.db.models import Organization, Project, User, UserSession
from backend.db.repositories import crud
from backend.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthenticatedRequestContext:
    user: User
    organization: Organization
    default_project: Project
    session: UserSession
    session_token: str


async def require_authenticated_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedRequestContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedAppError("Authentication is required.")

    claims = verify_session_token(credentials.credentials)

    user, organization, default_project = await crud.get_user_org_and_default_project(
        db,
        user_id=claims.user_id,
        organization_id=claims.organization_id,
    )
    if user is None or not user.is_active or user.deleted_at is not None:
        raise UnauthorizedAppError("Authentication is required.")
    if user.email.strip().lower() != claims.email:
        raise UnauthorizedAppError("Authentication is required.")
    if organization is None or not organization.is_active:
        raise UnauthorizedAppError("Authentication is required.")

    session_record = await AuthApplicationService(db).validate_session_token(
        session_id=claims.session_id,
        token=credentials.credentials,
        user_id=user.id,
        organization_id=claims.organization_id,
    )

    if default_project is None:
        default_project = await crud.get_or_create_default_project_for_organization(
            db,
            organization_id=organization.id,
            created_by_user_id=user.id,
        )
    bind_log_context(
        user_id=str(user.id),
        org_id=str(organization.id),
        project_id=str(default_project.id),
    )
    return AuthenticatedRequestContext(
        user=user,
        organization=organization,
        default_project=default_project,
        session=session_record,
        session_token=credentials.credentials,
    )
