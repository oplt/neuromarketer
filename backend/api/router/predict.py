from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import AuthenticatedRequestContext, require_authenticated_context
from backend.application.services.comparison import ComparisonApplicationService
from backend.application.services.optimization import OptimizationApplicationService
from backend.application.services.predictions import PredictionApplicationService
from backend.core.exceptions import NotFoundAppError
from backend.core.log_context import bound_log_context
from backend.db.repositories import CreativeRepository
from backend.db.session import get_db
from backend.schemas.schemas import (
    CompareItemResponse,
    CompareRequest,
    CompareResponse,
    OptimizeRequest,
    OptimizeResponse,
    PredictRequest,
    PredictResponse,
)
from backend.tasks import dispatch_prediction_job

router = APIRouter(prefix="/predictions", tags=["predictions"])


async def _resolve_project_id(
    *,
    db: AsyncSession,
    auth: AuthenticatedRequestContext,
    requested_project_id: UUID | None,
) -> UUID:
    if requested_project_id is None or requested_project_id == auth.default_project.id:
        return auth.default_project.id
    project = await CreativeRepository(db).get_project(requested_project_id)
    if project is None or project.organization_id != auth.organization.id:
        raise NotFoundAppError("Project not found.")
    return project.id


@router.post("", response_model=PredictResponse, status_code=status.HTTP_202_ACCEPTED)
async def predict(
    payload: PredictRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> PredictResponse:
    project_id = await _resolve_project_id(
        db=db,
        auth=auth,
        requested_project_id=payload.project_id,
    )
    resolved_payload = payload.model_copy(
        update={
            "project_id": project_id,
            "created_by_user_id": auth.user.id,
        }
    )
    with bound_log_context(
        project_id=str(resolved_payload.project_id),
        creative_id=str(resolved_payload.creative_id),
        creative_version_id=str(resolved_payload.creative_version_id),
    ):
        service = PredictionApplicationService(db)
        job = await service.create_prediction_job(resolved_payload)
        await dispatch_prediction_job(job.id)
        return PredictResponse(
            job=job,
            prediction_result=job.prediction
            if job.status.value == "succeeded"
            else None,
        )


@router.get("/jobs/{job_id}", response_model=PredictResponse)
async def get_prediction_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> PredictResponse:
    with bound_log_context(job_id=str(job_id)):
        job = await PredictionApplicationService(db).get_job(job_id)
        project = await CreativeRepository(db).get_project(job.project_id)
        if project is None or project.organization_id != auth.organization.id:
            raise NotFoundAppError("Job not found.")
        if job.created_by_user_id is not None and job.created_by_user_id != auth.user.id:
            raise NotFoundAppError("Job not found.")
        return PredictResponse(
            job=job, prediction_result=job.prediction if job.status.value == "succeeded" else None
        )


@router.post("/compare", response_model=CompareResponse)
async def compare_creatives(
    payload: CompareRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> CompareResponse:
    project_id = await _resolve_project_id(
        db=db,
        auth=auth,
        requested_project_id=payload.project_id,
    )
    with bound_log_context(project_id=str(project_id)):
        comparison, result = await ComparisonApplicationService(db).compare(
            project_id=project_id,
            name=payload.name,
            creative_version_ids=payload.creative_version_ids,
            comparison_context=payload.comparison_context,
        )
        return CompareResponse(
            comparison_id=comparison.id,
            winning_creative_version_id=result.winning_creative_version_id,
            summary_json=result.summary_json,
            items=[
                CompareItemResponse(
                    creative_version_id=item.creative_version_id,
                    overall_rank=item.overall_rank,
                    scores_json=item.scores_json,
                    rationale=item.rationale,
                )
                for item in sorted(
                    result.item_results, key=lambda candidate: candidate.overall_rank
                )
            ],
        )


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_prediction(
    payload: OptimizeRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> OptimizeResponse:
    with bound_log_context(prediction_result_id=str(payload.prediction_result_id)):
        prediction = await PredictionApplicationService(db).get_prediction_result(
            payload.prediction_result_id
        )
        project = await CreativeRepository(db).get_project(prediction.project_id)
        if project is None or project.organization_id != auth.organization.id:
            raise NotFoundAppError("Prediction result not found.")
        suggestions = OptimizationApplicationService().optimize(
            prediction=prediction,
            max_suggestions=payload.max_suggestions,
            constraints=payload.constraints,
        )
        return OptimizeResponse(prediction_result_id=prediction.id, suggestions=suggestions)
