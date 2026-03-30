from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.creative_versions import CreativeVersionApplicationService
from backend.db.session import get_db
from backend.schemas.schemas import CreativeVersionRead

router = APIRouter(prefix="/creative-versions", tags=["creative-versions"])


@router.post("/from-artifact/{artifact_id}", response_model=CreativeVersionRead, status_code=status.HTTP_201_CREATED)
async def create_version_from_artifact(
    artifact_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CreativeVersionRead:
    version = await CreativeVersionApplicationService(db).promote_artifact(artifact_id)
    return CreativeVersionRead.model_validate(version)
