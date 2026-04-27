from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.application.services.workspace_settings import ParsedEnvEntry, WorkspaceSettingsService
from backend.schemas.analysis import (
    AnalysisAssetRead,
    AnalysisJobProgressRead,
    AnalysisJobRead,
    AnalysisJobStatusLiteResponse,
    AnalysisResultSummaryRead,
)
from backend.schemas.evaluators import EvaluationDispatchRequest, EvaluationMode
from backend.schemas.llm_scoring import ScoringSuggestion
from backend.schemas.schemas import SignUpRequest
from backend.schemas.uploads import UploadSessionRead


def test_request_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SignUpRequest(
            full_name="User",
            email="user@example.com",
            password="password123",
            unexpected="x",
        )


def test_settings_secret_values_are_masked(monkeypatch) -> None:
    service = WorkspaceSettingsService(SimpleNamespace())

    async def fake_load_settings(*, organization_id):
        return []

    def fake_parse_env_entries(path):
        return [ParsedEnvEntry(key="LLM_API_KEY", value="supersecret")]

    monkeypatch.setattr(service, "_load_persisted_settings", fake_load_settings)
    monkeypatch.setattr(service, "_parse_env_entries", fake_parse_env_entries)

    response = asyncio.run(service.list_settings(organization_id=uuid4()))
    field = next(item for item in response.fields if item.key == "LLM_API_KEY")
    assert field.is_secret is True
    assert field.value is None
    assert field.has_value is True
    assert field.masked_value == "********"


def test_analysis_lite_response_has_no_heavy_result_payload() -> None:
    payload = AnalysisJobStatusLiteResponse(
        job=AnalysisJobRead(
            id=uuid4(),
            asset_id=uuid4(),
            status="processing",
            created_at=datetime.now(UTC),
        ),
        asset=AnalysisAssetRead(
            id=uuid4(),
            media_type="video",
            bucket="b",
            object_key="k",
            object_uri="s3://b/k",
            upload_status="uploaded",
            created_at=datetime.now(UTC),
        ),
        progress=AnalysisJobProgressRead(stage="processing"),
        has_result=True,
        result_summary=AnalysisResultSummaryRead(
            modality="video",
            overall_attention_score=70,
            hook_score_first_3_seconds=75,
            sustained_engagement_score=68,
            memory_proxy_score=64,
            cognitive_load_proxy=45,
        ),
    )
    dumped = payload.model_dump()
    assert "result" not in dumped
    assert dumped["has_result"] is True


def test_evaluator_modes_are_deduplicated() -> None:
    payload = EvaluationDispatchRequest(
        modes=[EvaluationMode.MARKETING, EvaluationMode.MARKETING, EvaluationMode.DEFENCE]
    )
    assert payload.modes == [EvaluationMode.MARKETING, EvaluationMode.DEFENCE]


def test_scoring_suggestion_filters_unsupported_lift_keys() -> None:
    suggestion = ScoringSuggestion(
        suggestion_type="copy",
        title="Improve CTA",
        rationale="Sharper CTA",
        confidence=0.7,
        expected_score_lift_json={"attention": 4, "unknown": 10},
    )
    assert suggestion.expected_score_lift_json == {"attention": 4.0}


def test_orm_schema_validates_from_attributes() -> None:
    source = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        creative_id=None,
        creative_version_id=None,
        upload_token="token",
        status="pending",
        bucket_name="bucket",
        storage_key="key",
        original_filename="file.txt",
        mime_type="text/plain",
        expected_size_bytes=123,
        uploaded_artifact_id=None,
        error_message=None,
        metadata_json={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    parsed = UploadSessionRead.model_validate(source)
    assert parsed.upload_token == "token"
