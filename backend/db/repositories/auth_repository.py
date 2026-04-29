from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import hash_password
from backend.db.models import (
    Organization,
    OrganizationMembership,
    OrgRole,
    Project,
    User,
)

DEFAULT_PROJECT_NAME = "Default Analysis Project"
DEFAULT_PROJECT_DESCRIPTION = "System-created project used by the Analysis workspace."


def _slugify_workspace_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "workspace"


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.strip().lower()))
        return result.scalar_one_or_none()

    async def create_user_with_workspace(
        self,
        *,
        email: str,
        full_name: str,
        password: str,
    ) -> tuple[User, Organization, Project]:
        normalized_email = email.strip().lower()
        cleaned_name = full_name.strip()
        name_parts = cleaned_name.split(maxsplit=1)
        first_name = name_parts[0] if name_parts else None
        last_name = name_parts[1] if len(name_parts) > 1 else None
        workspace_name = f"{cleaned_name}'s Workspace" if cleaned_name else "Workspace"
        workspace_slug = await self._build_unique_organization_slug(workspace_name)

        user = User(
            email=normalized_email,
            first_name=first_name,
            last_name=last_name,
            password_hash=hash_password(password),
            is_active=True,
            is_verified=False,
        )
        organization = Organization(
            name=workspace_name,
            slug=workspace_slug,
            billing_email=normalized_email,
            is_active=True,
            settings={},
        )
        membership = OrganizationMembership(
            organization=organization,
            user=user,
            role=OrgRole.OWNER,
        )
        project = Project(
            organization=organization,
            created_by_user=user,
            name=DEFAULT_PROJECT_NAME,
            description=DEFAULT_PROJECT_DESCRIPTION,
            settings={"system_managed": True, "surface": "analysis"},
        )

        self.session.add_all([user, organization, membership, project])
        await self.session.flush()
        await self.session.refresh(user)
        await self.session.refresh(organization)
        await self.session.refresh(project)
        return user, organization, project

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_users_by_ids(self, user_ids: Sequence[UUID]) -> dict[UUID, User]:
        unique_user_ids = tuple(dict.fromkeys(user_ids))
        if not unique_user_ids:
            return {}
        result = await self.session.execute(select(User).where(User.id.in_(unique_user_ids)))
        return {user.id: user for user in result.scalars().all()}

    async def get_user_and_organization(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
    ) -> tuple[User | None, Organization | None]:
        result = await self.session.execute(
            select(User, Organization)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                User.id == user_id,
                Organization.id == organization_id,
                OrganizationMembership.organization_id == organization_id,
            )
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            return None, None
        return row[0], row[1]

    async def get_primary_organization_for_user(self, user_id: UUID) -> Organization | None:
        result = await self.session.execute(
            select(Organization)
            .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
            .where(OrganizationMembership.user_id == user_id)
            .order_by(Organization.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_organization_for_user(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
    ) -> Organization | None:
        result = await self.session.execute(
            select(Organization)
            .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_membership_for_user(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
    ) -> OrganizationMembership | None:
        result = await self.session.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.organization_id == organization_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_default_project_for_organization(self, organization_id: UUID) -> Project | None:
        result = await self.session.execute(
            select(Project)
            .where(Project.organization_id == organization_id)
            .order_by(Project.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_or_create_default_project_for_organization(
        self,
        *,
        organization_id: UUID,
        created_by_user_id: UUID | None,
    ) -> Project:
        existing = await self.get_default_project_for_organization(organization_id)
        if existing is not None:
            return existing

        project = Project(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            name=DEFAULT_PROJECT_NAME,
            description=DEFAULT_PROJECT_DESCRIPTION,
            settings={"system_managed": True, "surface": "analysis"},
        )
        self.session.add(project)
        await self.session.flush()
        await self.session.refresh(project)
        return project

    async def _build_unique_organization_slug(self, base_name: str) -> str:
        base_slug = _slugify_workspace_name(base_name)
        candidate = base_slug
        suffix = 2

        while True:
            result = await self.session.execute(
                select(Organization.id).where(Organization.slug == candidate)
            )
            if result.scalar_one_or_none() is None:
                return candidate
            candidate = f"{base_slug}-{suffix}"
            suffix += 1
