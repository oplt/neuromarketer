from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import AuthenticatedRequestContext, require_authenticated_context
from backend.application.services.analysis import AnalysisApplicationService
from backend.core.config import settings
from backend.core.exceptions import AppError
from backend.db.session import get_db
from backend.schemas.analysis import (
    AnalysisConfigResponse,
    AnalysisJobCreateRequest,
    AnalysisJobStatusResponse,
    AnalysisResultRead,
    AnalysisUploadCompleteRequest,
    AnalysisUploadCompleteResponse,
    AnalysisUploadCreateRequest,
    AnalysisUploadCreateResponse,
)
from backend.tasks import process_prediction_job_task

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/config", response_model=AnalysisConfigResponse)
async def get_analysis_config(
    _: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisConfigResponse:
    return AnalysisConfigResponse(
        max_file_size_bytes=settings.upload_max_size_bytes,
        max_text_characters=settings.analysis_max_text_characters,
        allowed_media_types=["video", "audio", "text"],
        allowed_mime_types={
            "video": settings.analysis_allowed_video_mime_types,
            "audio": settings.analysis_allowed_audio_mime_types,
            "text": settings.analysis_allowed_text_mime_types,
        },
    )


@router.post("/uploads", response_model=AnalysisUploadCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis_upload_session(
    payload: AnalysisUploadCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisUploadCreateResponse:
    return await AnalysisApplicationService(db).create_upload_session(
        user_id=auth.user.id,
        project_id=auth.default_project.id,
        payload=payload,
    )


@router.post(
    "/uploads/{upload_session_id}/complete",
    response_model=AnalysisUploadCompleteResponse,
)
async def complete_analysis_upload(
    upload_session_id: UUID,
    payload: AnalysisUploadCompleteRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisUploadCompleteResponse:
    return await AnalysisApplicationService(db).complete_upload(
        user_id=auth.user.id,
        upload_session_id=upload_session_id,
        upload_token=payload.upload_token,
    )


@router.post("/jobs", response_model=AnalysisJobStatusResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis_job(
    payload: AnalysisJobCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisJobStatusResponse:
    service = AnalysisApplicationService(db)
    response = await service.create_analysis_job(
        user_id=auth.user.id,
        asset_id=payload.asset_id,
        project_id=auth.default_project.id,
        objective=payload.objective,
    )
    try:
        process_prediction_job_task.delay(str(response.job.id))
    except Exception as exc:
        await service.predictions.mark_job_failed(response.job.id, f"Job dispatch failed: {exc}")
        await db.commit()
        raise AppError(
            "Analysis job could not be queued.",
            code="queue_unavailable",
            status_code=503,
        ) from exc
    return await service.get_analysis_job(user_id=auth.user.id, job_id=response.job.id)


@router.get("/jobs/{job_id}", response_model=AnalysisJobStatusResponse)
async def get_analysis_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisJobStatusResponse:
    return await AnalysisApplicationService(db).get_analysis_job(
        user_id=auth.user.id,
        job_id=job_id,
    )


@router.get("/jobs/{job_id}/results", response_model=AnalysisResultRead)
async def get_analysis_results(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisResultRead:
    return await AnalysisApplicationService(db).get_analysis_result(
        user_id=auth.user.id,
        job_id=job_id,
    )
