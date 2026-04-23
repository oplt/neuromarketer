from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import (
    AssetType,
    Creative,
    CreativeStatus,
    CreativeVersion,
    Project,
    StoredArtifact,
)


class CreativeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_project(self, project_id: UUID) -> Project | None:
        result = await self.session.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def get_creative(self, creative_id: UUID) -> Creative | None:
        result = await self.session.execute(select(Creative).where(Creative.id == creative_id))
        return result.scalar_one_or_none()

    async def get_creative_version(self, creative_version_id: UUID) -> CreativeVersion | None:
        result = await self.session.execute(
            select(CreativeVersion).where(CreativeVersion.id == creative_version_id)
        )
        return result.scalar_one_or_none()

    async def get_stored_artifact(self, artifact_id: UUID) -> StoredArtifact | None:
        result = await self.session.execute(
            select(StoredArtifact).where(StoredArtifact.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def next_version_number(self, creative_id: UUID) -> int:
        result = await self.session.execute(
            select(func.max(CreativeVersion.version_number)).where(
                CreativeVersion.creative_id == creative_id
            )
        )
        current_max = result.scalar_one()
        return int(current_max or 0) + 1

    async def create_creative(
        self,
        *,
        project_id: UUID,
        created_by_user_id: UUID | None,
        name: str,
        asset_type: AssetType,
        tags: list[str] | None = None,
        metadata_json: dict | None = None,
    ) -> Creative:
        creative = Creative(
            project_id=project_id,
            created_by_user_id=created_by_user_id,
            name=name,
            asset_type=asset_type,
            status=CreativeStatus.DRAFT,
            tags=tags or [],
            metadata_json=metadata_json or {},
        )
        self.session.add(creative)
        await self.session.flush()
        await self.session.refresh(creative)
        return creative

    async def create_version_from_artifact(
        self,
        artifact: StoredArtifact,
        *,
        version_number: int | None = None,
        raw_text: str | None = None,
    ) -> CreativeVersion:
        if artifact.creative_id is None:
            raise ValueError("Artifact is not attached to a creative.")

        resolved_version_number = version_number or await self.next_version_number(
            artifact.creative_id
        )

        await self.session.execute(
            update(CreativeVersion)
            .where(CreativeVersion.creative_id == artifact.creative_id)
            .values(is_current=False)
        )

        version = CreativeVersion(
            creative_id=artifact.creative_id,
            version_number=resolved_version_number,
            is_current=True,
            source_uri=artifact.storage_uri,
            mime_type=artifact.mime_type,
            file_size_bytes=artifact.file_size_bytes,
            sha256=artifact.sha256,
            raw_text=raw_text,
            extracted_metadata=artifact.metadata_json.get("extracted_metadata", {}),
            preprocessing_summary=artifact.metadata_json.get("preprocessing_summary", {}),
            duration_ms=artifact.metadata_json.get("extracted_metadata", {}).get("duration_ms"),
            width_px=artifact.metadata_json.get("extracted_metadata", {}).get("width_px"),
            height_px=artifact.metadata_json.get("extracted_metadata", {}).get("height_px"),
            frame_rate=artifact.metadata_json.get("extracted_metadata", {}).get("frame_rate"),
        )
        self.session.add(version)

        creative = await self.get_creative(artifact.creative_id)
        if creative is not None:
            creative.status = CreativeStatus.READY

        await self.session.flush()
        await self.session.refresh(version)
        return version
