from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.comparison import ComparisonApplicationService
from backend.application.services.optimization import OptimizationApplicationService
from backend.application.services.predictions import PredictionApplicationService
from backend.core.exceptions import AppError
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
from backend.tasks import process_prediction_job_task

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("", response_model=PredictResponse, status_code=status.HTTP_202_ACCEPTED)
async def predict(
    payload: PredictRequest,
    db: AsyncSession = Depends(get_db),
) -> PredictResponse:
    service = PredictionApplicationService(db)
    job = await service.create_prediction_job(payload)
    try:
        process_prediction_job_task.delay(str(job.id))
    except Exception as exc:
        await service.mark_job_failed(job.id, f"Job dispatch failed: {exc}")
        await db.commit()
        raise AppError(
            "Prediction job could not be queued.",
            code="queue_unavailable",
            status_code=503,
        ) from exc
    hydrated_job = await service.get_job(job.id)
    return PredictResponse(
        job=hydrated_job,
        prediction_result=hydrated_job.prediction,
    )


@router.get("/jobs/{job_id}", response_model=PredictResponse)
async def get_prediction_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PredictResponse:
    job = await PredictionApplicationService(db).get_job(job_id)
    return PredictResponse(job=job, prediction_result=job.prediction)


@router.post("/compare", response_model=CompareResponse)
async def compare_creatives(
    payload: CompareRequest,
    db: AsyncSession = Depends(get_db),
) -> CompareResponse:
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
            for item in sorted(result.item_results, key=lambda candidate: candidate.overall_rank)
        ],
    )


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_prediction(
    payload: OptimizeRequest,
    db: AsyncSession = Depends(get_db),
) -> OptimizeResponse:
    prediction = await PredictionApplicationService(db).get_prediction_result(payload.prediction_result_id)
    suggestions = OptimizationApplicationService().optimize(
        prediction=prediction,
        max_suggestions=payload.max_suggestions,
        constraints=payload.constraints,
    )
    return OptimizeResponse(prediction_result_id=prediction.id, suggestions=suggestions)
