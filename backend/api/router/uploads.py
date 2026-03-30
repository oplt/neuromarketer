from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.uploads import UploadApplicationService
from backend.db.session import get_db
from backend.schemas.uploads import (
    DirectUploadResponse,
    StoredArtifactRead,
    UploadInitRequest,
    UploadInitResponse,
    UploadSessionRead,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/init", response_model=UploadInitResponse)
async def init_upload(
    payload: UploadInitRequest,
    db: AsyncSession = Depends(get_db),
) -> UploadInitResponse:
    service = UploadApplicationService(db)
    upload_session = await service.create_upload_session(payload)
    await db.commit()
    return UploadInitResponse(
        upload_session_id=upload_session.id,
        upload_token=upload_session.upload_token,
        bucket_name=upload_session.bucket_name,
        storage_key=upload_session.storage_key,
        storage_uri=f"s3://{upload_session.bucket_name}/{upload_session.storage_key}",
        presigned_put_url=service.storage.generate_presigned_put_url(
            bucket_name=upload_session.bucket_name,
            storage_key=upload_session.storage_key,
            content_type=payload.mime_type,
        ),
    )


@router.post("/direct", response_model=DirectUploadResponse, status_code=status.HTTP_201_CREATED)
async def direct_upload(
    project_id: str = Form(...),
    creative_id: str | None = Form(None),
    creative_version_id: str | None = Form(None),
    artifact_kind: str = Form("creative_source"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DirectUploadResponse:
    service = UploadApplicationService(db)
    result = await service.handle_direct_upload(
        project_id=UUID(project_id),
        creative_id=UUID(creative_id) if creative_id else None,
        creative_version_id=UUID(creative_version_id) if creative_version_id else None,
        artifact_kind=artifact_kind,
        file=file,
    )
    return DirectUploadResponse(
        upload_session=UploadSessionRead.model_validate(result.upload_session),
        artifact=StoredArtifactRead.model_validate(result.artifact),
    )
