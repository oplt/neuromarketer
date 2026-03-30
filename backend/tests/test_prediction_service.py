from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from backend.application.services.predictions import PredictionApplicationService
from backend.core.exceptions import UnsupportedModalityAppError
from backend.schemas.schemas import PredictRequest


class PredictionApplicationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_prediction_job_rejects_unsupported_html_modality(self) -> None:
        project_id = uuid4()
        creative_id = uuid4()
        creative_version_id = uuid4()
        session = AsyncMock()

        service = PredictionApplicationService(session)
        service.creatives = SimpleNamespace(
            get_creative=AsyncMock(
                return_value=SimpleNamespace(
                    id=creative_id,
                    project_id=project_id,
                )
            ),
            get_creative_version=AsyncMock(
                return_value=SimpleNamespace(
                    id=creative_version_id,
                    creative_id=creative_id,
                    preprocessing_summary={"modality": "html"},
                    raw_text="<html><body>Hello</body></html>",
                    mime_type="text/html",
                    source_uri=None,
                )
            ),
        )
        service.inference = SimpleNamespace(create_job=AsyncMock())

        with self.assertRaises(UnsupportedModalityAppError):
            await service.create_prediction_job(
                PredictRequest(
                    project_id=project_id,
                    creative_id=creative_id,
                    creative_version_id=creative_version_id,
                    created_by_user_id=None,
                )
            )

        service.inference.create_job.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
