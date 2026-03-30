from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMBaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UploadInitRequest(BaseModel):
    project_id: UUID
    creative_id: UUID | None = None
    creative_version_id: UUID | None = None
    artifact_kind: str = Field(default="creative_source", min_length=1, max_length=50)
    original_filename: str = Field(min_length=1, max_length=512)
    mime_type: str | None = Field(default=None, max_length=120)
    expected_size_bytes: int | None = Field(default=None, ge=0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class UploadInitResponse(BaseModel):
    upload_session_id: UUID
    upload_token: str
    bucket_name: str
    storage_key: str
    storage_uri: str
    presigned_put_url: str | None = None


class UploadCompleteRequest(BaseModel):
    upload_token: str


class UploadSessionRead(ORMBaseSchema):
    id: UUID
    project_id: UUID
    creative_id: UUID | None
    creative_version_id: UUID | None
    upload_token: str
    status: str
    bucket_name: str
    storage_key: str
    original_filename: str | None
    mime_type: str | None
    expected_size_bytes: int | None
    uploaded_artifact_id: UUID | None
    error_message: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class StoredArtifactRead(ORMBaseSchema):
    id: UUID
    project_id: UUID
    creative_id: UUID | None
    creative_version_id: UUID | None
    artifact_kind: str
    bucket_name: str
    storage_key: str
    storage_uri: str
    original_filename: str | None
    mime_type: str | None
    file_size_bytes: int | None
    sha256: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DirectUploadResponse(BaseModel):
    upload_session: UploadSessionRead
    artifact: StoredArtifactRead
