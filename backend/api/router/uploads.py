from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.rate_limit import limiter
from backend.application.services.uploads import UploadApplicationService
from backend.core.log_context import bound_log_context
from backend.db.repositories.uploads import UploadRepository
from backend.db.session import get_db
from backend.schemas.uploads import (
    DirectUploadResponse,
    StoredArtifactRead,
    UploadInitRequest,
    UploadInitResponse,
    UploadSessionRead,
)
from backend.services.storage import S3StorageService

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("/init", response_model=UploadInitResponse)
@limiter.limit("30/minute")
async def init_upload(
    payload: UploadInitRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UploadInitResponse:
    with bound_log_context(
        project_id=str(payload.project_id),
        creative_id=str(payload.creative_id) if payload.creative_id else None,
        creative_version_id=str(payload.creative_version_id)
        if payload.creative_version_id
        else None,
    ):
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
@limiter.limit("20/minute")
async def direct_upload(
    request: Request,
    project_id: str = Form(...),
    creative_id: str | None = Form(None),
    creative_version_id: str | None = Form(None),
    artifact_kind: str = Form("creative_source"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DirectUploadResponse:
    resolved_project_id = UUID(project_id)
    resolved_creative_id = UUID(creative_id) if creative_id else None
    resolved_creative_version_id = UUID(creative_version_id) if creative_version_id else None
    with bound_log_context(
        project_id=str(resolved_project_id),
        creative_id=str(resolved_creative_id) if resolved_creative_id else None,
        creative_version_id=str(resolved_creative_version_id)
        if resolved_creative_version_id
        else None,
    ):
        service = UploadApplicationService(db)
        result = await service.handle_direct_upload(
            project_id=resolved_project_id,
            creative_id=resolved_creative_id,
            creative_version_id=resolved_creative_version_id,
            artifact_kind=artifact_kind,
            file=file,
        )
        return DirectUploadResponse(
            upload_session=UploadSessionRead.model_validate(result.upload_session),
            artifact=StoredArtifactRead.model_validate(result.artifact),
        )


@router.get("/{artifact_id}/download-url")
@limiter.limit("60/minute")
async def get_download_url(
    artifact_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = UploadRepository(db)
    artifact = await repo.get_stored_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    storage = S3StorageService()
    url = storage.generate_presigned_get_url(
        bucket_name=artifact.bucket_name,
        storage_key=artifact.storage_key,
    )
    if url is None:
        raise HTTPException(status_code=502, detail="Could not generate download URL.")
    return {"url": url}
