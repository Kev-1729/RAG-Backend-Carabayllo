import hashlib
from dataclasses import dataclass, field
from typing import Protocol

from src.domain.entities import Chunk, Document, Page
from src.domain.exceptions import InvalidChunkingError, InvalidDocumentError
from src.domain.ports import DocumentRepository, Embedder, PdfLoader


@dataclass(frozen=True)
class SourceFile:
    name: str
    content: bytes


@dataclass(frozen=True)
class IngestedDocument:
    name: str
    pages: int
    chunks: int


@dataclass
class IngestionReport:
    ingested: list[IngestedDocument] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


class ParagraphChunker(Protocol):
    async def split(self, pages: tuple[Page, ...]) -> list[tuple[int, str]]: ...


def _title_from_name(name: str) -> str:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem.replace("_", " ")


class IngestDocuments:
    def __init__(
        self,
        loader: PdfLoader,
        embedder: Embedder,
        repository: DocumentRepository,
        chunker: ParagraphChunker,
    ) -> None:
        self._loader = loader
        self._embedder = embedder
        self._repository = repository
        self._chunker = chunker

    async def execute(self, files: list[SourceFile]) -> IngestionReport:
        report = IngestionReport()
        for source in files:
            sha256 = hashlib.sha256(source.content).hexdigest()
            if await self._repository.exists(sha256):
                report.skipped.append(source.name)
                continue

            try:
                pages = self._loader.load(source.content)
            except InvalidDocumentError as error:
                report.failed.append((source.name, str(error)))
                continue

            document = Document(
                title=_title_from_name(source.name),
                file_name=source.name,
                sha256=sha256,
                pages=pages,
            )
            try:
                pieces = await self._chunker.split(document.pages)
            except InvalidChunkingError as error:
                report.failed.append((source.name, str(error)))
                continue
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
            report.ingested.append(
                IngestedDocument(
                    name=document.file_name,
                    pages=document.page_count,
                    chunks=len(chunks),
                )
            )
        return report
