from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from pydantic import SecretStr
from pytest import MonkeyPatch

from src.application.answer.answer_query import ABSTENTION_MESSAGE
from src.container import answer
from src.domain.entities import Query, RetrievedChunk
from src.infrastructure.llm import anthropic_llm


@pytest.fixture
def resources(monkeypatch: MonkeyPatch) -> SimpleNamespace:
    settings = SimpleNamespace(
        database_url=SecretStr("postgresql+asyncpg://test:test@localhost/test"),
        anthropic_api_key=SecretStr("test-anthropic"),
        llm_model="test-llm",
        voyage_api_key=SecretStr("test-voyage"),
        embedding_model="test-embedding",
        retrieval_max_distance=0.25,
    )
    engine = SimpleNamespace(dispose=AsyncMock())
    llm = SimpleNamespace(generate=AsyncMock(), aclose=AsyncMock())
    embedder = SimpleNamespace(embed_query=AsyncMock(return_value=(1.0,)))
    retriever = SimpleNamespace(search_similar=AsyncMock(return_value=[]))
    engine_factory = Mock(return_value=engine)
    llm_factory = Mock(return_value=llm)
    embedder_factory = Mock(return_value=embedder)
    session_factory = Mock()
    monkeypatch.setattr(answer, "get_settings", lambda: settings)
    monkeypatch.setattr(answer, "create_engine", engine_factory)
    monkeypatch.setattr(
        answer, "create_session_factory", Mock(return_value=session_factory)
    )
    monkeypatch.setattr(answer, "AnthropicLLM", llm_factory)
    monkeypatch.setattr(answer, "VoyageEmbedder", embedder_factory)
    monkeypatch.setattr(
        answer, "SqlAlchemyChunkRetriever", Mock(return_value=retriever)
    )
    repository = SimpleNamespace(
        history=AsyncMock(return_value=()),
        save_exchange=AsyncMock(return_value=(UUID(int=1), UUID(int=2))),
    )
    monkeypatch.setattr(
        answer, "SqlAlchemyConversationRepository", Mock(return_value=repository)
    )
    rating_repository = SimpleNamespace(
        message_role=AsyncMock(return_value="assistant"), save=AsyncMock()
    )
    rating_factory = Mock(return_value=rating_repository)
    monkeypatch.setattr(answer, "SqlAlchemyRatingRepository", rating_factory)
    return SimpleNamespace(
        rating_factory=rating_factory,
        rating_repository=rating_repository,
        session_factory=session_factory,
        engine=engine,
        llm=llm,
        embedder=embedder,
        retriever=retriever,
        engine_factory=engine_factory,
        llm_factory=llm_factory,
        embedder_factory=embedder_factory,
    )


async def test_resources_are_shared_and_closed_on_exit(
    resources: SimpleNamespace,
) -> None:
    async with answer.answer_services() as services:
        for _ in range(2):
            result = await services.conversation_query.execute(Query("pregunta"))
            assert result.text == ABSTENTION_MESSAGE
        await services.submit_rating.execute(UUID(int=2), 5)
        resources.rating_repository.save.assert_awaited_once_with(UUID(int=2), 5)
        resources.llm.generate.assert_not_awaited()
        resources.engine.dispose.assert_not_awaited()
        resources.llm.aclose.assert_not_awaited()
    resources.engine_factory.assert_called_once()
    resources.rating_factory.assert_called_once_with(resources.session_factory)
    resources.llm_factory.assert_called_once_with(
        api_key="test-anthropic", model="test-llm"
    )
    resources.embedder_factory.assert_called_once_with(
        api_key="test-voyage",
        model="test-embedding",
        dimension=1024,
    )
    resources.llm.aclose.assert_awaited_once()
    resources.engine.dispose.assert_awaited_once()


async def test_partial_startup_failure_closes_created_resources(
    resources: SimpleNamespace,
) -> None:
    resources.embedder_factory.side_effect = ValueError("startup failed")
    with pytest.raises(ValueError, match="startup failed"):
        async with answer.answer_services():
            pytest.fail("startup should fail")
    resources.llm.aclose.assert_awaited_once()
    resources.engine.dispose.assert_awaited_once()


async def test_container_passes_configured_threshold(
    resources: SimpleNamespace,
) -> None:
    resources.retriever.search_similar.return_value = [
        RetrievedChunk(
            UUID(int=1),
            "Licencias",
            "licencias.pdf",
            1,
            "Texto",
            0.3,
            chunk_id=UUID(int=99),
        )
    ]
    async with answer.answer_services() as services:
        result = await services.conversation_query.execute(Query("pregunta"))
    assert result.text == ABSTENTION_MESSAGE
    resources.llm.generate.assert_not_awaited()


async def test_engine_is_disposed_even_if_llm_close_fails(
    resources: SimpleNamespace,
) -> None:
    resources.llm.aclose.side_effect = RuntimeError("close failed")
    with pytest.raises(RuntimeError, match="close failed"):
        async with answer.answer_services():
            pass
    resources.engine.dispose.assert_awaited_once()


async def test_anthropic_adapter_closes_its_client(monkeypatch: MonkeyPatch) -> None:
    client = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(
        anthropic_llm.anthropic, "AsyncAnthropic", Mock(return_value=client)
    )
    llm = anthropic_llm.AnthropicLLM("test", "model")
    await llm.aclose()
    client.close.assert_awaited_once()
