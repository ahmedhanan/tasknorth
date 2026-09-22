import re
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_color(v: str | None) -> str | None:
    if v is not None and not _HEX_RE.match(v):
        raise ValueError("color must be a hex code in #RRGGBB format")
    return v


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    color: str | None = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        return _validate_color(v)


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        return _validate_color(v)


class ProjectResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None
    color: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
