from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import NotFoundAppError, ValidationAppError
from backend.db.repositories import CreativeRepository


class CreativeVersionApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.creatives = CreativeRepository(session)

    async def promote_artifact(self, artifact_id: UUID):
        artifact = await self.creatives.get_stored_artifact(artifact_id)
        if artifact is None:
            raise NotFoundAppError("Artifact not found.")
        if artifact.creative_id is None:
            raise ValidationAppError("Artifact is not attached to a creative.")

        version = await self.creatives.create_version_from_artifact(artifact)
        await self.session.commit()
        await self.session.refresh(version)
        return version
