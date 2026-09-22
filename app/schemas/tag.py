import uuid

from pydantic import BaseModel


class TagCreate(BaseModel):
    name: str
    color: str | None = None


class TagResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    color: str | None

    model_config = {"from_attributes": True}
