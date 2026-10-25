from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.entities import Chunk, Document
from src.infrastructure.db.models import ChunkModel, DocumentModel


class SqlAlchemyDocumentRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def exists(self, sha256: str) -> bool:
        async with self._session_factory() as session:
            found = await session.scalar(
                select(DocumentModel.id).where(DocumentModel.sha256 == sha256)
            )
        return found is not None

    async def save(self, document: Document, chunks: list[Chunk]) -> None:
        async with self._session_factory() as session, session.begin():
            model = DocumentModel(
                title=document.title,
                file_name=document.file_name,
                sha256=document.sha256,
                page_count=document.page_count,
            )
            session.add(model)
            await session.flush()
            session.add_all(
                ChunkModel(
                    document_id=model.id,
                    page=chunk.page,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    embedding=list(chunk.embedding),
                )
                for chunk in chunks
            )
