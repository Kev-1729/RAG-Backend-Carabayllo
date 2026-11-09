from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.entities import Chunk, Document
from src.domain.exceptions import DocumentReplacementError
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

    async def save(
        self, document: Document, chunks: list[Chunk], *, supersedes: UUID | None = None
    ) -> None:
        try:
            await self._save(document, chunks, supersedes)
        except IntegrityError as error:
            if supersedes is None:
                raise
            raise DocumentReplacementError(
                "no se pudo guardar el reemplazo; se conservó la versión anterior"
            ) from error

    async def _save(
        self, document: Document, chunks: list[Chunk], supersedes: UUID | None
    ) -> None:
        async with self._session_factory() as session, session.begin():
            previous = None
            if supersedes is not None:
                previous = await session.scalar(
                    select(DocumentModel)
                    .where(DocumentModel.id == supersedes)
                    .with_for_update()
                )
                if previous is None:
                    raise DocumentReplacementError(
                        "el documento a reemplazar no existe"
                    )
                if previous.superseded_by_id is not None:
                    raise DocumentReplacementError("el documento ya fue reemplazado")
            model = DocumentModel(
                title=document.title,
                file_name=document.file_name,
                sha256=document.sha256,
                page_count=document.page_count,
            )
            session.add(model)
            await session.flush()
            if previous is not None:
                previous.superseded_by_id = model.id
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
