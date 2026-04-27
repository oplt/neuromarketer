from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from uuid import UUID

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import NotFoundAppError, ValidationAppError
from backend.core.log_context import bound_log_context
from backend.core.logging import (
    duration_ms,
    get_logger,
    log_event,
    log_exception,
    sha256_prefix,
    summarize_storage_reference,
)
from backend.db.models import UploadSession, UploadStatus
from backend.db.repositories import CreativeRepository, UploadRepository
from backend.schemas.uploads import UploadInitRequest
from backend.services.file_validation import validate_file_content
from backend.services.preprocess import PreprocessService
from backend.services.storage import S3StorageService, UploadedObject

logger = get_logger(__name__)


@dataclass(slots=True)
class DirectUploadResult:
    upload_session: UploadSession
    artifact: object


class UploadApplicationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: S3StorageService | None = None,
        preprocess: PreprocessService | None = None,
    ) -> None:
        self.session = session
        self.creatives = CreativeRepository(session)
        self.uploads = UploadRepository(session)
        self.storage = storage if storage is not None else S3StorageService()
        self.preprocess = preprocess if preprocess is not None else PreprocessService()

    async def create_upload_session(
        self,
        payload: UploadInitRequest,
        *,
        created_by_user_id: UUID | None = None,
    ) -> UploadSession:
        with bound_log_context(
            project_id=str(payload.project_id),
            creative_id=str(payload.creative_id) if payload.creative_id else None,
            creative_version_id=str(payload.creative_version_id)
            if payload.creative_version_id
            else None,
        ):
            await self._validate_relationships(
                project_id=payload.project_id,
                creative_id=payload.creative_id,
                creative_version_id=payload.creative_version_id,
            )
            if not self.storage.is_allowed_mime_type(payload.mime_type):
                raise ValidationAppError(f"Unsupported mime type: {payload.mime_type or 'unknown'}")
            if (
                payload.expected_size_bytes
                and payload.expected_size_bytes > settings.upload_max_size_bytes
            ):
                raise ValidationAppError(
                    f"Upload exceeds max size of {settings.upload_max_size_bytes} bytes.",
                )

            preprocess_result = await self.preprocess.preprocess_upload(
                filename=payload.original_filename,
                mime_type=payload.mime_type,
                file_size_bytes=payload.expected_size_bytes,
            )
            storage_key = self.storage.build_storage_key(
                project_id=str(payload.project_id),
                artifact_kind=payload.artifact_kind,
                original_filename=payload.original_filename,
            )
            upload_session = await self.uploads.create_session(
                project_id=payload.project_id,
                created_by_user_id=created_by_user_id,
                creative_id=payload.creative_id,
                creative_version_id=payload.creative_version_id,
                upload_token=secrets.token_urlsafe(24),
                bucket_name=self.storage.bucket_name,
                storage_key=storage_key,
                original_filename=payload.original_filename,
                mime_type=payload.mime_type,
                expected_size_bytes=payload.expected_size_bytes,
                metadata_json={
                    **payload.metadata_json,
                    "preprocessing_summary": preprocess_result.preprocessing_summary,
                    "extracted_metadata": preprocess_result.extracted_metadata,
                    "modality": preprocess_result.modality,
                },
            )
            log_event(
                logger,
                "upload_init_created",
                upload_session_id=str(upload_session.id),
                modality=preprocess_result.modality,
                artifact_kind=payload.artifact_kind,
                mime_type=payload.mime_type,
                file_size_bytes=payload.expected_size_bytes,
                status=upload_session.status.value,
            )
            return upload_session

    async def handle_direct_upload(
        self,
        *,
        project_id: UUID,
        created_by_user_id: UUID,
        creative_id: UUID | None,
        creative_version_id: UUID | None,
        artifact_kind: str,
        file: UploadFile,
        max_size_bytes: int | None = None,
    ) -> DirectUploadResult:
        with bound_log_context(
            project_id=str(project_id),
            creative_id=str(creative_id) if creative_id else None,
            creative_version_id=str(creative_version_id) if creative_version_id else None,
        ):
            await self._validate_relationships(
                project_id=project_id,
                creative_id=creative_id,
                creative_version_id=creative_version_id,
            )

            if not self.storage.is_allowed_mime_type(file.content_type):
                raise ValidationAppError(f"Unsupported mime type: {file.content_type or 'unknown'}")

            await file.seek(0)
            is_valid_content, detected_mime = validate_file_content(
                file.file, declared_mime_type=file.content_type
            )
            await file.seek(0)
            if not is_valid_content:
                raise ValidationAppError(
                    f"File content does not match declared type. Detected: {detected_mime or 'unknown'}"
                )

            upload_session = await self.uploads.create_session(
                project_id=project_id,
                created_by_user_id=created_by_user_id,
                creative_id=creative_id,
                creative_version_id=creative_version_id,
                upload_token=secrets.token_urlsafe(24),
                bucket_name=self.storage.bucket_name,
                storage_key=self.storage.build_storage_key(
                    project_id=str(project_id),
                    artifact_kind=artifact_kind,
                    original_filename=file.filename or "upload.bin",
                ),
                original_filename=file.filename,
                mime_type=file.content_type,
                expected_size_bytes=None,
                metadata_json={},
            )
            await self.session.commit()
            await self.session.refresh(upload_session)

            uploaded_object: UploadedObject | None = None
            artifact = None
            with bound_log_context(upload_session_id=str(upload_session.id)):
                try:
                    await self.uploads.mark_uploading(upload_session)
                    await self.session.commit()
                    log_event(
                        logger,
                        "upload_started",
                        upload_session_id=str(upload_session.id),
                        artifact_kind=artifact_kind,
                        mime_type=file.content_type,
                        status="uploading",
                    )

                    await file.seek(0)
                    upload_started_at = time.perf_counter()
                    uploaded_object = await run_in_threadpool(
                        self.storage.upload_fileobj,
                        fileobj=file.file,
                        bucket_name=self.storage.bucket_name,
                        storage_key=upload_session.storage_key,
                        content_type=file.content_type,
                    )
                    upload_finished_at = time.perf_counter()
                    log_event(
                        logger,
                        "artifact_uploaded",
                        artifact_kind=artifact_kind,
                        file_size_bytes=uploaded_object.file_size_bytes,
                        sha256=sha256_prefix(uploaded_object.sha256),
                        duration_ms=duration_ms(upload_started_at, upload_finished_at),
                        status="uploaded",
                        **summarize_storage_reference(
                            uploaded_object.bucket_name, uploaded_object.storage_key
                        ),
                    )

                    configured_max_size = (
                        min(settings.upload_max_size_bytes, max_size_bytes)
                        if max_size_bytes is not None
                        else settings.upload_max_size_bytes
                    )
                    if uploaded_object.file_size_bytes > configured_max_size:
                        await run_in_threadpool(
                            self.storage.delete_object,
                            bucket_name=uploaded_object.bucket_name,
                            storage_key=uploaded_object.storage_key,
                        )
                        uploaded_object = None
                        raise ValidationAppError(
                            f"Upload exceeds max size of {configured_max_size} bytes.",
                        )
                    preprocess_result = await self.preprocess.preprocess_upload(
                        filename=file.filename,
                        mime_type=file.content_type,
                        file_size_bytes=uploaded_object.file_size_bytes,
                    )
                    artifact = await self.uploads.create_stored_artifact(
                        project_id=project_id,
                        created_by_user_id=created_by_user_id,
                        creative_id=creative_id,
                        creative_version_id=creative_version_id,
                        artifact_kind=artifact_kind,
                        bucket_name=uploaded_object.bucket_name,
                        storage_key=uploaded_object.storage_key,
                        storage_uri=uploaded_object.storage_uri,
                        original_filename=file.filename,
                        mime_type=file.content_type,
                        file_size_bytes=uploaded_object.file_size_bytes,
                        sha256=uploaded_object.sha256,
                        metadata_json={
                            "preprocessing_summary": preprocess_result.preprocessing_summary,
                            "extracted_metadata": preprocess_result.extracted_metadata,
                            "modality": preprocess_result.modality,
                        },
                        upload_status=UploadStatus.STORED,
                    )
                    await self.uploads.mark_stored(upload_session, artifact.id)
                    await self.session.commit()
                    await self.session.refresh(upload_session)
                    log_event(
                        logger,
                        "artifact_persisted",
                        artifact_id=str(artifact.id),
                        artifact_kind=artifact_kind,
                        modality=preprocess_result.modality,
                        file_size_bytes=artifact.file_size_bytes,
                        sha256=sha256_prefix(artifact.sha256),
                        status="stored",
                    )
                    return DirectUploadResult(upload_session=upload_session, artifact=artifact)
                except Exception as exc:
                    await self.session.rollback()
                    persisted_session = await self.session.get(UploadSession, upload_session.id)
                    if persisted_session is not None:
                        await self.uploads.mark_failed(persisted_session, str(exc))
                        await self.session.commit()

                    if uploaded_object is not None:
                        await run_in_threadpool(
                            self.storage.delete_object,
                            bucket_name=uploaded_object.bucket_name,
                            storage_key=uploaded_object.storage_key,
                        )
                    log_exception(
                        logger,
                        "upload_failed",
                        exc,
                        level="warning" if isinstance(exc, ValidationAppError) else "error",
                        artifact_id=str(artifact.id) if artifact is not None else None,
                        artifact_kind=artifact_kind,
                        status="failed",
                    )
                    raise

    async def _validate_relationships(
        self,
        *,
        project_id: UUID,
        creative_id: UUID | None,
        creative_version_id: UUID | None,
    ) -> None:
        project = await self.creatives.get_project(project_id)
        if project is None:
            raise NotFoundAppError("Project not found.")

        creative = None
        if creative_id is not None:
            creative = await self.creatives.get_creative(creative_id)
            if creative is None:
                raise NotFoundAppError("Creative not found.")
            if creative.project_id != project_id:
                raise ValidationAppError("Creative does not belong to project.")

        if creative_version_id is not None:
            version = await self.creatives.get_creative_version(creative_version_id)
            if version is None:
                raise NotFoundAppError("Creative version not found.")
            version_creative = await self.creatives.get_creative(version.creative_id)
            if version_creative is None or version_creative.project_id != project_id:
                raise ValidationAppError("Creative version does not belong to project.")
            if creative is not None and version.creative_id != creative.id:
                raise ValidationAppError("Creative version does not belong to creative.")
