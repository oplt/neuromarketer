from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.predictions import PredictionApplicationService
from backend.core.config import settings
from backend.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.core.logging import get_logger
from backend.db.models import AssetType, InferenceJob, JobStatus, UploadStatus
from backend.db.repositories import CreativeRepository, UploadRepository
from backend.schemas.analysis import (
    AnalysisAssetRead,
    AnalysisConfigResponse,
    AnalysisJobRead,
    AnalysisJobStatusResponse,
    AnalysisResultRead,
    AnalysisUploadCreateRequest,
    AnalysisUploadCreateResponse,
    AnalysisUploadCompleteResponse,
    AnalysisUploadSessionRead,
)
from backend.schemas.schemas import PredictRequest
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
        self.storage = ObjectStorageService()

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

    async def create_upload_session(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        payload: AnalysisUploadCreateRequest,
    ) -> AnalysisUploadCreateResponse:
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
        storage_key = self.storage.build_analysis_object_key(
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
            bucket_name=self.storage.bucket_name,
            storage_key=storage_key,
            storage_uri=f"s3://{self.storage.bucket_name}/{storage_key}",
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
            bucket_name=self.storage.bucket_name,
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

        upload_url = self.storage.generate_presigned_put_url(
            bucket_name=upload_session.bucket_name,
            storage_key=upload_session.storage_key,
            expires_in_seconds=settings.upload_presign_expires_seconds,
            content_type=payload.mime_type,
        )
        if not upload_url:
            raise ValidationAppError("Unable to create a direct upload URL for the requested asset.")

        logger.info(
            "Analysis upload session created.",
            extra={
                "event": "analysis_upload_session_created",
                "extra_fields": {
                    "user_id": str(user_id),
                    "project_id": str(project_id),
                    "asset_id": str(asset.id),
                    "media_type": payload.media_type,
                    "storage_key": storage_key,
                },
            },
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
        upload_session = await self.uploads.get_upload_session(upload_session_id)
        if upload_session is None or upload_session.created_by_user_id != user_id:
            raise NotFoundAppError("Upload session not found.")
        if upload_session.upload_token != upload_token:
            raise ValidationAppError("Upload session token is invalid.")

        asset_id = self._extract_asset_id(upload_session.metadata_json)
        asset = await self.uploads.get_stored_artifact(asset_id)
        if asset is None or asset.created_by_user_id != user_id:
            raise NotFoundAppError("Uploaded asset not found.")

        if upload_session.status == UploadStatus.STORED and asset.upload_status == UploadStatus.STORED:
            return AnalysisUploadCompleteResponse(
                upload_session=self._build_upload_session_read(upload_session),
                asset=self._build_asset_read(asset),
            )

        try:
            await self.uploads.mark_uploading(upload_session)
            await self.uploads.mark_artifact_uploading(asset)
            object_head = self.storage.head_object(
                bucket_name=asset.bucket_name,
                storage_key=asset.storage_key,
            )
            if object_head.file_size_bytes > settings.upload_max_size_bytes:
                raise ValidationAppError(
                    f"Upload exceeds max size of {settings.upload_max_size_bytes} bytes.",
                )

            preprocess_result = await self.preprocess.preprocess_upload(
                filename=asset.original_filename,
                mime_type=object_head.content_type or asset.mime_type,
                file_size_bytes=object_head.file_size_bytes,
            )
            merged_metadata = {
                **(asset.metadata_json or {}),
                "upload_etag": object_head.etag,
                "preprocessing_summary": preprocess_result.preprocessing_summary,
                "extracted_metadata": preprocess_result.extracted_metadata,
                "modality": preprocess_result.modality,
            }
            await self.uploads.mark_artifact_stored(
                asset,
                creative_version_id=None,
                mime_type=object_head.content_type or asset.mime_type,
                file_size_bytes=object_head.file_size_bytes,
                sha256=asset.sha256,
                metadata_json=merged_metadata,
            )
            creative_version = await self.creatives.create_version_from_artifact(asset)
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
            logger.info(
                "Analysis upload completed and confirmed.",
                extra={
                    "event": "analysis_upload_completed",
                    "extra_fields": {
                        "user_id": str(user_id),
                        "asset_id": str(asset.id),
                        "creative_version_id": str(creative_version.id),
                        "media_type": str((asset.metadata_json or {}).get("media_type") or "unknown"),
                        "size_bytes": asset.file_size_bytes,
                    },
                },
            )
            return AnalysisUploadCompleteResponse(
                upload_session=self._build_upload_session_read(upload_session),
                asset=self._build_asset_read(asset),
            )
        except Exception as exc:
            await self.session.rollback()
            persisted_session = await self.uploads.get_upload_session(upload_session_id)
            persisted_asset = await self.uploads.get_stored_artifact(asset_id)
            if persisted_session is not None:
                await self.uploads.mark_failed(persisted_session, str(exc))
            if persisted_asset is not None:
                await self.uploads.mark_artifact_failed(persisted_asset, str(exc))
            await self.session.commit()
            logger.exception(
                "Analysis upload completion failed.",
                extra={
                    "event": "analysis_upload_failed",
                    "extra_fields": {
                        "user_id": str(user_id),
                        "upload_session_id": str(upload_session_id),
                        "asset_id": str(asset_id),
                        "error": str(exc),
                    },
                },
            )
            raise

    async def create_analysis_job(
        self,
        *,
        user_id: UUID,
        asset_id: UUID,
        project_id: UUID,
        objective: str | None,
    ) -> AnalysisJobStatusResponse:
        asset = await self.uploads.get_stored_artifact(asset_id)
        if asset is None or asset.created_by_user_id != user_id or asset.project_id != project_id:
            raise NotFoundAppError("Asset not found.")
        if asset.upload_status != UploadStatus.STORED:
            raise ConflictAppError("The selected asset has not finished uploading.")
        if asset.creative_id is None or asset.creative_version_id is None:
            raise ConflictAppError("The selected asset is not ready for analysis.")

        media_type = str((asset.metadata_json or {}).get("media_type") or self._detect_media_type(asset.mime_type))
        job = await self.predictions.create_prediction_job(
            PredictRequest(
                project_id=project_id,
                creative_id=asset.creative_id,
                creative_version_id=asset.creative_version_id,
                created_by_user_id=user_id,
                audience_context={},
                campaign_context={
                    "objective": (objective or "").strip() or None,
                    "media_type": media_type,
                    "surface": "analysis",
                },
                runtime_params={
                    "analysis_surface": "analysis_dashboard",
                    "asset_id": str(asset.id),
                    "media_type": media_type,
                },
            )
        )
        await self.session.refresh(job)
        logger.info(
            "Analysis job created.",
            extra={
                "event": "analysis_job_created",
                "extra_fields": {
                    "user_id": str(user_id),
                    "project_id": str(project_id),
                    "asset_id": str(asset.id),
                    "job_id": str(job.id),
                    "media_type": media_type,
                },
            },
        )
        return AnalysisJobStatusResponse(job=self._build_job_read(job), result=self._build_result(job))

    async def get_analysis_job(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
    ) -> AnalysisJobStatusResponse:
        job = await self.predictions.get_job(job_id)
        self._ensure_job_ownership(job, user_id=user_id)
        return AnalysisJobStatusResponse(job=self._build_job_read(job), result=self._build_result(job))

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

    def _build_job_read(self, job: InferenceJob) -> AnalysisJobRead:
        objective = ((job.request_payload or {}).get("campaign_context") or {}).get("objective")
        asset_id = UUID(str((job.runtime_params or {}).get("asset_id")))
        return AnalysisJobRead(
            id=job.id,
            asset_id=asset_id,
            status=self._map_job_status(job.status),
            objective=objective,
            started_at=job.started_at,
            finished_at=job.completed_at,
            error_message=job.error_message,
            created_at=job.created_at,
        )

    def _build_result(self, job: InferenceJob) -> AnalysisResultRead | None:
        record = job.analysis_result_record
        if record is None or job.status != JobStatus.SUCCEEDED:
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
