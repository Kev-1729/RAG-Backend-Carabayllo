from dataclasses import dataclass, field
from pathlib import Path

from src.application.ingest.chunking import split_text
from src.domain.entities import Chunk
from src.domain.exceptions import InvalidDocumentError
from src.domain.ports import DocumentRepository, Embedder, PdfLoader


@dataclass
class IngestionReport:
    ingested: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


class IngestDocuments:
    def __init__(
        self,
        loader: PdfLoader,
        embedder: Embedder,
        repository: DocumentRepository,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self._loader = loader
        self._embedder = embedder
        self._repository = repository
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def execute(self, paths: list[Path]) -> IngestionReport:
        report = IngestionReport()
        for path in paths:
            try:
                document = self._loader.load(path)
            except InvalidDocumentError as error:
                report.failed.append((path.name, str(error)))
                continue

            if await self._repository.exists(document.sha256):
                report.skipped.append(document.file_name)
                continue

            pieces = [
                (page.number, text)
                for page in document.pages
                for text in split_text(page.text, self._chunk_size, self._chunk_overlap)
            ]
            if not pieces:
                report.failed.append((document.file_name, "el PDF no tiene texto"))
                continue

            embeddings = await self._embedder.embed_documents(
                [text for _, text in pieces]
            )
            chunks = [
                Chunk(page=page, index=index, content=text, embedding=embedding)
                for index, ((page, text), embedding) in enumerate(
                    zip(pieces, embeddings, strict=True)
                )
            ]
            await self._repository.save(document, chunks)
            report.ingested.append(document.file_name)
        return report
