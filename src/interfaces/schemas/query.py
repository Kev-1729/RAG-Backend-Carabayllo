from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class SourceResponse(BaseModel):
    document: str
    page: int


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
    conversation_id: UUID
    message_id: UUID


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
