from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pytest import MonkeyPatch

from src import config
from src.application.answer.answer_query import ABSTENTION_MESSAGE, AnswerQuery
from src.domain.entities import Answer, Query, RetrievedChunk
from src.domain.exceptions import (
    EmbeddingUnavailableError,
    LLMUnavailableError,
    RetrievalUnavailableError,
)
from src.domain.ports import LLM, ChunkRetriever, Embedder


class SpyAnswerQuery:
    def __init__(self) -> None:
        self.questions: list[Query] = []

    async def execute(self, query: Query) -> Answer:
        self.questions.append(query)
        return Answer(text="respuesta de prueba")


def _client(monkeypatch: MonkeyPatch, spy: SpyAnswerQuery | AnswerQuery) -> TestClient:
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
    async def fake_resources() -> AsyncIterator[SpyAnswerQuery | AnswerQuery]:
        yield spy

    monkeypatch.setattr(main, "answer_query_resources", fake_resources)
    application = main.create_application()
    return TestClient(application)


@pytest.mark.parametrize("question", ["", "   ", "\t\n\r", "\u00a0"])
def test_blank_question_returns_422_without_running_use_case(
    monkeypatch: MonkeyPatch,
    question: str,
) -> None:
    spy = SpyAnswerQuery()
    with _client(monkeypatch, spy) as client:
        response = client.post("/query", json={"question": question})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "question"]
    assert spy.questions == []


def test_question_is_trimmed_before_running_use_case(monkeypatch: MonkeyPatch) -> None:
    spy = SpyAnswerQuery()
    with _client(monkeypatch, spy) as client:
        response = client.post(
            "/query", json={"question": "  Requisitos de licencia? \n"}
        )

    assert response.status_code == 200
    assert response.json() == {"answer": "respuesta de prueba", "sources": []}
    assert spy.questions == [Query(text="Requisitos de licencia?")]


def _rag() -> tuple[AnswerQuery, AsyncMock, AsyncMock, AsyncMock]:
    llm = AsyncMock(spec=LLM)
    llm.generate.return_value = "Presenta el formulario [1]."
    embedder = AsyncMock(spec=Embedder)
    embedder.embed_query.return_value = (1.0, 0.0)
    retriever = AsyncMock(spec=ChunkRetriever)
    retriever.search_similar.return_value = [
        RetrievedChunk(UUID(int=1), "Licencias", "licencias.pdf", 2, "Formulario", 0.1),
        RetrievedChunk(UUID(int=1), "Licencias", "licencias.pdf", 2, "Anexo", 0.2),
    ]
    return AnswerQuery(llm, embedder, retriever, 0.5), llm, embedder, retriever


def test_http_rag_returns_sources_and_reuses_use_case(monkeypatch: MonkeyPatch) -> None:
    use_case, _, embedder, retriever = _rag()
    client = _client(monkeypatch, use_case)
    with client:
        for _ in range(2):
            response = client.post("/query", json={"question": "Requisitos"})
            assert response.status_code == 200
            assert response.json() == {
                "answer": "Presenta el formulario [1].",
                "sources": [{"document": "Licencias", "page": 2}],
            }
    assert embedder.embed_query.await_count == 2
    assert retriever.search_similar.await_count == 2
    assert isinstance(client.app, FastAPI)
    assert not hasattr(client.app.state, "answer_query")


def test_http_abstention_skips_llm(monkeypatch: MonkeyPatch) -> None:
    use_case, llm, _, retriever = _rag()
    retriever.search_similar.return_value = []
    with _client(monkeypatch, use_case) as client:
        response = client.post("/query", json={"question": "Requisitos"})
    assert response.status_code == 200
    assert response.json() == {"answer": ABSTENTION_MESSAGE, "sources": []}
    llm.generate.assert_not_awaited()


@pytest.mark.parametrize("stage", ["embedding", "retrieval", "llm"])
def test_http_provider_errors_return_503_without_internal_details(
    monkeypatch: MonkeyPatch,
    stage: str,
) -> None:
    use_case, llm, embedder, retriever = _rag()
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
    methods[stage].side_effect = errors[stage]("private provider error")
    with _client(monkeypatch, use_case) as client:
        response = client.post("/query", json={"question": "Requisitos"})
    assert response.status_code == 503
    assert response.json() == {
        "detail": "El asistente no está disponible. Intenta en unos minutos."
    }


def test_http_blank_question_never_calls_providers(monkeypatch: MonkeyPatch) -> None:
    use_case, llm, embedder, retriever = _rag()
    with _client(monkeypatch, use_case) as client:
        response = client.post("/query", json={"question": " \t "})
    assert response.status_code == 422
    embedder.embed_query.assert_not_awaited()
    retriever.search_similar.assert_not_awaited()
    llm.generate.assert_not_awaited()
