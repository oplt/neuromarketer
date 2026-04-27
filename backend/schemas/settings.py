from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.schemas.base import APIBaseSchema


class SettingGroupRead(BaseModel):
    id: str
    label: str
    description: str


class SettingFieldRead(BaseModel):
    key: str
    env_name: str
    group_id: str
    label: str
    value: str | None = None
    has_value: bool = False
    masked_value: str | None = None
    value_type: str
    description: str | None = None
    is_secret: bool = False
    source: str = "env_file"
    updated_at: datetime | None = None


class SettingsResponse(BaseModel):
    env_file_path: str
    restart_required: bool = True
    groups: list[SettingGroupRead] = Field(default_factory=list)
    fields: list[SettingFieldRead] = Field(default_factory=list)


class SettingUpdateEntry(APIBaseSchema):
    key: str = Field(min_length=1, max_length=120)
    value: str | None = None


class SettingsUpdateRequest(APIBaseSchema):
    entries: list[SettingUpdateEntry] = Field(min_length=1)


class SettingsUpdateResponse(BaseModel):
    updated_count: int
    restart_required: bool = True
    saved_at: datetime
