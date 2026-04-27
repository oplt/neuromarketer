from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import AuthenticatedRequestContext, require_authenticated_context
from backend.application.services.creative_versions import CreativeVersionApplicationService
from backend.core.exceptions import NotFoundAppError
from backend.core.log_context import bound_log_context
from backend.db.repositories import CreativeRepository
from backend.db.session import get_db
from backend.schemas.schemas import CreativeVersionRead

router = APIRouter(prefix="/creative-versions", tags=["creative-versions"])


@router.post(
    "/from-artifact/{artifact_id}",
    response_model=CreativeVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_version_from_artifact(
    artifact_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> CreativeVersionRead:
    with bound_log_context(artifact_id=str(artifact_id)):
        artifact = await CreativeRepository(db).get_stored_artifact(artifact_id)
        if (
            artifact is None
            or artifact.created_by_user_id != auth.user.id
            or artifact.project_id != auth.default_project.id
        ):
            raise NotFoundAppError("Artifact not found.")
        version = await CreativeVersionApplicationService(db).promote_artifact(artifact_id)
        return CreativeVersionRead.model_validate(version)
