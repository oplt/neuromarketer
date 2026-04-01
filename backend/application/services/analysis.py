from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.predictions import PredictionApplicationService
from backend.core.config import settings
from backend.core.log_context import bound_log_context
from backend.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.core.logging import (
    duration_ms,
    get_logger,
    log_event,
    log_exception,
    sha256_prefix,
    summarize_storage_reference,
)
from backend.db.models import AssetType, InferenceJob, JobStatus, UploadStatus
from backend.db.repositories import CreativeRepository, UploadRepository
from backend.schemas.analysis import (
    AnalysisAssetRead,
    AnalysisAssetListResponse,
    AnalysisConfigResponse,
    AnalysisClientEventRequest,
    AnalysisGoalPresetsResponse,
    AnalysisJobDiagnosticsRead,
    AnalysisJobRead,
    AnalysisJobListItemRead,
    AnalysisJobListResponse,
    AnalysisJobProgressRead,
    AnalysisJobStatusResponse,
    AnalysisResultRead,
    AnalysisUploadCreateRequest,
    AnalysisUploadCreateResponse,
    AnalysisUploadCompleteResponse,
    AnalysisUploadSessionRead,
)
from backend.schemas.schemas import PredictRequest
from backend.services.analysis_goal_taxonomy import (
    get_goal_presets_payload,
    normalize_analysis_channel,
    normalize_goal_template,
)
from backend.services.preprocess import PreprocessService
from backend.services.storage import ObjectStorageService, UploadedObject

logger = get_logger(__name__)


class AnalysisApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.creatives = CreativeRepository(session)
        self.uploads = UploadRepository(session)
        self.predictions = PredictionApplicationService(session)
        self.preprocess = PreprocessService()
        self.storage: ObjectStorageService | None = None

    def _storage(self) -> ObjectStorageService:
        if self.storage is None:
            self.storage = ObjectStorageService()
        return self.storage

    def get_config(self) -> AnalysisConfigResponse:
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

    def get_goal_presets(self) -> AnalysisGoalPresetsResponse:
        return AnalysisGoalPresetsResponse.model_validate(get_goal_presets_payload())

    async def track_client_event(
        self,
        *,
        user_id: UUID,
        payload: AnalysisClientEventRequest,
    ) -> None:
        log_event(
            logger,
            payload.event_name,
            user_id=str(user_id),
            job_id=str(payload.job_id) if payload.job_id is not None else None,
            media_type=payload.media_type,
            goal_template=payload.goal_template,
            channel=payload.channel,
            audience_segment=payload.audience_segment,
            metadata_json=payload.metadata_json,
            status="accepted",
        )

    async def list_assets(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        media_type: str | None,
        limit: int,
    ) -> AnalysisAssetListResponse:
        assets = await self.uploads.list_analysis_artifacts(
            project_id=project_id,
            created_by_user_id=user_id,
            limit=limit,
        )
        if media_type is not None:
            assets = [
                asset
                for asset in assets
                if str((asset.metadata_json or {}).get("media_type") or self._detect_media_type(asset.mime_type)) == media_type
            ]
        return AnalysisAssetListResponse(items=[self._build_asset_read(asset) for asset in assets])

    async def list_jobs(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        media_type: str | None,
        goal_template: str | None,
        channel: str | None,
        audience_contains: str | None,
        limit: int,
    ) -> AnalysisJobListResponse:
        fetch_limit = max(limit * 10, 50) if goal_template or channel or audience_contains else limit
        jobs = await self.predictions.inference.list_analysis_jobs_for_user(
            project_id=project_id,
            created_by_user_id=user_id,
            media_type=media_type,
            limit=fetch_limit,
        )
        items: list[AnalysisJobListItemRead] = []
        for job in jobs:
            campaign_context = (job.request_payload or {}).get("campaign_context") or {}
            normalized_goal_template = normalize_goal_template(campaign_context.get("goal_template"))
            normalized_channel = normalize_analysis_channel(campaign_context.get("channel"))
            normalized_audience_segment = str(campaign_context.get("audience_segment") or "").strip() or None
            if goal_template is not None and normalized_goal_template != goal_template:
                continue
            if channel is not None and normalized_channel != channel:
                continue
            if audience_contains is not None:
                audience_query = audience_contains.strip().lower()
                if not audience_query or audience_query not in str(normalized_audience_segment or "").lower():
                    continue
            asset = None
            raw_asset_id = (job.runtime_params or {}).get("asset_id")
            if raw_asset_id:
                try:
                    asset = await self.uploads.get_stored_artifact(UUID(str(raw_asset_id)))
                except (TypeError, ValueError):
                    asset = None
            items.append(
                AnalysisJobListItemRead(
                    job=self._build_job_read(job),
                    asset=self._build_asset_read(asset) if asset is not None else None,
                    has_result=job.analysis_result_record is not None,
                    result_created_at=job.analysis_result_record.created_at if job.analysis_result_record is not None else None,
                )
            )
            if len(items) >= limit:
                break
        return AnalysisJobListResponse(items=items)

    async def create_upload_session(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        payload: AnalysisUploadCreateRequest,
    ) -> AnalysisUploadCreateResponse:
        with bound_log_context(project_id=str(project_id)):
            self._validate_payload(payload)
            creative = await self.creatives.create_creative(
                project_id=project_id,
                created_by_user_id=user_id,
                name=self._build_creative_name(payload.original_filename),
                asset_type=self._to_asset_type(payload.media_type),
                metadata_json={
                    "surface": "analysis",
                    "media_type": payload.media_type,
                },
            )
            asset_id = uuid4()
            storage = self._storage()
            storage_key = storage.build_analysis_object_key(
                user_id=str(user_id),
                asset_id=str(asset_id),
                original_filename=payload.original_filename,
            )
            asset = await self.uploads.create_stored_artifact(
                artifact_id=asset_id,
                project_id=project_id,
                created_by_user_id=user_id,
                creative_id=creative.id,
                creative_version_id=None,
                artifact_kind="analysis_source",
                bucket_name=storage.bucket_name,
                storage_key=storage_key,
                storage_uri=f"s3://{storage.bucket_name}/{storage_key}",
                original_filename=payload.original_filename,
                mime_type=payload.mime_type,
                file_size_bytes=payload.size_bytes,
                sha256=None,
                metadata_json={
                    "surface": "analysis",
                    "media_type": payload.media_type,
                },
                upload_status=UploadStatus.PENDING,
            )
            upload_session = await self.uploads.create_session(
                project_id=project_id,
                created_by_user_id=user_id,
                creative_id=creative.id,
                creative_version_id=None,
                upload_token=self._build_upload_token(),
                bucket_name=storage.bucket_name,
                storage_key=storage_key,
                original_filename=payload.original_filename,
                mime_type=payload.mime_type,
                expected_size_bytes=payload.size_bytes,
                metadata_json={
                    "surface": "analysis",
                    "media_type": payload.media_type,
                    "stored_artifact_id": str(asset.id),
                },
            )
            await self.session.commit()
            await self.session.refresh(asset)
            await self.session.refresh(upload_session)

            upload_url = storage.generate_presigned_put_url(
                bucket_name=upload_session.bucket_name,
                storage_key=upload_session.storage_key,
                expires_in_seconds=settings.upload_presign_expires_seconds,
                content_type=payload.mime_type,
            )
            if not upload_url:
                raise ValidationAppError("Unable to create a direct upload URL for the requested asset.")

            log_event(
                logger,
                "upload_init_created",
                upload_session_id=str(upload_session.id),
                artifact_id=str(asset.id),
                creative_id=str(creative.id),
                artifact_kind="analysis_source",
                modality=payload.media_type,
                mime_type=payload.mime_type,
                file_size_bytes=payload.size_bytes,
                status=upload_session.status.value,
                **summarize_storage_reference(storage.bucket_name, storage_key),
            )

            return AnalysisUploadCreateResponse(
                upload_session=self._build_upload_session_read(upload_session),
                asset=self._build_asset_read(asset),
                upload_url=upload_url,
                upload_headers={"Content-Type": payload.mime_type},
            )

    async def complete_upload(
        self,
        *,
        user_id: UUID,
        upload_session_id: UUID,
        upload_token: str,
    ) -> AnalysisUploadCompleteResponse:
        upload_session, asset = await self._get_owned_upload_context(
            user_id=user_id,
            upload_session_id=upload_session_id,
            upload_token=upload_token,
        )

        if upload_session.status == UploadStatus.STORED and asset.upload_status == UploadStatus.STORED:
            return AnalysisUploadCompleteResponse(
                upload_session=self._build_upload_session_read(upload_session),
                asset=self._build_asset_read(asset),
            )

        with bound_log_context(
            upload_session_id=str(upload_session.id),
            artifact_id=str(asset.id),
            creative_id=str(asset.creative_id) if asset.creative_id else None,
        ):
            try:
                await self.uploads.mark_uploading(upload_session)
                await self.uploads.mark_artifact_uploading(asset)
                log_event(
                    logger,
                    "upload_started",
                    upload_session_id=str(upload_session.id),
                    artifact_id=str(asset.id),
                    artifact_kind=asset.artifact_kind,
                    status="uploading",
                )
                storage_started_at = time.perf_counter()
                object_head = self._storage().head_object(
                    bucket_name=asset.bucket_name,
                    storage_key=asset.storage_key,
                )
                storage_finished_at = time.perf_counter()
                if object_head.file_size_bytes > settings.upload_max_size_bytes:
                    raise ValidationAppError(
                        f"Upload exceeds max size of {settings.upload_max_size_bytes} bytes.",
                    )

                log_event(
                    logger,
                    "artifact_uploaded",
                    artifact_id=str(asset.id),
                    artifact_kind=asset.artifact_kind,
                    file_size_bytes=object_head.file_size_bytes,
                    duration_ms=duration_ms(storage_started_at, storage_finished_at),
                    status="uploaded",
                    **summarize_storage_reference(asset.bucket_name, asset.storage_key),
                )

                preprocess_result = await self.preprocess.preprocess_upload(
                    filename=asset.original_filename,
                    mime_type=object_head.content_type or asset.mime_type,
                    file_size_bytes=object_head.file_size_bytes,
                )
                return await self._finalize_uploaded_asset(
                    user_id=user_id,
                    upload_session=upload_session,
                    asset=asset,
                    resolved_mime_type=object_head.content_type or asset.mime_type,
                    resolved_file_size_bytes=object_head.file_size_bytes,
                    sha256=asset.sha256,
                    preprocess_result=preprocess_result,
                    upload_etag=object_head.etag,
                    upload_source="direct_object_storage",
                )
            except Exception as exc:
                log_exception(
                    logger,
                    "upload_failed",
                    exc,
                    level="warning" if isinstance(exc, ValidationAppError) else "error",
                    upload_session_id=str(upload_session.id),
                    artifact_id=str(asset.id),
                    artifact_kind=asset.artifact_kind,
                    status="failed",
                )
                await self._mark_upload_failed(
                    user_id=user_id,
                    upload_session_id=upload_session_id,
                    asset_id=asset.id,
                    error_message=str(exc),
                )
                raise

    async def upload_via_backend(
        self,
        *,
        user_id: UUID,
        upload_session_id: UUID,
        upload_token: str,
        file: UploadFile,
    ) -> AnalysisUploadCompleteResponse:
        upload_session, asset = await self._get_owned_upload_context(
            user_id=user_id,
            upload_session_id=upload_session_id,
            upload_token=upload_token,
        )

        if upload_session.status == UploadStatus.STORED and asset.upload_status == UploadStatus.STORED:
            return AnalysisUploadCompleteResponse(
                upload_session=self._build_upload_session_read(upload_session),
                asset=self._build_asset_read(asset),
            )

        content_type = file.content_type or asset.mime_type
        self._validate_asset_mime_type(asset=asset, mime_type=content_type)

        uploaded_object: UploadedObject | None = None
        with bound_log_context(
            upload_session_id=str(upload_session.id),
            artifact_id=str(asset.id),
            creative_id=str(asset.creative_id) if asset.creative_id else None,
        ):
            try:
                await self.uploads.mark_uploading(upload_session)
                await self.uploads.mark_artifact_uploading(asset)
                await self.session.commit()
                log_event(
                    logger,
                    "upload_started",
                    upload_session_id=str(upload_session.id),
                    artifact_id=str(asset.id),
                    artifact_kind=asset.artifact_kind,
                    status="uploading",
                )

                await file.seek(0)
                upload_started_at = time.perf_counter()
                uploaded_object = await run_in_threadpool(
                    self._storage().upload_fileobj,
                    fileobj=file.file,
                    bucket_name=asset.bucket_name,
                    storage_key=asset.storage_key,
                    content_type=content_type,
                )
                upload_finished_at = time.perf_counter()
                log_event(
                    logger,
                    "artifact_uploaded",
                    artifact_id=str(asset.id),
                    artifact_kind=asset.artifact_kind,
                    file_size_bytes=uploaded_object.file_size_bytes,
                    sha256=sha256_prefix(uploaded_object.sha256),
                    duration_ms=duration_ms(upload_started_at, upload_finished_at),
                    status="uploaded",
                    **summarize_storage_reference(uploaded_object.bucket_name, uploaded_object.storage_key),
                )
                if uploaded_object.file_size_bytes > settings.upload_max_size_bytes:
                    await run_in_threadpool(
                        self._storage().delete_object,
                        bucket_name=uploaded_object.bucket_name,
                        storage_key=uploaded_object.storage_key,
                    )
                    uploaded_object = None
                    raise ValidationAppError(
                        f"Upload exceeds max size of {settings.upload_max_size_bytes} bytes.",
                    )

                preprocess_result = await self.preprocess.preprocess_upload(
                    filename=file.filename or asset.original_filename,
                    mime_type=content_type,
                    file_size_bytes=uploaded_object.file_size_bytes,
                )
                return await self._finalize_uploaded_asset(
                    user_id=user_id,
                    upload_session=upload_session,
                    asset=asset,
                    resolved_mime_type=content_type,
                    resolved_file_size_bytes=uploaded_object.file_size_bytes,
                    sha256=uploaded_object.sha256,
                    preprocess_result=preprocess_result,
                    upload_etag=None,
                    upload_source="backend_proxy",
                )
            except Exception as exc:
                if uploaded_object is not None:
                    await run_in_threadpool(
                        self._storage().delete_object,
                        bucket_name=uploaded_object.bucket_name,
                        storage_key=uploaded_object.storage_key,
                    )
                log_exception(
                    logger,
                    "upload_failed",
                    exc,
                    level="warning" if isinstance(exc, ValidationAppError) else "error",
                    upload_session_id=str(upload_session.id),
                    artifact_id=str(asset.id),
                    artifact_kind=asset.artifact_kind,
                    status="failed",
                )
                await self._mark_upload_failed(
                    user_id=user_id,
                    upload_session_id=upload_session_id,
                    asset_id=asset.id,
                    error_message=str(exc),
                )
                raise

    async def _finalize_uploaded_asset(
        self,
        *,
        user_id: UUID,
        upload_session,
        asset,
        resolved_mime_type: str | None,
        resolved_file_size_bytes: int | None,
        sha256: str | None,
        preprocess_result,
        upload_etag: str | None,
        upload_source: str,
    ) -> AnalysisUploadCompleteResponse:
        merged_metadata = {
            **(asset.metadata_json or {}),
            "upload_source": upload_source,
            "upload_etag": upload_etag,
            "preprocessing_summary": preprocess_result.preprocessing_summary,
            "extracted_metadata": preprocess_result.extracted_metadata,
            "modality": preprocess_result.modality,
        }
        await self.uploads.mark_artifact_stored(
            asset,
            creative_version_id=None,
            mime_type=resolved_mime_type or asset.mime_type,
            file_size_bytes=resolved_file_size_bytes,
            sha256=sha256,
            metadata_json=merged_metadata,
        )
        try:
            creative_version = await self.creatives.create_version_from_artifact(asset)
        except Exception as exc:
            log_exception(
                logger,
                "creative_version_promotion_failed",
                exc,
                level="warning" if isinstance(exc, (NotFoundAppError, ValidationAppError)) else "error",
                upload_session_id=str(upload_session.id),
                artifact_id=str(asset.id),
                creative_id=str(asset.creative_id) if asset.creative_id else None,
                status="failed",
            )
            raise
        await self.uploads.mark_artifact_stored(
            asset,
            creative_version_id=creative_version.id,
            mime_type=asset.mime_type,
            file_size_bytes=asset.file_size_bytes,
            sha256=asset.sha256,
            metadata_json=asset.metadata_json,
        )
        upload_session.creative_version_id = creative_version.id
        await self.uploads.mark_stored(upload_session, asset.id)
        await self.session.commit()
        await self.session.refresh(upload_session)
        await self.session.refresh(asset)
        log_event(
            logger,
            "artifact_persisted",
            upload_session_id=str(upload_session.id),
            artifact_id=str(asset.id),
            creative_id=str(asset.creative_id) if asset.creative_id else None,
            creative_version_id=str(creative_version.id),
            modality=str((asset.metadata_json or {}).get("media_type") or "unknown"),
            file_size_bytes=asset.file_size_bytes,
            sha256=sha256_prefix(asset.sha256),
            upload_source=upload_source,
            status="stored",
        )
        log_event(
            logger,
            "artifact_promoted_to_creative_version",
            artifact_id=str(asset.id),
            creative_id=str(asset.creative_id) if asset.creative_id else None,
            creative_version_id=str(creative_version.id),
            status="succeeded",
        )
        return AnalysisUploadCompleteResponse(
            upload_session=self._build_upload_session_read(upload_session),
            asset=self._build_asset_read(asset),
        )

    async def _mark_upload_failed(
        self,
        *,
        user_id: UUID,
        upload_session_id: UUID,
        asset_id: UUID,
        error_message: str,
    ) -> None:
        await self.session.rollback()
        persisted_session = await self.uploads.get_upload_session(upload_session_id)
        persisted_asset = await self.uploads.get_stored_artifact(asset_id)
        if persisted_session is not None:
            await self.uploads.mark_failed(persisted_session, error_message)
        if persisted_asset is not None:
            await self.uploads.mark_artifact_failed(persisted_asset, error_message)
        await self.session.commit()

    async def _get_owned_upload_context(
        self,
        *,
        user_id: UUID,
        upload_session_id: UUID,
        upload_token: str,
    ) -> tuple[object, object]:
        upload_session = await self.uploads.get_upload_session(upload_session_id)
        if upload_session is None or upload_session.created_by_user_id != user_id:
            raise NotFoundAppError("Upload session not found.")
        if upload_session.upload_token != upload_token:
            raise ValidationAppError("Upload session token is invalid.")

        asset_id = self._extract_asset_id(upload_session.metadata_json)
        asset = await self.uploads.get_stored_artifact(asset_id)
        if asset is None or asset.created_by_user_id != user_id:
            raise NotFoundAppError("Uploaded asset not found.")
        return upload_session, asset

    def _validate_asset_mime_type(self, *, asset, mime_type: str | None) -> None:
        media_type = str((asset.metadata_json or {}).get("media_type") or self._detect_media_type(asset.mime_type))
        if mime_type is None:
            return
        allowed_by_media_type = {
            "video": settings.analysis_allowed_video_mime_types,
            "audio": settings.analysis_allowed_audio_mime_types,
            "text": settings.analysis_allowed_text_mime_types,
        }
        if mime_type not in allowed_by_media_type.get(media_type, []):
            raise ValidationAppError(f"Unsupported {media_type} mime type: {mime_type}")

    async def create_analysis_job(
        self,
        *,
        user_id: UUID,
        asset_id: UUID,
        project_id: UUID,
        objective: str | None,
        goal_template: str | None,
        channel: str | None,
        audience_segment: str | None,
    ) -> AnalysisJobStatusResponse:
        asset = await self.uploads.get_stored_artifact(asset_id)
        if asset is None or asset.created_by_user_id != user_id or asset.project_id != project_id:
            raise NotFoundAppError("Asset not found.")
        if asset.upload_status != UploadStatus.STORED:
            raise ConflictAppError("The selected asset has not finished uploading.")
        if asset.creative_id is None or asset.creative_version_id is None:
            raise ConflictAppError("The selected asset is not ready for analysis.")

        media_type = str((asset.metadata_json or {}).get("media_type") or self._detect_media_type(asset.mime_type))
        normalized_goal_template = normalize_goal_template(goal_template)
        normalized_channel = normalize_analysis_channel(channel)
        normalized_objective = (objective or "").strip() or None
        normalized_audience_segment = (audience_segment or "").strip() or None
        job = await self.predictions.create_prediction_job(
            PredictRequest(
                project_id=project_id,
                creative_id=asset.creative_id,
                creative_version_id=asset.creative_version_id,
                created_by_user_id=user_id,
                audience_context={},
                campaign_context={
                    "objective": normalized_objective,
                    "goal_template": normalized_goal_template,
                    "channel": normalized_channel,
                    "audience_segment": normalized_audience_segment,
                    "media_type": media_type,
                    "surface": "analysis",
                },
                runtime_params={
                    "analysis_surface": "analysis_dashboard",
                    "asset_id": str(asset.id),
                    "media_type": media_type,
                    "analysis_progress": {
                        "stage": "queued",
                        "stage_label": "Upload finalized. The analysis job is queued and waiting for worker capacity.",
                        "diagnostics": {},
                        "is_partial": False,
                    },
                },
            )
        )
        await self.session.refresh(job)
        log_event(
            logger,
            "analysis_job_requested",
            job_id=str(job.id),
            project_id=str(project_id),
            asset_id=str(asset.id),
            media_type=media_type,
            goal_template=normalized_goal_template,
            channel=normalized_channel,
            audience_segment=normalized_audience_segment,
            has_objective=normalized_objective is not None,
            status=job.status.value,
        )
        return await self._build_job_status_response(job)

    async def get_analysis_job(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
    ) -> AnalysisJobStatusResponse:
        job = await self.predictions.get_job(job_id)
        self._ensure_job_ownership(job, user_id=user_id)
        return await self._build_job_status_response(job)

    async def get_analysis_result(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
    ) -> AnalysisResultRead:
        job = await self.predictions.get_job(job_id)
        self._ensure_job_ownership(job, user_id=user_id)
        result = self._build_result(job)
        if result is None:
            raise ConflictAppError("Analysis results are not ready yet.")
        return result

    async def get_asset_media(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        asset_id: UUID,
    ) -> tuple[AnalysisAssetRead, bytes, str | None]:
        asset = await self.uploads.get_stored_artifact(asset_id)
        if asset is None or asset.created_by_user_id != user_id or asset.project_id != project_id:
            raise NotFoundAppError("Asset not found.")

        body, content_type = await run_in_threadpool(
            self._storage().get_object_bytes,
            bucket_name=asset.bucket_name,
            storage_key=asset.storage_key,
        )
        return self._build_asset_read(asset), body, content_type or asset.mime_type

    def _validate_payload(self, payload: AnalysisUploadCreateRequest) -> None:
        if payload.size_bytes > settings.upload_max_size_bytes:
            raise ValidationAppError(
                f"Upload exceeds max size of {settings.upload_max_size_bytes} bytes.",
            )

        allowed_by_media_type = {
            "video": settings.analysis_allowed_video_mime_types,
            "audio": settings.analysis_allowed_audio_mime_types,
            "text": settings.analysis_allowed_text_mime_types,
        }
        allowed_mime_types = allowed_by_media_type[payload.media_type]
        if payload.mime_type not in allowed_mime_types:
            raise ValidationAppError(f"Unsupported {payload.media_type} mime type: {payload.mime_type}")
        if payload.media_type == "text" and payload.size_bytes > settings.analysis_max_text_characters * 8:
            raise ValidationAppError("Text upload exceeds the configured analysis size budget.")

    def _to_asset_type(self, media_type: str) -> AssetType:
        mapping = {
            "video": AssetType.VIDEO,
            "audio": AssetType.AUDIO,
            "text": AssetType.TEXT,
        }
        return mapping[media_type]

    def _build_creative_name(self, original_filename: str) -> str:
        stem = original_filename.rsplit(".", 1)[0].strip()
        return stem[:255] or "Analysis Upload"

    def _build_upload_token(self) -> str:
        return str(uuid4())

    def _extract_asset_id(self, metadata_json: dict[str, Any]) -> UUID:
        raw_value = metadata_json.get("stored_artifact_id")
        try:
            return UUID(str(raw_value))
        except (TypeError, ValueError) as exc:
            raise ValidationAppError("Upload session is missing its asset reference.") from exc

    def _build_asset_read(self, asset) -> AnalysisAssetRead:
        metadata_json = asset.metadata_json or {}
        return AnalysisAssetRead(
            id=asset.id,
            creative_id=asset.creative_id,
            creative_version_id=asset.creative_version_id,
            media_type=str(metadata_json.get("media_type") or self._detect_media_type(asset.mime_type)),
            original_filename=asset.original_filename,
            mime_type=asset.mime_type,
            size_bytes=asset.file_size_bytes,
            bucket=asset.bucket_name,
            object_key=asset.storage_key,
            object_uri=asset.storage_uri,
            checksum=asset.sha256,
            upload_status=self._map_upload_status(asset.upload_status),
            created_at=asset.created_at,
        )

    def _build_upload_session_read(self, upload_session) -> AnalysisUploadSessionRead:
        return AnalysisUploadSessionRead(
            id=upload_session.id,
            upload_token=upload_session.upload_token,
            upload_status=self._map_upload_status(upload_session.status),
            created_at=upload_session.created_at,
        )

    async def _build_job_status_response(self, job: InferenceJob) -> AnalysisJobStatusResponse:
        asset = await self._load_job_asset(job)
        return AnalysisJobStatusResponse(
            job=self._build_job_read(job),
            result=self._build_result(job),
            asset=self._build_asset_read(asset) if asset is not None else None,
            progress=self._build_job_progress(job),
        )

    async def _load_job_asset(self, job: InferenceJob):
        raw_asset_id = (job.runtime_params or {}).get("asset_id")
        if raw_asset_id is None:
            return None
        try:
            return await self.uploads.get_stored_artifact(UUID(str(raw_asset_id)))
        except (TypeError, ValueError):
            return None

    def _build_job_read(self, job: InferenceJob) -> AnalysisJobRead:
        campaign_context = (job.request_payload or {}).get("campaign_context") or {}
        objective = campaign_context.get("objective")
        raw_asset_id = (job.runtime_params or {}).get("asset_id")
        asset_id = UUID(str(raw_asset_id)) if raw_asset_id is not None else UUID(int=0)
        return AnalysisJobRead(
            id=job.id,
            asset_id=asset_id,
            status=self._map_job_status(job.status),
            objective=objective,
            goal_template=normalize_goal_template(campaign_context.get("goal_template")),
            channel=normalize_analysis_channel(campaign_context.get("channel")),
            audience_segment=str(campaign_context.get("audience_segment") or "").strip() or None,
            started_at=job.started_at,
            finished_at=job.completed_at,
            error_message=job.error_message,
            created_at=job.created_at,
        )

    def _build_job_progress(self, job: InferenceJob) -> AnalysisJobProgressRead | None:
        runtime_params = job.runtime_params or {}
        raw_progress = runtime_params.get("analysis_progress") if isinstance(runtime_params, dict) else None
        progress_payload = raw_progress if isinstance(raw_progress, dict) else {}
        diagnostics = self._build_job_diagnostics(job, progress_payload.get("diagnostics"))

        status = self._map_job_status(job.status)
        stage = self._normalize_optional_string(progress_payload.get("stage"))
        stage_label = self._normalize_optional_string(progress_payload.get("stage_label"))

        if stage is None:
            if status == "queued":
                stage = "queued"
                stage_label = stage_label or "The job is queued and waiting for worker capacity."
            elif status == "processing":
                stage = "processing"
                stage_label = stage_label or "The worker is processing the asset."
            elif status == "completed":
                stage = "completed"
                stage_label = stage_label or "Results are ready."
            elif status == "failed":
                stage = "failed"
                stage_label = stage_label or "The analysis stopped before results were produced."

        if stage is None and not any(value is not None for value in diagnostics.model_dump().values()):
            return None

        return AnalysisJobProgressRead(
            stage=stage or status,
            stage_label=stage_label,
            diagnostics=diagnostics,
            is_partial=bool(progress_payload.get("is_partial")),
        )

    def _build_job_diagnostics(
        self,
        job: InferenceJob,
        raw_diagnostics: Any,
    ) -> AnalysisJobDiagnosticsRead:
        diagnostics_payload = raw_diagnostics if isinstance(raw_diagnostics, dict) else {}

        queue_wait_ms = self._coerce_non_negative_int(diagnostics_payload.get("queue_wait_ms"))
        if queue_wait_ms is None:
            queue_wait_ms = self._calculate_elapsed_ms(job.created_at, job.started_at)

        processing_duration_ms = self._coerce_non_negative_int(diagnostics_payload.get("processing_duration_ms"))
        if processing_duration_ms is None:
            processing_duration_ms = self._calculate_elapsed_ms(job.started_at, job.completed_at)

        result_delivery_ms = self._coerce_non_negative_int(diagnostics_payload.get("result_delivery_ms"))
        if result_delivery_ms is None:
            result_delivery_ms = self._calculate_elapsed_ms(job.created_at, job.completed_at)

        return AnalysisJobDiagnosticsRead(
            queue_wait_ms=queue_wait_ms,
            processing_duration_ms=processing_duration_ms,
            time_to_first_result_ms=self._coerce_non_negative_int(diagnostics_payload.get("time_to_first_result_ms")),
            result_delivery_ms=result_delivery_ms,
            postprocess_duration_ms=self._coerce_non_negative_int(diagnostics_payload.get("postprocess_duration_ms")),
        )

    def _build_result(self, job: InferenceJob) -> AnalysisResultRead | None:
        if job.status != JobStatus.SUCCEEDED:
            return None
        record = job.__dict__.get("analysis_result_record")
        if record is None:
            return None

        return AnalysisResultRead(
            job_id=job.id,
            summary_json=record.summary_json or {},
            metrics_json=record.metrics_json or [],
            timeline_json=record.timeline_json or [],
            segments_json=record.segments_json or [],
            visualizations_json=record.visualizations_json
            or {
                "visualization_mode": "frame_grid_fallback",
                "heatmap_frames": [],
                "high_attention_intervals": [],
                "low_attention_intervals": [],
            },
            recommendations_json=record.recommendations_json or [],
            created_at=record.created_at,
        )

    def _coerce_non_negative_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            return None
        return max(coerced, 0)

    def _calculate_elapsed_ms(self, started_at: datetime | None, finished_at: datetime | None) -> int | None:
        if started_at is None or finished_at is None:
            return None
        return max(int((finished_at - started_at).total_seconds() * 1000), 0)

    def _normalize_optional_string(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        return normalized or None

    def _ensure_job_ownership(self, job: InferenceJob, *, user_id: UUID) -> None:
        if job.created_by_user_id != user_id:
            raise NotFoundAppError("Analysis job not found.")

    def _map_upload_status(self, status: UploadStatus) -> str:
        mapping = {
            UploadStatus.PENDING: "pending",
            UploadStatus.UPLOADING: "uploading",
            UploadStatus.STORED: "uploaded",
            UploadStatus.FAILED: "failed",
        }
        return mapping[status]

    def _map_job_status(self, status: JobStatus) -> str:
        mapping = {
            JobStatus.QUEUED: "queued",
            JobStatus.PREPROCESSING: "processing",
            JobStatus.RUNNING: "processing",
            JobStatus.SUCCEEDED: "completed",
            JobStatus.FAILED: "failed",
            JobStatus.CANCELED: "failed",
        }
        return mapping[status]

    def _detect_media_type(self, mime_type: str | None) -> str:
        if not mime_type:
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
        if mime_type.startswith("text/"):
            return "text"
        return "video"
