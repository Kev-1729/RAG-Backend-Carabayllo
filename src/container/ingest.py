from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.application.ingest.ingest_documents import IngestDocuments
from src.config import settings
from src.infrastructure.db.database import create_engine, create_session_factory
from src.infrastructure.db.document_repository import SqlAlchemyDocumentRepository
from src.infrastructure.db.models import EMBEDDING_DIMENSION
from src.infrastructure.embeddings.voyage_embedder import VoyageEmbedder
from src.infrastructure.pdf.pypdf_loader import PypdfLoader


@asynccontextmanager
async def ingest_documents() -> AsyncIterator[IngestDocuments]:
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        yield IngestDocuments(
            loader=PypdfLoader(),
            embedder=VoyageEmbedder(
                api_key=settings.voyage_api_key.get_secret_value(),
                model=settings.embedding_model,
                dimension=EMBEDDING_DIMENSION,
            ),
            repository=SqlAlchemyDocumentRepository(create_session_factory(engine)),
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    finally:
        await engine.dispose()
