from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.auth_service import AuthApplicationService
from backend.core.config import settings
from backend.core.exceptions import UnauthorizedAppError
from backend.core.log_context import bind_log_context
from backend.core.security import SessionClaims, hash_token, verify_session_token
from backend.db.models import UserSession
from backend.db.repositories import AuthRepository
from backend.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)
_AUTH_CACHE_TTL_SECONDS = float(getattr(settings, "auth_context_cache_ttl_seconds", 60))
_SESSION_CACHE_TTL_SECONDS = float(getattr(settings, "auth_session_cache_ttl_seconds", 60))


@dataclass(slots=True)
class AuthenticatedUser:
    id: UUID
    email: str
    is_active: bool
    deleted_at: object | None


@dataclass(slots=True)
class AuthenticatedOrganization:
    id: UUID
    is_active: bool
    name: str
    slug: str


@dataclass(slots=True)
class AuthenticatedProject:
    id: UUID
    name: str


@dataclass(slots=True)
class AuthenticatedClaimsContext:
    claims: SessionClaims
    session_token: str


@dataclass(slots=True)
class AuthenticatedSessionContext:
    claims: SessionClaims
    user: AuthenticatedUser
    organization: AuthenticatedOrganization
    session: UserSession
    session_token: str


@dataclass(slots=True)
class AuthenticatedProjectContext:
    claims: SessionClaims
    user: AuthenticatedUser
    organization: AuthenticatedOrganization
    default_project: AuthenticatedProject
    session: UserSession
    session_token: str


@dataclass(slots=True)
class AuthenticatedRequestContext:
    claims: SessionClaims
    user: AuthenticatedUser
    organization: AuthenticatedOrganization
    default_project: AuthenticatedProject
    session: UserSession
    session_token: str


@dataclass(slots=True)
class _AuthCacheEntry:
    user: AuthenticatedUser
    organization: AuthenticatedOrganization
    default_project: AuthenticatedProject | None
    expires_at: float


@dataclass(slots=True)
class _SessionCacheEntry:
    session: UserSession
    expires_at: float


_auth_cache: dict[str, _AuthCacheEntry] = {}
_session_cache: dict[str, _SessionCacheEntry] = {}


def _monotonic_now() -> float:
    return time.monotonic()


def _auth_cache_key(*, user_id: UUID, organization_id: UUID) -> str:
    return f"{user_id}:{organization_id}"


def _session_cache_key(*, session_id: UUID, token: str) -> str:
    return f"{session_id}:{hash_token(token)}"


def _get_cached_auth(*, user_id: UUID, organization_id: UUID) -> _AuthCacheEntry | None:
    entry = _auth_cache.get(_auth_cache_key(user_id=user_id, organization_id=organization_id))
    if entry is None:
        return None
    if entry.expires_at <= _monotonic_now():
        _auth_cache.pop(_auth_cache_key(user_id=user_id, organization_id=organization_id), None)
        return None
    return entry


def _set_cached_auth(
    *,
    user_id: UUID,
    organization_id: UUID,
    user: AuthenticatedUser,
    organization: AuthenticatedOrganization,
    default_project: AuthenticatedProject | None,
) -> None:
    _auth_cache[_auth_cache_key(user_id=user_id, organization_id=organization_id)] = _AuthCacheEntry(
        user=user,
        organization=organization,
        default_project=default_project,
        expires_at=_monotonic_now() + _AUTH_CACHE_TTL_SECONDS,
    )


def _get_cached_session(*, session_id: UUID, token: str) -> UserSession | None:
    cache_key = _session_cache_key(session_id=session_id, token=token)
    entry = _session_cache.get(cache_key)
    if entry is None:
        return None
    if entry.expires_at <= _monotonic_now():
        _session_cache.pop(cache_key, None)
        return None
    return entry.session


def _set_cached_session(*, session_id: UUID, token: str, session: UserSession) -> None:
    _session_cache[_session_cache_key(session_id=session_id, token=token)] = _SessionCacheEntry(
        session=session,
        expires_at=_monotonic_now() + _SESSION_CACHE_TTL_SECONDS,
    )


def _build_authenticated_user(user) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        is_active=bool(user.is_active),
        deleted_at=user.deleted_at,
    )


def _build_authenticated_organization(organization) -> AuthenticatedOrganization:
    return AuthenticatedOrganization(
        id=organization.id,
        is_active=bool(organization.is_active),
        name=organization.name,
        slug=organization.slug,
    )


def _build_authenticated_project(project) -> AuthenticatedProject | None:
    if project is None:
        return None
    return AuthenticatedProject(id=project.id, name=project.name)


async def require_authenticated_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedClaimsContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedAppError("Authentication is required.")
    claims = verify_session_token(credentials.credentials)
    return AuthenticatedClaimsContext(claims=claims, session_token=credentials.credentials)


async def require_authenticated_session(
    auth_claims: AuthenticatedClaimsContext = Depends(require_authenticated_claims),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedSessionContext:
    claims = auth_claims.claims
    auth_repo = AuthRepository(db)
    cached_entry = _get_cached_auth(user_id=claims.user_id, organization_id=claims.organization_id)
    if cached_entry is None:
        user, organization = await auth_repo.get_user_and_organization(
            user_id=claims.user_id,
            organization_id=claims.organization_id,
        )
        if user is None or organization is None:
            raise UnauthorizedAppError("Authentication is required.")
        authenticated_user = _build_authenticated_user(user)
        authenticated_org = _build_authenticated_organization(organization)
        _set_cached_auth(
            user_id=claims.user_id,
            organization_id=claims.organization_id,
            user=authenticated_user,
            organization=authenticated_org,
            default_project=None,
        )
    else:
        authenticated_user = cached_entry.user
        authenticated_org = cached_entry.organization

    if not authenticated_user.is_active or authenticated_user.deleted_at is not None:
        raise UnauthorizedAppError("Authentication is required.")
    if authenticated_user.email.strip().lower() != claims.email:
        raise UnauthorizedAppError("Authentication is required.")
    if not authenticated_org.is_active:
        raise UnauthorizedAppError("Authentication is required.")

    session_record = _get_cached_session(
        session_id=claims.session_id,
        token=auth_claims.session_token,
    )
    if session_record is None:
        session_record = await AuthApplicationService(db).validate_session_token(
            session_id=claims.session_id,
            token=auth_claims.session_token,
            user_id=authenticated_user.id,
            organization_id=claims.organization_id,
        )
        _set_cached_session(
            session_id=claims.session_id,
            token=auth_claims.session_token,
            session=session_record,
        )

    return AuthenticatedSessionContext(
        claims=claims,
        user=authenticated_user,
        organization=authenticated_org,
        session=session_record,
        session_token=auth_claims.session_token,
    )


async def require_project_context(
    auth_session: AuthenticatedSessionContext = Depends(require_authenticated_session),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedProjectContext:
    claims = auth_session.claims
    auth_repo = AuthRepository(db)
    cached_entry = _get_cached_auth(user_id=claims.user_id, organization_id=claims.organization_id)
    cached_project = cached_entry.default_project if cached_entry is not None else None
    if cached_project is None:
        default_project = await auth_repo.get_default_project_for_organization(
            auth_session.organization.id
        )
        if default_project is None:
            default_project = await auth_repo.get_or_create_default_project_for_organization(
                organization_id=auth_session.organization.id,
                created_by_user_id=auth_session.user.id,
            )
        cached_project = _build_authenticated_project(default_project)
        _set_cached_auth(
            user_id=claims.user_id,
            organization_id=claims.organization_id,
            user=auth_session.user,
            organization=auth_session.organization,
            default_project=cached_project,
        )

    return AuthenticatedProjectContext(
        claims=auth_session.claims,
        user=auth_session.user,
        organization=auth_session.organization,
        default_project=cached_project,
        session=auth_session.session,
        session_token=auth_session.session_token,
    )


async def require_authenticated_context(
    auth_project: AuthenticatedProjectContext = Depends(require_project_context),
) -> AuthenticatedRequestContext:
    bind_log_context(
        user_id=str(auth_project.user.id),
        org_id=str(auth_project.organization.id),
        project_id=str(auth_project.default_project.id),
    )
    return AuthenticatedRequestContext(
        claims=auth_project.claims,
        user=auth_project.user,
        organization=auth_project.organization,
        default_project=auth_project.default_project,
        session=auth_project.session,
        session_token=auth_project.session_token,
    )
