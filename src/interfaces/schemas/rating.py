from uuid import UUID

from pydantic import BaseModel, Field


class RatingRequest(BaseModel):
    stars: int = Field(ge=1, le=5, strict=True)


class RatingResponse(BaseModel):
    message_id: UUID
    stars: int
