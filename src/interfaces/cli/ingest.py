import argparse
import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.ingest.ingest_documents import IngestDocuments, IngestionReport
from src.config import settings
from src.infrastructure.db.document_repository import SqlAlchemyDocumentRepository
from src.infrastructure.db.models import EMBEDDING_DIMENSION
from src.infrastructure.embeddings.voyage_embedder import VoyageEmbedder
from src.infrastructure.pdf.pypdf_loader import PypdfLoader


async def ingest(folder: Path) -> IngestionReport:
    engine = create_async_engine(settings.database_url.get_secret_value())
    try:
        use_case = IngestDocuments(
            loader=PypdfLoader(),
            embedder=VoyageEmbedder(
                api_key=settings.voyage_api_key.get_secret_value(),
                model=settings.embedding_model,
                dimension=EMBEDDING_DIMENSION,
            ),
            repository=SqlAlchemyDocumentRepository(async_sessionmaker(engine)),
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        return await use_case.execute(sorted(folder.glob("*.pdf")))
    finally:
        await engine.dispose()


def print_report(report: IngestionReport) -> None:
    print(f"Ingeridos: {len(report.ingested)}")
    for name in report.ingested:
        print(f"  + {name}")
    print(f"Omitidos (ya existían): {len(report.skipped)}")
    for name in report.skipped:
        print(f"  = {name}")
    print(f"Fallidos: {len(report.failed)}")
    for name, reason in report.failed:
        print(f"  ! {name}: {reason}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingiere los PDF de una carpeta en la base de datos."
    )
    parser.add_argument("folder", type=Path, help="carpeta con los PDF a ingerir")
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error(f"no existe la carpeta: {args.folder}")

    report = asyncio.run(ingest(args.folder))
    print_report(report)
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
