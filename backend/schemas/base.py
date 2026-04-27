from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class APIBaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ORMBaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


StrictSchemaModel = APIBaseSchema
