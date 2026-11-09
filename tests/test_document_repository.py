from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from src.domain.entities import Chunk, Document, Page
from src.domain.exceptions import DocumentReplacementError
from src.infrastructure.db.document_repository import SqlAlchemyDocumentRepository
from src.infrastructure.db.models import DocumentModel


def repository() -> tuple[SqlAlchemyDocumentRepository, AsyncMock]:
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.begin = Mock(return_value=AsyncMock())
    session.add = Mock()
    session.add_all = Mock()
    return SqlAlchemyDocumentRepository(Mock(return_value=session)), session


DOCUMENT = Document("Nueva", "nueva.pdf", "a" * 64, (Page(1, ("Texto",)),))
CHUNKS = [Chunk(1, 0, "Texto", (1.0,))]


async def test_replacement_locks_previous_and_saves_without_deleting_history() -> None:
    repo, session = repository()
    previous = DocumentModel(id=UUID(int=1), superseded_by_id=None)
    session.scalar.return_value = previous

    async def assign_id() -> None:
        session.add.call_args.args[0].id = UUID(int=2)

    session.flush.side_effect = assign_id
    await repo.save(DOCUMENT, CHUNKS, supersedes=previous.id)
    statement = session.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "FOR UPDATE" in str(statement)
    assert previous.id in statement.params.values()
    assert previous.superseded_by_id == UUID(int=2)
    saved = session.add.call_args.args[0]
    assert saved.file_name == "nueva.pdf"
    chunks = list(session.add_all.call_args.args[0])
    assert chunks[0].document_id == UUID(int=2)
    session.delete.assert_not_awaited()
    session.begin.return_value.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.parametrize("missing", [True, False])
async def test_missing_or_superseded_target_rolls_back(missing: bool) -> None:
    repo, session = repository()
    session.scalar.return_value = (
        None if missing else DocumentModel(id=UUID(int=1), superseded_by_id=UUID(int=2))
    )
    with pytest.raises(DocumentReplacementError):
        await repo.save(DOCUMENT, CHUNKS, supersedes=UUID(int=1))
    session.add.assert_not_called()
    assert (
        session.begin.return_value.__aexit__.await_args.args[0]
        is DocumentReplacementError
    )


async def test_duplicate_replacement_rolls_back_transaction() -> None:
    repo, session = repository()
    session.scalar.return_value = DocumentModel(id=UUID(int=1), superseded_by_id=None)
    session.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    with pytest.raises(DocumentReplacementError):
        await repo.save(DOCUMENT, CHUNKS, supersedes=UUID(int=1))
    assert session.begin.return_value.__aexit__.await_args.args[0] is IntegrityError
    session.add_all.assert_not_called()


async def test_normal_ingestion_does_not_lock_an_existing_document() -> None:
    repo, session = repository()
    await repo.save(DOCUMENT, CHUNKS)
    session.scalar.assert_not_awaited()
