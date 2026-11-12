from collections.abc import AsyncGenerator
from typing import Protocol
from uuid import UUID

from src.domain.entities import (
    Answer,
    ChatMessage,
    Chunk,
    Document,
    Generation,
    Page,
    RetrievedChunk,
)


class ConversationTokens(Protocol):
    def issue(self, conversation_id: UUID) -> str: ...
    def verify(self, token: str) -> UUID: ...
    def request_key(self, client: str, scope: str) -> str: ...


class RequestLimiter(Protocol):
    async def allow(self, key: str, limit: int) -> bool: ...


class RatingRepository(Protocol):
    async def message_role(
        self, message_id: UUID, *, conversation_id: UUID | None = None
    ) -> str | None: ...

    async def save(self, message_id: UUID, stars: int) -> None: ...


class ConversationRepository(Protocol):
    async def history(
        self, conversation_id: UUID, limit: int
    ) -> tuple[ChatMessage, ...]: ...

    async def save_exchange(
        self, conversation_id: UUID | None, question: str, answer: Answer
    ) -> tuple[UUID, UUID]: ...


class LLM(Protocol):
    async def generate(self, system: str, prompt: str) -> Generation: ...

    def stream(
        self, system: str, prompt: str
    ) -> AsyncGenerator[str | Generation, None]:
        """Texto incremental seguido de una Generation final, solo al completar.

        El texto final coincide con los fragmentos concatenados. El consumidor debe
        cerrar el generador al interrumpir la lectura para liberar la conexión.
        """
        ...


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

    async def save(
        self, document: Document, chunks: list[Chunk], *, supersedes: UUID | None = None
    ) -> None:
        """Guarda documento y chunks, y reemplaza la versión indicada atómicamente.

        El destino debe existir y estar vigente. Nunca elimina versiones anteriores.
        """
        ...
