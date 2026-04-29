from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.db.repositories.uploads import UploadRepository


def _make_session_capture():
    session = AsyncMock()
    captured = []

    async def _record(stmt, *_args, **_kwargs):
        captured.append(stmt)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result

    session.execute.side_effect = _record
    return session, captured


class TestUploadRepositoryMediaTypeFiltering(unittest.IsolatedAsyncioTestCase):
    async def test_list_analysis_artifacts_prefers_media_type_column(self) -> None:
        session, captured = _make_session_capture()
        repo = UploadRepository(session)

        await repo.list_analysis_artifacts(
            project_id=uuid4(),
            created_by_user_id=uuid4(),
            media_type="video",
            limit=25,
        )

        self.assertEqual(len(captured), 1)
        compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("stored_artifacts.media_type = 'video'", compiled)

    async def test_create_stored_artifact_persists_media_type(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        repo = UploadRepository(session)

        artifact = await repo.create_stored_artifact(
            project_id=uuid4(),
            created_by_user_id=uuid4(),
            creative_id=None,
            creative_version_id=None,
            artifact_kind="analysis_source",
            bucket_name="bucket",
            storage_key="k",
            storage_uri="s3://bucket/k",
            original_filename="x.mp4",
            mime_type="video/mp4",
            media_type="video",
            file_size_bytes=1,
            sha256=None,
            metadata_json={},
        )

        self.assertEqual(artifact.media_type, "video")


if __name__ == "__main__":
    unittest.main()
