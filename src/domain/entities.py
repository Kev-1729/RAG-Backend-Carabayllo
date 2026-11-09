from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Query:
    text: str
    conversation_id: UUID | None = None


@dataclass(frozen=True)
class AnswerSource:
    document_id: UUID
    document: str
    page: int


@dataclass(frozen=True)
class AnswerReference:
    """Contexto de una respuesta sin abstención; no certifica citas utilizadas.

    Rank desde 1; score = 1 - distancia coseno, con rango [-1, 1].
    """

    chunk_id: UUID
    rank: int
    score: float


@dataclass(frozen=True)
class Answer:
    text: str
    sources: tuple[AnswerSource, ...] = ()
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    references: tuple[AnswerReference, ...] = ()


@dataclass(frozen=True)
class Generation:
    text: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ChatMessage:
    id: UUID
    role: str
    content: str
    created_at: datetime


@dataclass(frozen=True)
class Page:
    number: int
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Document:
    title: str
    file_name: str
    sha256: str
    pages: tuple[Page, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)


@dataclass(frozen=True)
class Chunk:
    page: int
    index: int
    content: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class RetrievedChunk:
    """Fragmento recuperado; page es la página inicial y menor distance es mejor."""

    document_id: UUID
    title: str
    file_name: str
    page: int
    content: str
    distance: float
    chunk_id: UUID = field(kw_only=True)
