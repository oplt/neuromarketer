from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.db.models import CreativeStatus
from backend.db.repositories.creatives import CreativeRepository
from sqlalchemy.exc import IntegrityError


class _DummyNested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _integrity_error() -> IntegrityError:
    return IntegrityError("insert", {}, Exception("duplicate key value"))


class TestCreativeVersionRetry(unittest.IsolatedAsyncioTestCase):
    async def test_create_version_retries_after_integrity_error(self) -> None:
        session = AsyncMock()
        session.begin_nested = MagicMock(return_value=_DummyNested())
        session.add = MagicMock()
        # First flush conflicts on uq_creative_version_number, second succeeds.
        session.flush = AsyncMock(side_effect=[_integrity_error(), None])
        session.refresh = AsyncMock()
        session.execute = AsyncMock()

        repo = CreativeRepository(session)
        repo.next_version_number = AsyncMock(side_effect=[1, 2])
        repo.get_creative = AsyncMock(return_value=SimpleNamespace(status=CreativeStatus.DRAFT))

        artifact = SimpleNamespace(
            creative_id=uuid4(),
            storage_uri="s3://bucket/object",
            mime_type="video/mp4",
            file_size_bytes=123,
            sha256="deadbeef",
            metadata_json={},
        )

        version = await repo.create_version_from_artifact(artifact)

        self.assertEqual(version.version_number, 2)
        self.assertEqual(repo.next_version_number.await_count, 2)
        self.assertEqual(session.flush.await_count, 2)

    async def test_create_version_with_explicit_number_does_not_retry(self) -> None:
        session = AsyncMock()
        session.begin_nested = MagicMock(return_value=_DummyNested())
        session.add = MagicMock()
        session.flush = AsyncMock(side_effect=_integrity_error())
        session.refresh = AsyncMock()
        session.execute = AsyncMock()

        repo = CreativeRepository(session)
        repo.next_version_number = AsyncMock()
        repo.get_creative = AsyncMock(return_value=None)

        artifact = SimpleNamespace(
            creative_id=uuid4(),
            storage_uri="s3://bucket/object",
            mime_type="video/mp4",
            file_size_bytes=123,
            sha256="deadbeef",
            metadata_json={},
        )

        with self.assertRaises(IntegrityError):
            await repo.create_version_from_artifact(artifact, version_number=7)

        repo.next_version_number.assert_not_awaited()
        self.assertEqual(session.flush.await_count, 1)


if __name__ == "__main__":
    unittest.main()
