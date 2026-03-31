from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import StoredArtifact, UploadSession, UploadStatus


class UploadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        *,
        project_id: UUID,
        created_by_user_id: UUID | None,
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
            created_by_user_id=created_by_user_id,
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

    async def get_upload_session(self, upload_session_id: UUID) -> UploadSession | None:
        result = await self.session.execute(select(UploadSession).where(UploadSession.id == upload_session_id))
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
        artifact_id: UUID | None = None,
        project_id: UUID,
        created_by_user_id: UUID | None,
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
        upload_status: UploadStatus = UploadStatus.PENDING,
    ) -> StoredArtifact:
        artifact = StoredArtifact(
            id=artifact_id,
            project_id=project_id,
            created_by_user_id=created_by_user_id,
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
            upload_status=upload_status,
            metadata_json=metadata_json,
        )
        self.session.add(artifact)
        await self.session.flush()
        await self.session.refresh(artifact)
        return artifact

    async def get_stored_artifact(self, artifact_id: UUID) -> StoredArtifact | None:
        result = await self.session.execute(select(StoredArtifact).where(StoredArtifact.id == artifact_id))
        return result.scalar_one_or_none()

    async def list_analysis_artifacts(
        self,
        *,
        project_id: UUID,
        created_by_user_id: UUID,
        limit: int,
    ) -> list[StoredArtifact]:
        result = await self.session.execute(
            select(StoredArtifact)
            .where(
                StoredArtifact.project_id == project_id,
                StoredArtifact.created_by_user_id == created_by_user_id,
                StoredArtifact.artifact_kind == "analysis_source",
                StoredArtifact.upload_status == UploadStatus.STORED,
            )
            .order_by(desc(StoredArtifact.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_stored(self, upload_session: UploadSession, uploaded_artifact_id: UUID) -> UploadSession:
        upload_session.status = UploadStatus.STORED
        upload_session.uploaded_artifact_id = uploaded_artifact_id
        upload_session.error_message = None
        await self.session.flush()
        return upload_session

    async def mark_artifact_uploading(self, artifact: StoredArtifact) -> StoredArtifact:
        artifact.upload_status = UploadStatus.UPLOADING
        await self.session.flush()
        return artifact

    async def mark_artifact_failed(self, artifact: StoredArtifact, error_message: str | None = None) -> StoredArtifact:
        artifact.upload_status = UploadStatus.FAILED
        metadata_json = dict(artifact.metadata_json or {})
        if error_message:
            metadata_json["upload_error"] = error_message
        artifact.metadata_json = metadata_json
        await self.session.flush()
        return artifact

    async def mark_artifact_stored(
        self,
        artifact: StoredArtifact,
        *,
        creative_version_id: UUID | None,
        mime_type: str | None,
        file_size_bytes: int | None,
        sha256: str | None,
        metadata_json: dict,
    ) -> StoredArtifact:
        artifact.creative_version_id = creative_version_id
        artifact.mime_type = mime_type
        artifact.file_size_bytes = file_size_bytes
        artifact.sha256 = sha256
        artifact.upload_status = UploadStatus.STORED
        artifact.metadata_json = metadata_json
        await self.session.flush()
        return artifact
