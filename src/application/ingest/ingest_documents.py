import hashlib
from dataclasses import dataclass, field

from src.application.ingest.chunking import split_text
from src.domain.entities import Chunk, Document
from src.domain.exceptions import InvalidDocumentError
from src.domain.ports import DocumentRepository, Embedder, PdfLoader


@dataclass(frozen=True)
class SourceFile:
    name: str
    content: bytes


@dataclass
class IngestionReport:
    ingested: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def _title_from_name(name: str) -> str:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem.replace("_", " ")


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
