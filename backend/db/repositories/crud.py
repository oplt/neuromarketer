from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
import re
from uuid import UUID

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.security import hash_password
from backend.db.models import (
    Creative,
    CreativeComparison,
    CreativeComparisonItem,
    CreativeComparisonItemResult,
    CreativeComparisonResult,
    CreativeStatus,
    CreativeVersion,
    InferenceJob,
    JobMetric,
    JobStatus,
    Organization,
    OrganizationMembership,
    OrgRole,
    OptimizationSuggestion,
    PredictionResult,
    PredictionScore,
    PredictionTimelinePoint,
    PredictionType,
    PredictionVisualization,
    Project,
    SuggestionStatus,
    User,
)
from backend.schemas.schemas import (
    CreativeCreate,
    CreativeVersionCreate,
    ProjectCreate,
)

DEFAULT_PROJECT_NAME = "Default Analysis Project"
DEFAULT_PROJECT_DESCRIPTION = "System-created project used by the Analysis workspace."


# ---------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------

def _slugify_workspace_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "workspace"


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email.strip().lower())
    )
    return result.scalar_one_or_none()


async def _build_unique_organization_slug(db: AsyncSession, base_name: str) -> str:
    base_slug = _slugify_workspace_name(base_name)
    candidate = base_slug
    suffix = 2

    while True:
        result = await db.execute(
            select(Organization.id).where(Organization.slug == candidate)
        )
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


async def create_user_with_workspace(
    db: AsyncSession,
    *,
    email: str,
    full_name: str,
    password: str,
) -> tuple[User, Organization, Project]:
    normalized_email = email.strip().lower()
    cleaned_name = full_name.strip()
    name_parts = cleaned_name.split(maxsplit=1)
    first_name = name_parts[0] if name_parts else None
    last_name = name_parts[1] if len(name_parts) > 1 else None
    workspace_name = f"{cleaned_name}'s Workspace" if cleaned_name else "Workspace"
    workspace_slug = await _build_unique_organization_slug(db, workspace_name)

    user = User(
        email=normalized_email,
        first_name=first_name,
        last_name=last_name,
        password_hash=hash_password(password),
        is_active=True,
        is_verified=False,
    )
    organization = Organization(
        name=workspace_name,
        slug=workspace_slug,
        billing_email=normalized_email,
        is_active=True,
        settings={},
    )
    membership = OrganizationMembership(
        organization=organization,
        user=user,
        role=OrgRole.OWNER,
    )
    project = Project(
        organization=organization,
        created_by_user=user,
        name=DEFAULT_PROJECT_NAME,
        description=DEFAULT_PROJECT_DESCRIPTION,
        settings={"system_managed": True, "surface": "analysis"},
    )

    db.add_all([user, organization, membership, project])
    await db.commit()
    await db.refresh(user)
    await db.refresh(organization)
    await db.refresh(project)
    return user, organization, project


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_primary_organization_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Organization | None:
    result = await db.execute(
        select(Organization)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(OrganizationMembership.user_id == user_id)
        .order_by(Organization.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_default_project_for_organization(
    db: AsyncSession,
    organization_id: UUID,
) -> Project | None:
    result = await db.execute(
        select(Project)
        .where(Project.organization_id == organization_id)
        .order_by(Project.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_or_create_default_project_for_organization(
    db: AsyncSession,
    *,
    organization_id: UUID,
    created_by_user_id: UUID | None,
) -> Project:
    existing = await get_default_project_for_organization(db, organization_id)
    if existing is not None:
        return existing

    project = Project(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        name=DEFAULT_PROJECT_NAME,
        description=DEFAULT_PROJECT_DESCRIPTION,
        settings={"system_managed": True, "surface": "analysis"},
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


# ---------------------------------------------------------------------
# Project / creative
# ---------------------------------------------------------------------

async def create_project(db: AsyncSession, payload: ProjectCreate) -> Project:
    obj = Project(
        organization_id=payload.organization_id,
        created_by_user_id=payload.created_by_user_id,
        name=payload.name,
        description=payload.description,
        external_ref=payload.external_ref,
        settings=payload.settings,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def get_project(db: AsyncSession, project_id: UUID) -> Project | None:
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    return result.scalar_one_or_none()


async def create_creative(db: AsyncSession, payload: CreativeCreate) -> Creative:
    obj = Creative(
        project_id=payload.project_id,
        created_by_user_id=payload.created_by_user_id,
        name=payload.name,
        asset_type=payload.asset_type,
        tags=payload.tags,
        metadata_json=payload.metadata_json,
        status=CreativeStatus.DRAFT,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def get_creative(db: AsyncSession, creative_id: UUID) -> Creative | None:
    result = await db.execute(
        select(Creative).where(Creative.id == creative_id)
    )
    return result.scalar_one_or_none()


async def create_creative_version(
    db: AsyncSession,
    payload: CreativeVersionCreate,
) -> CreativeVersion:
    if payload.is_current:
        await db.execute(
            update(CreativeVersion)
            .where(CreativeVersion.creative_id == payload.creative_id)
            .values(is_current=False)
        )

    obj = CreativeVersion(
        creative_id=payload.creative_id,
        version_number=payload.version_number,
        is_current=payload.is_current,
        source_uri=payload.source_uri,
        mime_type=payload.mime_type,
        file_size_bytes=payload.file_size_bytes,
        sha256=payload.sha256,
        raw_text=payload.raw_text,
        source_url=str(payload.source_url) if payload.source_url else None,
        html_snapshot_uri=payload.html_snapshot_uri,
        duration_ms=payload.duration_ms,
        width_px=payload.width_px,
        height_px=payload.height_px,
        frame_rate=payload.frame_rate,
        extracted_metadata=payload.extracted_metadata,
        preprocessing_summary=payload.preprocessing_summary,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def get_creative_version(db: AsyncSession, creative_version_id: UUID) -> CreativeVersion | None:
    result = await db.execute(
        select(CreativeVersion).where(CreativeVersion.id == creative_version_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------
# Inference jobs / prediction results
# ---------------------------------------------------------------------

async def create_inference_job(
    db: AsyncSession,
    *,
    project_id: UUID,
    creative_id: UUID,
    creative_version_id: UUID,
    created_by_user_id: UUID | None,
    request_payload: dict,
    runtime_params: dict,
    prediction_type: PredictionType = PredictionType.SINGLE_ASSET,
) -> InferenceJob:
    job = InferenceJob(
        project_id=project_id,
        creative_id=creative_id,
        creative_version_id=creative_version_id,
        created_by_user_id=created_by_user_id,
        prediction_type=prediction_type,
        status=JobStatus.QUEUED,
        request_payload=request_payload,
        runtime_params=runtime_params,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def mark_job_running(db: AsyncSession, job_id: UUID) -> InferenceJob | None:
    result = await db.execute(
        select(InferenceJob).where(InferenceJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return job


async def mark_job_failed(db: AsyncSession, job_id: UUID, error_message: str) -> InferenceJob | None:
    result = await db.execute(
        select(InferenceJob).where(InferenceJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    job.status = JobStatus.FAILED
    job.error_message = error_message
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return job


async def add_job_metric(
    db: AsyncSession,
    *,
    job_id: UUID,
    metric_name: str,
    metric_value: Decimal,
    metric_unit: str | None = None,
    metadata_json: dict | None = None,
) -> JobMetric:
    metric = JobMetric(
        job_id=job_id,
        metric_name=metric_name,
        metric_value=metric_value,
        metric_unit=metric_unit,
        metadata_json=metadata_json or {},
    )
    db.add(metric)
    await db.commit()
    await db.refresh(metric)
    return metric


async def create_prediction_result(
    db: AsyncSession,
    *,
    job_id: UUID,
    project_id: UUID,
    creative_id: UUID,
    creative_version_id: UUID,
    raw_brain_response_uri: str | None,
    raw_brain_response_summary: dict,
    reduced_feature_vector: dict,
    region_activation_summary: dict,
    provenance_json: dict,
) -> PredictionResult:
    obj = PredictionResult(
        job_id=job_id,
        project_id=project_id,
        creative_id=creative_id,
        creative_version_id=creative_version_id,
        raw_brain_response_uri=raw_brain_response_uri,
        raw_brain_response_summary=raw_brain_response_summary,
        reduced_feature_vector=reduced_feature_vector,
        region_activation_summary=region_activation_summary,
        provenance_json=provenance_json,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def create_prediction_score(
    db: AsyncSession,
    *,
    prediction_result_id: UUID,
    score_type: str,
    normalized_score: Decimal,
    raw_value: Decimal | None = None,
    confidence: Decimal | None = None,
    percentile: Decimal | None = None,
    metadata_json: dict | None = None,
) -> PredictionScore:
    obj = PredictionScore(
        prediction_result_id=prediction_result_id,
        score_type=score_type,
        normalized_score=normalized_score,
        raw_value=raw_value,
        confidence=confidence,
        percentile=percentile,
        metadata_json=metadata_json or {},
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def create_prediction_visualization(
    db: AsyncSession,
    *,
    prediction_result_id: UUID,
    visualization_type: str,
    title: str | None,
    storage_uri: str | None,
    data_json: dict,
) -> PredictionVisualization:
    obj = PredictionVisualization(
        prediction_result_id=prediction_result_id,
        visualization_type=visualization_type,
        title=title,
        storage_uri=storage_uri,
        data_json=data_json,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def create_timeline_points(
    db: AsyncSession,
    *,
    prediction_result_id: UUID,
    points: list[dict],
) -> None:
    rows = [
        PredictionTimelinePoint(
            prediction_result_id=prediction_result_id,
            timestamp_ms=point["timestamp_ms"],
            attention_score=point.get("attention_score"),
            emotion_score=point.get("emotion_score"),
            memory_score=point.get("memory_score"),
            cognitive_load_score=point.get("cognitive_load_score"),
            conversion_proxy_score=point.get("conversion_proxy_score"),
            metadata_json=point.get("metadata_json", {}),
        )
        for point in points
    ]
    db.add_all(rows)
    await db.commit()


async def create_optimization_suggestion(
    db: AsyncSession,
    *,
    prediction_result_id: UUID,
    suggestion_type: str,
    title: str,
    rationale: str,
    proposed_change_json: dict,
    expected_score_lift_json: dict,
    confidence: Decimal | None = None,
) -> OptimizationSuggestion:
    obj = OptimizationSuggestion(
        prediction_result_id=prediction_result_id,
        suggestion_type=suggestion_type,
        status=SuggestionStatus.PROPOSED,
        title=title,
        rationale=rationale,
        proposed_change_json=proposed_change_json,
        expected_score_lift_json=expected_score_lift_json,
        confidence=confidence,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def mark_job_succeeded(db: AsyncSession, job_id: UUID) -> InferenceJob | None:
    result = await db.execute(
        select(InferenceJob).where(InferenceJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    job.status = JobStatus.SUCCEEDED
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job_with_prediction(db: AsyncSession, job_id: UUID) -> InferenceJob | None:
    result = await db.execute(
        select(InferenceJob)
        .options(
            selectinload(InferenceJob.prediction).selectinload(PredictionResult.scores),
            selectinload(InferenceJob.prediction).selectinload(PredictionResult.visualizations),
            selectinload(InferenceJob.prediction).selectinload(PredictionResult.timeline_points),
            selectinload(InferenceJob.prediction).selectinload(PredictionResult.suggestions),
        )
        .where(InferenceJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def get_prediction_result_full(
    db: AsyncSession,
    prediction_result_id: UUID,
) -> PredictionResult | None:
    result = await db.execute(
        select(PredictionResult)
        .options(
            selectinload(PredictionResult.scores),
            selectinload(PredictionResult.visualizations),
            selectinload(PredictionResult.timeline_points),
            selectinload(PredictionResult.suggestions),
        )
        .where(PredictionResult.id == prediction_result_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------

async def create_comparison(
    db: AsyncSession,
    *,
    project_id: UUID,
    name: str,
    creative_version_ids: list[UUID],
    comparison_context: dict,
) -> CreativeComparison:
    comparison = CreativeComparison(
        project_id=project_id,
        name=name,
        comparison_context=comparison_context,
    )
    db.add(comparison)
    await db.flush()

    versions_result = await db.execute(
        select(CreativeVersion).where(CreativeVersion.id.in_(creative_version_ids))
    )
    versions = list(versions_result.scalars().all())

    version_by_id = {version.id: version for version in versions}

    for creative_version_id in creative_version_ids:
        version = version_by_id[creative_version_id]
        db.add(
            CreativeComparisonItem(
                comparison_id=comparison.id,
                creative_id=version.creative_id,
                creative_version_id=creative_version_id,
            )
        )

    await db.commit()
    await db.refresh(comparison)
    return comparison


async def save_comparison_result(
    db: AsyncSession,
    *,
    comparison_id: UUID,
    winning_creative_version_id: UUID | None,
    summary_json: dict,
    items: list[dict],
) -> CreativeComparisonResult:
    comparison_result = CreativeComparisonResult(
        comparison_id=comparison_id,
        winning_creative_version_id=winning_creative_version_id,
        summary_json=summary_json,
    )
    db.add(comparison_result)
    await db.flush()

    for item in items:
        db.add(
            CreativeComparisonItemResult(
                comparison_result_id=comparison_result.id,
                creative_version_id=item["creative_version_id"],
                overall_rank=item["overall_rank"],
                scores_json=item["scores_json"],
                rationale=item.get("rationale"),
            )
        )

    await db.commit()
    await db.refresh(comparison_result)
    return comparison_result


async def get_comparison_result(
    db: AsyncSession,
    comparison_id: UUID,
) -> CreativeComparisonResult | None:
    result = await db.execute(
        select(CreativeComparisonResult)
        .options(selectinload(CreativeComparisonResult.item_results))
        .where(CreativeComparisonResult.comparison_id == comparison_id)
    )
    return result.scalar_one_or_none()
