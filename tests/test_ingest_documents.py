from pathlib import Path

from src.application.ingest.ingest_documents import IngestDocuments
from src.domain.entities import Chunk, Document, Page
from src.domain.exceptions import InvalidDocumentError


def make_document(name: str, *pages: str) -> Document:
    return Document(
        title=name,
        file_name=f"{name}.pdf",
        sha256=f"sha-{name}",
        pages=tuple(
            Page(number=number, text=text) for number, text in enumerate(pages, start=1)
        ),
    )


class FakeLoader:
    def __init__(self, *documents: Document) -> None:
        self._documents = {document.file_name: document for document in documents}

    def load(self, path: Path) -> Document:
        if path.name not in self._documents:
            raise InvalidDocumentError("PDF dañado")
        return self._documents[path.name]


class FakeEmbedder:
    async def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(float(len(text)),) for text in texts]


class FakeRepository:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.saved: dict[str, list[Chunk]] = {}

    async def exists(self, sha256: str) -> bool:
        return sha256 in self.existing

    async def save(self, document: Document, chunks: list[Chunk]) -> None:
        self.existing.add(document.sha256)
        self.saved[document.file_name] = chunks


def make_use_case(loader: FakeLoader, repository: FakeRepository) -> IngestDocuments:
    return IngestDocuments(
        loader, FakeEmbedder(), repository, chunk_size=100, chunk_overlap=20
    )


async def test_ingests_new_document_with_one_chunk_per_page() -> None:
    document = make_document("tributos", "Requisitos para pagar.", "Plazos de pago.")
    repository = FakeRepository()

    report = await make_use_case(FakeLoader(document), repository).execute(
        [Path("tributos.pdf")]
    )

    assert report.ingested == ["tributos.pdf"]
    chunks = repository.saved["tributos.pdf"]
    assert [(c.page, c.index, c.content) for c in chunks] == [
        (1, 0, "Requisitos para pagar."),
        (2, 1, "Plazos de pago."),
    ]
    assert chunks[0].embedding == (22.0,)


async def test_skips_document_already_ingested() -> None:
    document = make_document("tributos", "Texto.")
    repository = FakeRepository(existing={document.sha256})

    report = await make_use_case(FakeLoader(document), repository).execute(
        [Path("tributos.pdf")]
    )

    assert report.skipped == ["tributos.pdf"]
    assert repository.saved == {}


async def test_damaged_pdf_does_not_stop_the_rest() -> None:
    document = make_document("tributos", "Texto.")
    repository = FakeRepository()

    report = await make_use_case(FakeLoader(document), repository).execute(
        [Path("danado.pdf"), Path("tributos.pdf")]
    )

    assert report.failed == [("danado.pdf", "PDF dañado")]
    assert report.ingested == ["tributos.pdf"]


async def test_document_without_text_is_reported_as_failed() -> None:
    document = make_document("escaneado", "   ")
    repository = FakeRepository()

    report = await make_use_case(FakeLoader(document), repository).execute(
        [Path("escaneado.pdf")]
    )

    assert report.failed == [("escaneado.pdf", "el PDF no tiene texto")]
    assert repository.saved == {}
