from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    text: str


@dataclass(frozen=True)
class Answer:
    text: str


@dataclass(frozen=True)
class Page:
    number: int
    text: str


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
