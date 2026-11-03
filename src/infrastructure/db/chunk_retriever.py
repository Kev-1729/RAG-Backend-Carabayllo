from sqlalchemy import select
from sqlalchemy.exc import (
    InterfaceError,
    OperationalError,
    TimeoutError as SqlAlchemyTimeoutError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.entities import RetrievedChunk
from src.domain.exceptions import RetrievalUnavailableError
from src.infrastructure.db.models import ChunkModel, DocumentModel


class SqlAlchemyChunkRetriever:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search_similar(
        self, embedding: tuple[float, ...], k: int = 5
    ) -> list[RetrievedChunk]:
        if k <= 0:
            raise ValueError("k must be positive")

        distance = ChunkModel.embedding.cosine_distance(list(embedding))
        statement = (
            select(
                DocumentModel.id.label("document_id"),
                DocumentModel.title,
                DocumentModel.file_name,
                ChunkModel.page,
                ChunkModel.content,
                distance.label("distance"),
            )
            .join(DocumentModel, ChunkModel.document_id == DocumentModel.id)
            .where(DocumentModel.superseded_by_id.is_(None))
            .order_by(distance)
            .limit(k)
        )
        try:
            async with self._session_factory() as session:
                result = await session.execute(statement)
                return [
                    RetrievedChunk(
                        document_id=row.document_id,
                        title=row.title,
                        file_name=row.file_name,
                        page=row.page,
                        content=row.content,
                        distance=float(row.distance),
                    )
                    for row in result
                ]
        except (
            OperationalError,
            InterfaceError,
            SqlAlchemyTimeoutError,
            OSError,
            TimeoutError,
        ) as error:
            raise RetrievalUnavailableError() from error
