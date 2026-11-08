from typing import Protocol

from src.domain.entities import Chunk, Document, Page, RetrievedChunk


class LLM(Protocol):
    async def generate(self, system: str, prompt: str) -> str: ...


class PdfLoader(Protocol):
    def load(self, content: bytes) -> tuple[Page, ...]: ...


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]: ...

    async def embed_query(self, text: str) -> tuple[float, ...]: ...


class ChunkRetriever(Protocol):
    async def search_similar(
        self, embedding: tuple[float, ...], k: int = 5
    ) -> list[RetrievedChunk]:
        """Devuelve hasta k fragmentos vigentes por distancia coseno ascendente.

        k debe ser positivo. Una lista vacía indica ausencia de resultados,
        no indisponibilidad del servicio.
        """
        ...


class DocumentRepository(Protocol):
    async def exists(self, sha256: str) -> bool: ...

    async def save(self, document: Document, chunks: list[Chunk]) -> None: ...
