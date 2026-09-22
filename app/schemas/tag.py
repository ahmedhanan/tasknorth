import re
import uuid

from pydantic import BaseModel, field_validator

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_color(v: str | None) -> str | None:
    if v is not None and not _HEX_RE.match(v):
        raise ValueError("color must be a hex code in #RRGGBB format")
    return v


class TagCreate(BaseModel):
    name: str
    color: str | None = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        return _validate_color(v)


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        return _validate_color(v)


class TagResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    color: str | None

    model_config = {"from_attributes": True}
