from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.log_context import bound_log_context
from backend.core.exceptions import NotFoundAppError, ValidationAppError
from backend.core.logging import get_logger, log_event, log_exception
from backend.db.repositories import CreativeRepository

logger = get_logger(__name__)


class CreativeVersionApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.creatives = CreativeRepository(session)

    async def promote_artifact(self, artifact_id: UUID):
        with bound_log_context(artifact_id=str(artifact_id)):
            try:
                artifact = await self.creatives.get_stored_artifact(artifact_id)
                if artifact is None:
                    raise NotFoundAppError("Artifact not found.")
                if artifact.creative_id is None:
                    raise ValidationAppError("Artifact is not attached to a creative.")

                with bound_log_context(
                    project_id=str(artifact.project_id),
                    creative_id=str(artifact.creative_id),
                ):
                    version = await self.creatives.create_version_from_artifact(artifact)
                    await self.session.commit()
                    await self.session.refresh(version)
                    log_event(
                        logger,
                        "artifact_promoted_to_creative_version",
                        creative_version_id=str(version.id),
                        project_id=str(artifact.project_id),
                        creative_id=str(artifact.creative_id),
                        status="succeeded",
                    )
                    return version
            except Exception as exc:
                log_exception(
                    logger,
                    "creative_version_promotion_failed",
                    exc,
                    level="warning" if isinstance(exc, (NotFoundAppError, ValidationAppError)) else "error",
                    artifact_id=str(artifact_id),
                    status="failed",
                )
                raise
