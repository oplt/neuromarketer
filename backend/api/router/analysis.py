from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import AuthenticatedRequestContext, require_authenticated_context
from backend.application.services.analysis_evaluations import AnalysisEvaluationApplicationService
from backend.application.services.analysis import AnalysisApplicationService
from backend.core.config import settings
from backend.db.session import get_db
from backend.schemas.analysis import (
    AnalysisAssetListResponse,
    AnalysisConfigResponse,
    AnalysisJobCreateRequest,
    AnalysisJobStatusResponse,
    AnalysisResultRead,
    AnalysisUploadCompleteRequest,
    AnalysisUploadCompleteResponse,
    AnalysisUploadCreateRequest,
    AnalysisUploadCreateResponse,
    MediaType,
)
from backend.schemas.evaluators import (
    EvaluationDispatchRequest,
    EvaluationListResponse,
    EvaluationMode,
    EvaluationRecordRead,
)
from backend.tasks import dispatch_prediction_job

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


@router.get("/assets", response_model=AnalysisAssetListResponse)
async def list_analysis_assets(
    media_type: MediaType | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisAssetListResponse:
    return await AnalysisApplicationService(db).list_assets(
        user_id=auth.user.id,
        project_id=auth.default_project.id,
        media_type=media_type,
        limit=limit,
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


@router.post(
    "/uploads/{upload_session_id}/fallback",
    response_model=AnalysisUploadCompleteResponse,
)
async def fallback_analysis_upload(
    upload_session_id: UUID,
    upload_token: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisUploadCompleteResponse:
    return await AnalysisApplicationService(db).upload_via_backend(
        user_id=auth.user.id,
        upload_session_id=upload_session_id,
        upload_token=upload_token,
        file=file,
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
    await dispatch_prediction_job(response.job.id)
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


@router.post(
    "/jobs/{job_id}/evaluate",
    response_model=EvaluationListResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_llm_evaluations(
    job_id: UUID,
    payload: EvaluationDispatchRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> EvaluationListResponse:
    return await AnalysisEvaluationApplicationService(db).request_evaluations(
        user_id=auth.user.id,
        job_id=job_id,
        payload=payload,
    )


@router.get("/jobs/{job_id}/evaluations", response_model=EvaluationListResponse)
async def list_llm_evaluations(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> EvaluationListResponse:
    return await AnalysisEvaluationApplicationService(db).list_evaluations(
        user_id=auth.user.id,
        job_id=job_id,
    )


@router.get("/jobs/{job_id}/evaluations/{mode}", response_model=EvaluationRecordRead)
async def get_llm_evaluation(
    job_id: UUID,
    mode: EvaluationMode,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> EvaluationRecordRead:
    return await AnalysisEvaluationApplicationService(db).get_evaluation(
        user_id=auth.user.id,
        job_id=job_id,
        mode=mode,
    )
