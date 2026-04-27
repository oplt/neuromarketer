from __future__ import annotations

from typing import Any

from pydantic import Field

from backend.schemas.base import APIBaseSchema


class MetadataPayload(APIBaseSchema):
    data: dict[str, Any] = Field(default_factory=dict)


class RuntimeParamsPayload(APIBaseSchema):
    data: dict[str, Any] = Field(default_factory=dict)


class PaginationParams(APIBaseSchema):
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class PaginatedResponseMeta(APIBaseSchema):
    total: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1)
    offset: int = Field(default=0, ge=0)
