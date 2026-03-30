from __future__ import annotations

from uuid import UUID

from backend.application.services.creative_versions import CreativeVersionApplicationService
from backend.db.session import session_scope


async def promote_artifact_to_creative_version(*, artifact_id: UUID) -> UUID:
    async with session_scope() as db:
        version = await CreativeVersionApplicationService(db).promote_artifact(artifact_id)
        return version.id
