from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import StoredArtifact, UploadSession, UploadStatus


class UploadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        *,
        project_id: UUID,
        creative_id: UUID | None,
        creative_version_id: UUID | None,
        upload_token: str,
        bucket_name: str,
        storage_key: str,
        original_filename: str | None,
        mime_type: str | None,
        expected_size_bytes: int | None,
        metadata_json: dict,
    ) -> UploadSession:
        upload_session = UploadSession(
            project_id=project_id,
            creative_id=creative_id,
            creative_version_id=creative_version_id,
            upload_token=upload_token,
            status=UploadStatus.PENDING,
            bucket_name=bucket_name,
            storage_key=storage_key,
            original_filename=original_filename,
            mime_type=mime_type,
            expected_size_bytes=expected_size_bytes,
            metadata_json=metadata_json,
        )
        self.session.add(upload_session)
        await self.session.flush()
        await self.session.refresh(upload_session)
        return upload_session

    async def get_upload_session_by_token(self, upload_token: str) -> UploadSession | None:
        result = await self.session.execute(select(UploadSession).where(UploadSession.upload_token == upload_token))
        return result.scalar_one_or_none()

    async def mark_uploading(self, upload_session: UploadSession) -> UploadSession:
        upload_session.status = UploadStatus.UPLOADING
        upload_session.error_message = None
        await self.session.flush()
        return upload_session

    async def mark_failed(self, upload_session: UploadSession, error_message: str) -> UploadSession:
        upload_session.status = UploadStatus.FAILED
        upload_session.error_message = error_message
        await self.session.flush()
        return upload_session

    async def create_stored_artifact(
        self,
        *,
        project_id: UUID,
        creative_id: UUID | None,
        creative_version_id: UUID | None,
        artifact_kind: str,
        bucket_name: str,
        storage_key: str,
        storage_uri: str,
        original_filename: str | None,
        mime_type: str | None,
        file_size_bytes: int | None,
        sha256: str | None,
        metadata_json: dict,
    ) -> StoredArtifact:
        artifact = StoredArtifact(
            project_id=project_id,
            creative_id=creative_id,
            creative_version_id=creative_version_id,
            artifact_kind=artifact_kind,
            bucket_name=bucket_name,
            storage_key=storage_key,
            storage_uri=storage_uri,
            original_filename=original_filename,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            sha256=sha256,
            metadata_json=metadata_json,
        )
        self.session.add(artifact)
        await self.session.flush()
        await self.session.refresh(artifact)
        return artifact

    async def mark_stored(self, upload_session: UploadSession, uploaded_artifact_id: UUID) -> UploadSession:
        upload_session.status = UploadStatus.STORED
        upload_session.uploaded_artifact_id = uploaded_artifact_id
        upload_session.error_message = None
        await self.session.flush()
        return upload_session
