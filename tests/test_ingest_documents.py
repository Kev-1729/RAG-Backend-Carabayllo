import hashlib
from unittest.mock import AsyncMock, patch
from uuid import UUID

from src.application.ingest.ingest_documents import IngestDocuments, SourceFile
from src.domain.entities import Chunk, Document, Page
from src.domain.exceptions import (
    DocumentReplacementError,
    InvalidChunkingError,
    InvalidDocumentError,
)

DAMAGED = b"damaged"
EMPTY = b"empty-pdf"
TRIBUTOS = b"tributos-pdf"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class FakeLoader:
    def __init__(self, pages: dict[bytes, tuple[Page, ...]]) -> None:
        self._pages = pages
        self.loaded: list[bytes] = []

    def load(self, content: bytes) -> tuple[Page, ...]:
        self.loaded.append(content)
        if content not in self._pages:
            raise InvalidDocumentError("PDF dañado")
        return self._pages[content]


class FakeEmbedder:
    async def embed_documents(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(float(len(text)),) for text in texts]

    async def embed_query(self, text: str) -> tuple[float, ...]:
        raise AssertionError("La ingesta no debe generar embeddings de consultas")


class FakeRepository:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.saved: dict[str, list[Chunk]] = {}
        self.saved_titles: dict[str, str] = {}

    async def exists(self, sha256: str) -> bool:
        return sha256 in self.existing

    async def save(
        self, document: Document, chunks: list[Chunk], *, supersedes: UUID | None = None
    ) -> None:
        self.existing.add(document.sha256)
        self.saved[document.file_name] = chunks
        self.saved_titles[document.file_name] = document.title


class FakeChunker:
    async def split(self, pages: tuple[Page, ...]) -> list[tuple[int, str]]:
        return [
            (page.number, paragraph) for page in pages for paragraph in page.paragraphs
        ]


class FailingChunker:
    async def split(self, pages: tuple[Page, ...]) -> list[tuple[int, str]]:
        raise InvalidChunkingError("el modelo no devolvió grupos de párrafos válidos")


def make_use_case(
    loader: FakeLoader,
    repository: FakeRepository,
    chunker: FakeChunker | FailingChunker | None = None,
) -> IngestDocuments:
    return IngestDocuments(loader, FakeEmbedder(), repository, chunker or FakeChunker())


def tributos_loader() -> FakeLoader:
    return FakeLoader(
        {
            TRIBUTOS: (
                Page(number=1, paragraphs=("Requisitos para pagar.",)),
                Page(number=2, paragraphs=("Plazos de pago.",)),
            )
        }
    )


async def test_ingests_new_document_with_one_chunk_per_page() -> None:
    repository = FakeRepository()
    loader = tributos_loader()

    report = await make_use_case(loader, repository).execute(
        [SourceFile(name="tributos.pdf", content=TRIBUTOS)]
    )

    assert [(item.name, item.pages, item.chunks) for item in report.ingested] == [
        ("tributos.pdf", 2, 2)
    ]
    chunks = repository.saved["tributos.pdf"]
    assert [(c.page, c.index, c.content) for c in chunks] == [
        (1, 0, "Requisitos para pagar."),
        (2, 1, "Plazos de pago."),
    ]
    assert chunks[0].embedding == (22.0,)
    assert repository.saved_titles["tributos.pdf"] == "tributos"
    assert loader.loaded == [TRIBUTOS]


async def test_skips_document_already_ingested_before_reading_pdf() -> None:
    repository = FakeRepository(existing={_sha(TRIBUTOS)})
    loader = tributos_loader()

    report = await make_use_case(loader, repository).execute(
        [SourceFile(name="tributos.pdf", content=TRIBUTOS)]
    )

    assert report.skipped == ["tributos.pdf"]
    assert repository.saved == {}
    assert loader.loaded == []


async def test_damaged_pdf_does_not_stop_the_rest() -> None:
    repository = FakeRepository()
    loader = tributos_loader()

    report = await make_use_case(loader, repository).execute(
        [
            SourceFile(name="danado.pdf", content=DAMAGED),
            SourceFile(name="tributos.pdf", content=TRIBUTOS),
        ]
    )

    assert report.failed == [("danado.pdf", "PDF dañado")]
    assert [(item.name, item.pages, item.chunks) for item in report.ingested] == [
        ("tributos.pdf", 2, 2)
    ]


async def test_document_without_text_is_reported_as_failed() -> None:
    repository = FakeRepository()
    loader = FakeLoader({EMPTY: (Page(number=1, paragraphs=()),)})

    report = await make_use_case(loader, repository).execute(
        [SourceFile(name="escaneado.pdf", content=EMPTY)]
    )

    assert report.failed == [("escaneado.pdf", "el PDF no tiene texto")]
    assert repository.saved == {}


async def test_title_comes_from_file_name() -> None:
    repository = FakeRepository()
    loader = tributos_loader()

    await make_use_case(loader, repository).execute(
        [SourceFile(name="Licencia_Funcionamiento.pdf", content=TRIBUTOS)]
    )

    assert repository.saved_titles["Licencia_Funcionamiento.pdf"] == (
        "Licencia Funcionamiento"
    )


async def test_invalid_chunking_does_not_stop_the_rest() -> None:
    repository = FakeRepository()
    loader = tributos_loader()

    report = await make_use_case(loader, repository, FailingChunker()).execute(
        [SourceFile(name="tributos.pdf", content=TRIBUTOS)]
    )

    assert report.failed == [
        ("tributos.pdf", "el modelo no devolvió grupos de párrafos válidos")
    ]
    assert repository.saved == {}


async def test_replacement_passes_explicit_target_to_repository() -> None:
    repository = FakeRepository()
    with patch.object(repository, "save", new_callable=AsyncMock) as save_mock:
        report = await make_use_case(tributos_loader(), repository).execute(
            [SourceFile("nueva.pdf", TRIBUTOS, supersedes=UUID(int=1))]
        )
    assert len(report.ingested) == 1
    save_mock.assert_awaited_once()
    assert save_mock.await_args is not None
    assert save_mock.await_args.kwargs == {"supersedes": UUID(int=1)}


async def test_existing_content_cannot_silently_skip_replacement() -> None:
    repository = FakeRepository(existing={_sha(TRIBUTOS)})
    loader = tributos_loader()
    report = await make_use_case(loader, repository).execute(
        [SourceFile("nueva.pdf", TRIBUTOS, supersedes=UUID(int=1))]
    )
    assert len(report.failed) == 1
    assert report.skipped == []
    assert loader.loaded == []
    assert repository.saved == {}


async def test_rejected_replacement_is_reported_and_next_file_is_ingested() -> None:
    repository = FakeRepository()
    with patch.object(
        repository,
        "save",
        new_callable=AsyncMock,
        side_effect=[DocumentReplacementError("ya reemplazado"), None],
    ):
        report = await make_use_case(tributos_loader(), repository).execute(
            [
                SourceFile("nueva.pdf", TRIBUTOS, supersedes=UUID(int=1)),
                SourceFile("otra.pdf", TRIBUTOS),
            ]
        )
    assert report.failed == [("nueva.pdf", "ya reemplazado")]
    assert [d.name for d in report.ingested] == ["otra.pdf"]
