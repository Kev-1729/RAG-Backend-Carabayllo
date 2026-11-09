from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import (
    InterfaceError,
    OperationalError,
    ProgrammingError,
    TimeoutError as SqlAlchemyTimeoutError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.entities import RetrievedChunk
from src.domain.exceptions import RetrievalUnavailableError
from src.domain.ports import ChunkRetriever
from src.infrastructure.db.chunk_retriever import SqlAlchemyChunkRetriever

EMBEDDING = (1.0,) + (0.0,) * 1023


def make_retriever() -> tuple[ChunkRetriever, MagicMock, AsyncMock]:
    session = AsyncMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    session.execute.return_value = []
    factory = MagicMock(spec=async_sessionmaker, return_value=session)
    return SqlAlchemyChunkRetriever(factory), factory, session


@pytest.mark.parametrize("k", [None, 2])
async def test_search_compiles_cosine_order_active_filter_and_limit(
    k: int | None,
) -> None:
    retriever, _, session = make_retriever()
    if k is None:
        await retriever.search_similar(EMBEDDING)
    else:
        await retriever.search_similar(EMBEDDING, k=k)

    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = " ".join(str(compiled).split())

    assert "JOIN documents ON chunks.document_id = documents.id" in sql
    assert "WHERE documents.superseded_by_id IS NULL" in sql
    assert "ORDER BY chunks.embedding <=> %(embedding_1)s" in sql
    assert "LIMIT %(param_1)s" in sql
    assert compiled.params["embedding_1"] == list(EMBEDDING)
    assert compiled.params["param_1"] == (5 if k is None else k)
    session.__aexit__.assert_awaited_once()


async def test_search_maps_rows_to_domain_results_in_returned_order() -> None:
    retriever, _, session = make_retriever()
    document_id = UUID("00000000-0000-0000-0000-000000000001")
    rows = [
        SimpleNamespace(
            chunk_id=UUID(int=99),
            document_id=document_id,
            title="Licencias",
            file_name="licencias.pdf",
            page=page,
            content=content,
            distance=distance,
        )
        for page, content, distance in [(3, "Requisitos", 0.1), (1, "Trámite", 0.3)]
    ]
    session.execute.return_value = rows

    result = await retriever.search_similar(EMBEDDING)

    assert result == [
        RetrievedChunk(
            document_id=document_id,
            title="Licencias",
            file_name="licencias.pdf",
            page=3,
            content="Requisitos",
            distance=0.1,
            chunk_id=UUID(int=99),
        ),
        RetrievedChunk(
            document_id=document_id,
            title="Licencias",
            file_name="licencias.pdf",
            page=1,
            content="Trámite",
            distance=0.3,
            chunk_id=UUID(int=99),
        ),
    ]


async def test_search_without_rows_returns_empty_list() -> None:
    retriever, _, _ = make_retriever()
    assert await retriever.search_similar(EMBEDDING) == []


@pytest.mark.parametrize("k", [0, -1])
async def test_nonpositive_limit_is_rejected_before_opening_session(k: int) -> None:
    retriever, factory, _ = make_retriever()

    with pytest.raises(ValueError, match="k must be positive"):
        await retriever.search_similar(EMBEDDING, k=k)

    factory.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT", {}, Exception("connection lost")),
        InterfaceError("SELECT", {}, Exception("connection closed")),
        SqlAlchemyTimeoutError("pool exhausted"),
        ConnectionRefusedError("connection refused"),
        TimeoutError("connection timed out"),
    ],
)
async def test_database_unavailability_is_not_an_empty_result(error: Exception) -> None:
    retriever, _, session = make_retriever()
    session.execute.side_effect = error

    with pytest.raises(RetrievalUnavailableError) as raised:
        await retriever.search_similar(EMBEDDING)

    assert raised.value.__cause__ is error
    session.__aexit__.assert_awaited_once()


async def test_failure_to_open_session_is_translated() -> None:
    retriever, _, session = make_retriever()
    session.__aenter__.side_effect = ConnectionRefusedError()

    with pytest.raises(RetrievalUnavailableError):
        await retriever.search_similar(EMBEDDING)


async def test_programming_errors_are_not_masked_as_unavailability() -> None:
    retriever, _, session = make_retriever()
    session.execute.side_effect = ProgrammingError("SELECT", {}, Exception("bad SQL"))

    with pytest.raises(ProgrammingError):
        await retriever.search_similar(EMBEDDING)
