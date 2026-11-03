import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pytest import MonkeyPatch

from src import config
from src.domain.entities import Answer, Query
from src.interfaces.dependencies.answer import get_answer_query


class SpyAnswerQuery:
    def __init__(self) -> None:
        self.questions: list[Query] = []

    async def execute(self, query: Query) -> Answer:
        self.questions.append(query)
        return Answer(text="respuesta de prueba")


def _client(monkeypatch: MonkeyPatch, spy: SpyAnswerQuery) -> TestClient:
    settings = config.Settings(
        _env_file=None,  # type: ignore[call-arg]
        anthropic_api_key=SecretStr("test"),
        llm_model="test-model",
        database_url=SecretStr("postgresql+asyncpg://test:test@localhost/test"),
        voyage_api_key=SecretStr("test"),
        cors_allow_origins="",
        embedding_model="test-model",
        chunk_size=1000,
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)

    from src import main

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    application = main.create_application()
    application.dependency_overrides[get_answer_query] = lambda: spy
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
    assert response.json() == {"answer": "respuesta de prueba"}
    assert spy.questions == [Query(text="Requisitos de licencia?")]
