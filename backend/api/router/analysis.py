from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import AuthenticatedRequestContext, require_authenticated_context
from backend.api.rate_limit import limiter
from backend.application.services.analysis_comparisons import AnalysisComparisonApplicationService
from backend.application.services.analysis_evaluations import AnalysisEvaluationApplicationService
from backend.application.services.analysis_generated_variants import AnalysisGeneratedVariantsApplicationService
from backend.application.services.analysis_insights import AnalysisInsightsApplicationService
from backend.application.services.collaboration import CollaborationApplicationService
from backend.application.services.analysis import AnalysisApplicationService
from backend.core.config import settings
from backend.db.models import CollaborationEntityType
from backend.db.session import AsyncSessionLocal, get_db
from backend.services.analysis_job_events import close_analysis_job_subscription, open_analysis_job_subscription
from backend.services.analysis_goal_taxonomy import AnalysisChannel, GoalTemplate
from backend.schemas.analysis import (
    AnalysisAssetListResponse,
    AnalysisComparisonCreateRequest,
    AnalysisComparisonListResponse,
    AnalysisComparisonRead,
    AnalysisBenchmarkResponse,
    AnalysisCalibrationResponse,
    AnalysisConfigResponse,
    AnalysisClientEventRequest,
    AnalysisExecutiveVerdictRead,
    AnalysisGeneratedVariantCreateRequest,
    AnalysisGeneratedVariantListResponse,
    AnalysisJobCreateRequest,
    AnalysisJobListResponse,
    AnalysisJobStatusResponse,
    AnalysisGoalPresetsResponse,
    AnalysisOutcomeImportResponse,
    AnalysisResultRead,
    AnalysisUploadCompleteRequest,
    AnalysisUploadCompleteResponse,
    AnalysisUploadCreateRequest,
    AnalysisUploadCreateResponse,
    MediaType,
)
from backend.schemas.collaboration import (
    CollaborationCommentCreateRequest,
    CollaborationReviewRead,
    CollaborationReviewUpdateRequest,
    WorkspaceMemberListResponse,
)
from backend.schemas.evaluators import (
    EvaluationDispatchRequest,
    EvaluationListResponse,
    EvaluationMode,
    EvaluationRecordRead,
)
from backend.tasks import dispatch_prediction_job, dispatch_llm_evaluation_job

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _encode_sse_event(*, event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _decode_analysis_job_event_message(message: dict[str, Any] | None) -> dict[str, Any] | None:
    if not message:
        return None
    raw_payload = message.get("data")
    if not isinstance(raw_payload, str) or not raw_payload.strip():
        return None
    try:
        decoded = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


async def _load_analysis_job_snapshot(*, user_id: UUID, job_id: UUID) -> AnalysisJobStatusResponse:
    async with AsyncSessionLocal() as session:
        return await AnalysisApplicationService(session).get_analysis_job(user_id=user_id, job_id=job_id)


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


@router.get("/goal-presets", response_model=AnalysisGoalPresetsResponse)
async def get_analysis_goal_presets(
    db: AsyncSession = Depends(get_db),
    _: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisGoalPresetsResponse:
    return AnalysisApplicationService(db).get_goal_presets()


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def track_analysis_client_event(
    payload: AnalysisClientEventRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> dict[str, str]:
    await AnalysisApplicationService(db).track_client_event(
        user_id=auth.user.id,
        payload=payload,
    )
    return {"status": "accepted"}


@router.get("/comparisons", response_model=AnalysisComparisonListResponse)
async def list_analysis_comparisons(
    limit: int = Query(default=12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisComparisonListResponse:
    return await AnalysisComparisonApplicationService(db).list_comparisons(
        project_id=auth.default_project.id,
        limit=limit,
    )


@router.post("/comparisons", response_model=AnalysisComparisonRead, status_code=status.HTTP_201_CREATED)
async def create_analysis_comparison(
    payload: AnalysisComparisonCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisComparisonRead:
    return await AnalysisComparisonApplicationService(db).create_comparison(
        user_id=auth.user.id,
        project_id=auth.default_project.id,
        payload=payload,
    )


@router.get("/comparisons/{comparison_id}", response_model=AnalysisComparisonRead)
async def get_analysis_comparison(
    comparison_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisComparisonRead:
    return await AnalysisComparisonApplicationService(db).get_comparison(
        project_id=auth.default_project.id,
        comparison_id=comparison_id,
    )


@router.get("/collaboration/members", response_model=WorkspaceMemberListResponse)
async def list_collaboration_members(
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> WorkspaceMemberListResponse:
    return await CollaborationApplicationService(db).list_workspace_members(
        organization_id=auth.organization.id,
    )


@router.get("/collaboration/{entity_type}/{entity_id}", response_model=CollaborationReviewRead)
async def get_collaboration_review(
    entity_type: CollaborationEntityType,
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> CollaborationReviewRead:
    return await CollaborationApplicationService(db).get_review(
        project_id=auth.default_project.id,
        organization_id=auth.organization.id,
        entity_type=entity_type,
        entity_id=entity_id,
    )


@router.put("/collaboration/{entity_type}/{entity_id}", response_model=CollaborationReviewRead)
async def update_collaboration_review(
    entity_type: CollaborationEntityType,
    entity_id: UUID,
    payload: CollaborationReviewUpdateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> CollaborationReviewRead:
    return await CollaborationApplicationService(db).update_review(
        user_id=auth.user.id,
        project_id=auth.default_project.id,
        organization_id=auth.organization.id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )


@router.post("/collaboration/{entity_type}/{entity_id}/comments", response_model=CollaborationReviewRead, status_code=status.HTTP_201_CREATED)
async def create_collaboration_comment(
    entity_type: CollaborationEntityType,
    entity_id: UUID,
    payload: CollaborationCommentCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> CollaborationReviewRead:
    return await CollaborationApplicationService(db).add_comment(
        user_id=auth.user.id,
        project_id=auth.default_project.id,
        organization_id=auth.organization.id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
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


@router.get("/assets/{asset_id}/media")
@limiter.limit("30/minute")
async def get_analysis_asset_media(
    asset_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> Response:
    asset, body, content_type = await AnalysisApplicationService(db).get_asset_media(
        user_id=auth.user.id,
        project_id=auth.default_project.id,
        asset_id=asset_id,
    )
    response = Response(
        content=body,
        media_type=content_type or "application/octet-stream",
    )
    if asset.original_filename:
        response.headers["Content-Disposition"] = f'inline; filename="{asset.original_filename}"'
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@router.get("/jobs", response_model=AnalysisJobListResponse)
async def list_analysis_jobs(
    media_type: MediaType | None = Query(default=None),
    goal_template: GoalTemplate | None = Query(default=None),
    channel: AnalysisChannel | None = Query(default=None),
    audience_contains: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisJobListResponse:
    return await AnalysisApplicationService(db).list_jobs(
        user_id=auth.user.id,
        project_id=auth.default_project.id,
        media_type=media_type,
        goal_template=goal_template,
        channel=channel,
        audience_contains=audience_contains,
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
@limiter.limit("20/minute")
async def create_analysis_job(
    payload: AnalysisJobCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisJobStatusResponse:
    service = AnalysisApplicationService(db)
    response = await service.create_analysis_job(
        user_id=auth.user.id,
        asset_id=payload.asset_id,
        project_id=auth.default_project.id,
        objective=payload.objective,
        goal_template=payload.goal_template,
        channel=payload.channel,
        audience_segment=payload.audience_segment,
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


@router.post("/jobs/{job_id}/rerun", response_model=AnalysisJobStatusResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
async def rerun_analysis_job(
    job_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisJobStatusResponse:
    """Re-queue a failed or canceled analysis job without re-uploading the asset."""
    from backend.application.services.predictions import PredictionApplicationService

    svc = PredictionApplicationService(db)
    await svc.rerun_job(job_id=job_id, user_id=auth.user.id)
    await db.commit()
    await dispatch_prediction_job(job_id)
    return await AnalysisApplicationService(db).get_analysis_job(user_id=auth.user.id, job_id=job_id)


@router.get("/jobs/{job_id}/events")
async def stream_analysis_job_events(
    job_id: UUID,
    request: Request,
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> StreamingResponse:
    await _load_analysis_job_snapshot(user_id=auth.user.id, job_id=job_id)

    async def event_stream():
        subscription = await open_analysis_job_subscription(job_id)
        last_snapshot_json: str | None = None
        heartbeat_elapsed = 0.0

        try:
            initial_snapshot = await _load_analysis_job_snapshot(user_id=auth.user.id, job_id=job_id)
            initial_payload = initial_snapshot.model_dump(mode="json")
            last_snapshot_json = json.dumps(initial_payload, sort_keys=True)
            yield _encode_sse_event(event="status", data=initial_payload)

            if initial_snapshot.job.status in {"completed", "failed"}:
                yield _encode_sse_event(event="done", data=initial_payload)
                return

            while True:
                if await request.is_disconnected():
                    break

                if subscription is None:
                    await asyncio.sleep(1.0)
                    heartbeat_elapsed += 1.0
                    if heartbeat_elapsed >= 15.0:
                        yield _encode_sse_event(
                            event="heartbeat",
                            data={"job_id": str(job_id)},
                        )
                        heartbeat_elapsed = 0.0
                else:
                    _, pubsub = subscription
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=10.0,
                    )
                    if message is None:
                        heartbeat_elapsed += 10.0
                        if heartbeat_elapsed >= 15.0:
                            yield _encode_sse_event(
                                event="heartbeat",
                                data={"job_id": str(job_id)},
                            )
                            heartbeat_elapsed = 0.0
                    else:
                        heartbeat_elapsed = 0.0
                        decoded_message = _decode_analysis_job_event_message(message)
                        progress_payload = (decoded_message or {}).get("payload") or {}
                        if decoded_message is not None and (
                            decoded_message.get("event_type") == "job_progress"
                            or progress_payload.get("stage") is not None
                            or progress_payload.get("diagnostics")
                        ):
                            progress_payload = decoded_message.get("payload") or {}
                            snapshot = await _load_analysis_job_snapshot(user_id=auth.user.id, job_id=job_id)
                            yield _encode_sse_event(
                                event="progress",
                                data={
                                    "job": snapshot.job.model_dump(mode="json"),
                                    "asset": snapshot.asset.model_dump(mode="json") if snapshot.asset is not None else None,
                                    "result": progress_payload.get("partial_result"),
                                    "stage": progress_payload.get("stage")
                                    or (snapshot.progress.stage if snapshot.progress is not None else None),
                                    "stage_label": progress_payload.get("stage_label")
                                    or (snapshot.progress.stage_label if snapshot.progress is not None else None),
                                    "diagnostics": progress_payload.get("diagnostics")
                                    or (
                                        snapshot.progress.diagnostics.model_dump(mode="json")
                                        if snapshot.progress is not None
                                        else {}
                                    ),
                                    "is_partial": bool(
                                        progress_payload.get("is_partial")
                                        or progress_payload.get("partial_result")
                                        or (snapshot.progress.is_partial if snapshot.progress is not None else False)
                                    ),
                                },
                            )

                snapshot = await _load_analysis_job_snapshot(user_id=auth.user.id, job_id=job_id)
                payload = snapshot.model_dump(mode="json")
                snapshot_json = json.dumps(payload, sort_keys=True)
                if snapshot_json != last_snapshot_json:
                    yield _encode_sse_event(event="status", data=payload)
                    last_snapshot_json = snapshot_json

                if snapshot.job.status in {"completed", "failed"}:
                    yield _encode_sse_event(event="done", data=payload)
                    break
        finally:
            await close_analysis_job_subscription(subscription)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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


@router.get("/jobs/{job_id}/benchmarks", response_model=AnalysisBenchmarkResponse)
async def get_analysis_benchmarks(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisBenchmarkResponse:
    return await AnalysisInsightsApplicationService(db).get_benchmark(
        user_id=auth.user.id,
        job_id=job_id,
    )


@router.get("/jobs/{job_id}/verdict", response_model=AnalysisExecutiveVerdictRead)
async def get_analysis_executive_verdict(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisExecutiveVerdictRead:
    return await AnalysisInsightsApplicationService(db).get_executive_verdict(
        user_id=auth.user.id,
        job_id=job_id,
    )


@router.get("/jobs/{job_id}/calibration", response_model=AnalysisCalibrationResponse)
async def get_analysis_calibration(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisCalibrationResponse:
    return await AnalysisInsightsApplicationService(db).get_calibration(
        user_id=auth.user.id,
        job_id=job_id,
    )


@router.get("/jobs/{job_id}/variants", response_model=AnalysisGeneratedVariantListResponse)
async def list_generated_variants(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisGeneratedVariantListResponse:
    return await AnalysisGeneratedVariantsApplicationService(db).list_variants(
        user_id=auth.user.id,
        job_id=job_id,
    )


@router.post(
    "/jobs/{job_id}/variants",
    response_model=AnalysisGeneratedVariantListResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_analysis_variants(
    job_id: UUID,
    payload: AnalysisGeneratedVariantCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisGeneratedVariantListResponse:
    return await AnalysisGeneratedVariantsApplicationService(db).generate_variants(
        user_id=auth.user.id,
        job_id=job_id,
        payload=payload,
    )


@router.post("/outcomes/import", response_model=AnalysisOutcomeImportResponse, status_code=status.HTTP_201_CREATED)
async def import_analysis_outcomes(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    auth: AuthenticatedRequestContext = Depends(require_authenticated_context),
) -> AnalysisOutcomeImportResponse:
    return await AnalysisInsightsApplicationService(db).import_outcomes_csv(
        user_id=auth.user.id,
        project_id=auth.default_project.id,
        file=file,
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
