from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Query:
    text: str


@dataclass(frozen=True)
class AnswerSource:
    document_id: UUID
    document: str
    page: int


@dataclass(frozen=True)
class Answer:
    text: str
    sources: tuple[AnswerSource, ...] = ()


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
