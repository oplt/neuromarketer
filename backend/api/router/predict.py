from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.comparison import ComparisonApplicationService
from backend.application.services.optimization import OptimizationApplicationService
from backend.application.services.predictions import PredictionApplicationService
from backend.core.log_context import bound_log_context
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


@router.post("", response_model=PredictResponse, status_code=status.HTTP_202_ACCEPTED)
async def predict(
    payload: PredictRequest,
    db: AsyncSession = Depends(get_db),
) -> PredictResponse:
    with bound_log_context(
        project_id=str(payload.project_id),
        creative_id=str(payload.creative_id),
        creative_version_id=str(payload.creative_version_id),
    ):
        service = PredictionApplicationService(db)
        job = await service.create_prediction_job(payload)
        await dispatch_prediction_job(job.id)
        hydrated_job = await service.get_job(job.id)
        return PredictResponse(
            job=hydrated_job,
            prediction_result=hydrated_job.prediction
            if hydrated_job.status.value == "succeeded"
            else None,
        )


@router.get("/jobs/{job_id}", response_model=PredictResponse)
async def get_prediction_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PredictResponse:
    with bound_log_context(job_id=str(job_id)):
        job = await PredictionApplicationService(db).get_job(job_id)
        return PredictResponse(
            job=job, prediction_result=job.prediction if job.status.value == "succeeded" else None
        )


@router.post("/compare", response_model=CompareResponse)
async def compare_creatives(
    payload: CompareRequest,
    db: AsyncSession = Depends(get_db),
) -> CompareResponse:
    with bound_log_context(project_id=str(payload.project_id)):
        comparison, result = await ComparisonApplicationService(db).compare(
            project_id=payload.project_id,
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
) -> OptimizeResponse:
    with bound_log_context(prediction_result_id=str(payload.prediction_result_id)):
        prediction = await PredictionApplicationService(db).get_prediction_result(
            payload.prediction_result_id
        )
        suggestions = OptimizationApplicationService().optimize(
            prediction=prediction,
            max_suggestions=payload.max_suggestions,
            constraints=payload.constraints,
        )
        return OptimizeResponse(prediction_result_id=prediction.id, suggestions=suggestions)
