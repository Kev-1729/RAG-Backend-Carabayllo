from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from pytest import MonkeyPatch

from src import config
from src.application.answer.answer_query import ABSTENTION_MESSAGE, AnswerQuery
from src.application.answer.conversation_query import ConversationQuery
from src.application.answer.submit_rating import SubmitRating
from src.container.answer import AnswerServices
from src.domain.entities import ChatMessage, RetrievedChunk
from src.domain.exceptions import (
    ConversationNotFoundError,
    ConversationUnavailableError,
    EmbeddingUnavailableError,
    LLMUnavailableError,
    RetrievalUnavailableError,
)
from src.domain.ports import (
    LLM,
    ChunkRetriever,
    ConversationRepository,
    Embedder,
    RatingRepository,
)
from src.interfaces.schemas.query import QueryResponse


class MemoryConversations:
    def __init__(self) -> None:
        self.messages: dict[UUID, list[ChatMessage]] = {}

    async def history(
        self, conversation_id: UUID, limit: int
    ) -> tuple[ChatMessage, ...]:
        if conversation_id not in self.messages:
            raise ConversationNotFoundError()
        return tuple(self.messages[conversation_id][-limit:])

    async def save_exchange(
        self, conversation_id: UUID | None, question: str, answer: str
    ) -> tuple[UUID, UUID]:
        if conversation_id is None:
            conversation_id = uuid4()
            self.messages[conversation_id] = []
        if conversation_id not in self.messages:
            raise ConversationNotFoundError()
        user = ChatMessage(uuid4(), "user", question, datetime.now(timezone.utc))
        assistant = ChatMessage(
            uuid4(), "assistant", answer, datetime.now(timezone.utc)
        )
        self.messages[conversation_id].extend([user, assistant])
        return conversation_id, assistant.id


def _client(
    monkeypatch: MonkeyPatch,
    use_case: ConversationQuery,
    submit_rating: SubmitRating | None = None,
) -> TestClient:
    settings = config.Settings(
        _env_file=None,  # type: ignore[call-arg]
        anthropic_api_key=SecretStr("test"),
        llm_model="test-model",
        database_url=SecretStr("postgresql+asyncpg://test:test@localhost/test"),
        voyage_api_key=SecretStr("test"),
        cors_allow_origins="",
        embedding_model="test-model",
        chunk_size=1000,
        retrieval_max_distance=0.5,
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    from src import main

    monkeypatch.setattr(main, "get_settings", lambda: settings)

    @asynccontextmanager
    async def fake_resources() -> AsyncIterator[AnswerServices]:
        yield AnswerServices(
            use_case, submit_rating or SubmitRating(AsyncMock(spec=RatingRepository))
        )

    monkeypatch.setattr(main, "answer_services", fake_resources)
    return TestClient(main.create_application())


def _rag() -> tuple[ConversationQuery, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    llm = AsyncMock(spec=LLM)
    llm.generate.return_value = "Presenta el formulario [1]."
    embedder = AsyncMock(spec=Embedder)
    embedder.embed_query.return_value = (1.0, 0.0)
    retriever = AsyncMock(spec=ChunkRetriever)
    retriever.search_similar.return_value = [
        RetrievedChunk(UUID(int=1), "Licencias", "licencias.pdf", 2, "Formulario", 0.1),
        RetrievedChunk(UUID(int=1), "Licencias", "licencias.pdf", 2, "Anexo", 0.2),
    ]
    repository = AsyncMock(spec=ConversationRepository, wraps=MemoryConversations())
    return (
        ConversationQuery(AnswerQuery(llm, embedder, retriever, 0.5), repository),
        llm,
        embedder,
        retriever,
        repository,
    )


@pytest.mark.parametrize("question", ["", "   ", "\t\n\r", "\u00a0"])
def test_blank_question_never_calls_providers_or_storage(
    monkeypatch: MonkeyPatch, question: str
) -> None:
    use_case, llm, embedder, retriever, repository = _rag()
    with _client(monkeypatch, use_case) as client:
        response = client.post("/query", json={"question": question})
    assert response.status_code == 422
    llm.generate.assert_not_awaited()
    embedder.embed_query.assert_not_awaited()
    retriever.search_similar.assert_not_awaited()
    repository.save_exchange.assert_not_awaited()
    repository.history.assert_not_awaited()


def test_question_is_trimmed_and_persisted(monkeypatch: MonkeyPatch) -> None:
    use_case, _, embedder, _, repository = _rag()
    with _client(monkeypatch, use_case) as client:
        response = client.post(
            "/query", json={"question": "  Requisitos de licencia? \n"}
        )
    assert response.status_code == 200
    embedder.embed_query.assert_awaited_once_with("Requisitos de licencia?")
    repository.save_exchange.assert_awaited_once_with(
        None, "Requisitos de licencia?", "Presenta el formulario [1]."
    )
    assert UUID(response.json()["conversation_id"])
    assert UUID(response.json()["message_id"])


def test_http_continuation_persists_and_recovers_separate_conversations(
    monkeypatch: MonkeyPatch,
) -> None:
    use_case, _, embedder, retriever, repository = _rag()
    client = _client(monkeypatch, use_case)
    with client:
        first = client.post("/query", json={"question": "Licencia de bodega"}).json()
        identifier = first["conversation_id"]
        assert first["sources"] == [{"document": "Licencias", "page": 2}]
        second = client.post(
            "/query",
            json={"question": "¿Y cuánto cuesta?", "conversation_id": identifier},
        )
        assert second.status_code == 200
        assert second.json()["conversation_id"] == identifier
        assert second.json()["message_id"] != first["message_id"]
        embedder.embed_query.assert_awaited_with(
            "Licencia de bodega\n¿Y cuánto cuesta?"
        )
        history = client.get(f"/conversations/{identifier}")
        assert history.status_code == 200
        assert [m["role"] for m in history.json()] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert history.json()[0]["content"] == "Licencia de bodega"
        assert history.json()[-1]["id"] == second.json()["message_id"]
        assert len(client.get(f"/conversations/{identifier}?limit=2").json()) == 2
        other = client.post("/query", json={"question": "Otro tema"}).json()
        assert other["conversation_id"] != identifier
        assert len(client.get(f"/conversations/{other['conversation_id']}").json()) == 2
    assert retriever.search_similar.await_count == 3
    assert repository.save_exchange.await_count == 3
    assert isinstance(client.app, FastAPI)
    assert not hasattr(client.app.state, "conversation_query")


def test_http_abstention_is_persisted_without_llm(monkeypatch: MonkeyPatch) -> None:
    use_case, llm, _, retriever, repository = _rag()
    retriever.search_similar.return_value = []
    with _client(monkeypatch, use_case) as client:
        response = client.post("/query", json={"question": "Requisitos"})
        data = response.json()
        history = client.get(f"/conversations/{data['conversation_id']}").json()
    assert response.status_code == 200
    assert data["answer"] == ABSTENTION_MESSAGE
    assert data["sources"] == []
    assert history[-1]["content"] == ABSTENTION_MESSAGE
    llm.generate.assert_not_awaited()
    repository.save_exchange.assert_awaited_once_with(
        None, "Requisitos", ABSTENTION_MESSAGE
    )


@pytest.mark.parametrize("stage", ["embedding", "retrieval", "llm"])
def test_provider_errors_return_503_without_persisting_turn(
    monkeypatch: MonkeyPatch, stage: str
) -> None:
    use_case, llm, embedder, retriever, repository = _rag()
    errors = {
        "embedding": EmbeddingUnavailableError,
        "retrieval": RetrievalUnavailableError,
        "llm": LLMUnavailableError,
    }
    methods = {
        "embedding": embedder.embed_query,
        "retrieval": retriever.search_similar,
        "llm": llm.generate,
    }
    methods[stage].side_effect = errors[stage]("private detail")
    with _client(monkeypatch, use_case) as client:
        response = client.post("/query", json={"question": "Requisitos"})
    assert response.status_code == 503
    assert "private detail" not in response.text
    repository.save_exchange.assert_not_awaited()


def test_unknown_conversation_is_404_before_rag(monkeypatch: MonkeyPatch) -> None:
    use_case, llm, embedder, _, repository = _rag()
    with _client(monkeypatch, use_case) as client:
        identifier = str(uuid4())
        assert (
            client.post(
                "/query", json={"question": "q", "conversation_id": identifier}
            ).status_code
            == 404
        )
        assert client.get(f"/conversations/{identifier}").status_code == 404
    embedder.embed_query.assert_not_awaited()
    llm.generate.assert_not_awaited()
    repository.save_exchange.assert_not_awaited()


def test_http_uuid_and_limit_validation(monkeypatch: MonkeyPatch) -> None:
    use_case, _, _, _, repository = _rag()
    with _client(monkeypatch, use_case) as client:
        assert (
            client.post(
                "/query", json={"question": "q", "conversation_id": "wrong"}
            ).status_code
            == 422
        )
        assert client.get("/conversations/wrong").status_code == 422
        assert client.get(f"/conversations/{uuid4()}?limit=101").status_code == 422
    repository.history.assert_not_awaited()
    repository.save_exchange.assert_not_awaited()


def test_storage_unavailability_returns_503_for_post_and_get(
    monkeypatch: MonkeyPatch,
) -> None:
    use_case, _, _, _, repository = _rag()
    repository.save_exchange.side_effect = ConversationUnavailableError(
        "private detail"
    )
    repository.history.side_effect = ConversationUnavailableError("private detail")
    with _client(monkeypatch, use_case) as client:
        for response in [
            client.post("/query", json={"question": "q"}),
            client.get(f"/conversations/{uuid4()}"),
        ]:
            assert response.status_code == 503
            assert "private detail" not in response.text


def test_openapi_requires_response_identifiers(monkeypatch: MonkeyPatch) -> None:
    use_case, _, _, _, _ = _rag()
    with _client(monkeypatch, use_case) as client:
        schema = client.get("/openapi.json").json()["components"]["schemas"][
            "QueryResponse"
        ]
    assert {"answer", "sources", "conversation_id", "message_id"} <= set(
        schema["required"]
    )
    for name in ("conversation_id", "message_id"):
        assert schema["properties"][name]["type"] == "string"
        assert schema["properties"][name]["format"] == "uuid"


@pytest.mark.parametrize(
    "identifiers", [{}, {"conversation_id": None, "message_id": None}]
)
def test_response_rejects_missing_or_null_identifiers(
    identifiers: dict[str, None],
) -> None:
    with pytest.raises(ValidationError):
        QueryResponse.model_validate(
            {"answer": "respuesta", "sources": [], **identifiers}
        )
