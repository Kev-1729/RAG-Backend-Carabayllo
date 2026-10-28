from typing import Protocol

from src.domain.entities import Chunk, Document, Page


class LLM(Protocol):
    async def generate(self, system: str, prompt: str) -> str: ...


class PdfLoader(Protocol):
    def load(self, content: bytes) -> tuple[Page, ...]: ...


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]: ...


class DocumentRepository(Protocol):
    async def exists(self, sha256: str) -> bool: ...

    async def save(self, document: Document, chunks: list[Chunk]) -> None: ...
