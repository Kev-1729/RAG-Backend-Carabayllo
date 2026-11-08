from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pytest import MonkeyPatch

from src.application.answer.submit_rating import SubmitRating
from src.domain.exceptions import RatingAlreadyExistsError, RatingUnavailableError
from src.domain.ports import RatingRepository
from tests.test_query_endpoint import _client, _rag


def test_http_rates_a_generated_answer_and_rejects_duplicate(
    monkeypatch: MonkeyPatch,
) -> None:
    conversation, llm, embedder, retriever, _ = _rag()
    repository = AsyncMock(spec=RatingRepository)
    repository.message_role.return_value = "assistant"
    repository.save.side_effect = [None, RatingAlreadyExistsError()]
    with _client(monkeypatch, conversation, SubmitRating(repository)) as client:
        answer = client.post("/query", json={"question": "Requisitos"}).json()
        identifier = answer["message_id"]
        calls = (
            llm.generate.await_count,
            embedder.embed_query.await_count,
            retriever.search_similar.await_count,
        )
        first = client.post(f"/messages/{identifier}/rating", json={"stars": 4})
        second = client.post(f"/messages/{identifier}/rating", json={"stars": 1})
    assert first.status_code == 201
    assert first.json() == {"message_id": identifier, "stars": 4}
    assert second.status_code == 409
    assert calls == (
        llm.generate.await_count,
        embedder.embed_query.await_count,
        retriever.search_similar.await_count,
    )
    repository.save.assert_any_await(UUID(identifier), 4)


@pytest.mark.parametrize("stars", [0, 6, True, "4", 4.5, None])
def test_invalid_stars_return_422_without_storage(
    monkeypatch: MonkeyPatch, stars: object
) -> None:
    conversation, _, _, _, _ = _rag()
    repository = AsyncMock(spec=RatingRepository)
    with _client(monkeypatch, conversation, SubmitRating(repository)) as client:
        assert (
            client.post(
                f"/messages/{UUID(int=1)}/rating", json={"stars": stars}
            ).status_code
            == 422
        )
        assert (
            client.post("/messages/wrong/rating", json={"stars": 4}).status_code == 422
        )
    repository.message_role.assert_not_awaited()
    repository.save.assert_not_awaited()


@pytest.mark.parametrize("role,status", [(None, 404), ("user", 422)])
def test_unknown_or_user_message_is_rejected(
    monkeypatch: MonkeyPatch, role: str | None, status: int
) -> None:
    conversation, _, _, _, _ = _rag()
    repository = AsyncMock(spec=RatingRepository)
    repository.message_role.return_value = role
    with _client(monkeypatch, conversation, SubmitRating(repository)) as client:
        assert (
            client.post(
                f"/messages/{UUID(int=1)}/rating", json={"stars": 4}
            ).status_code
            == status
        )
    repository.save.assert_not_awaited()


@pytest.mark.parametrize("stage", ["message_role", "save"])
def test_storage_error_is_503_without_internal_details(
    monkeypatch: MonkeyPatch, stage: str
) -> None:
    conversation, _, _, _, _ = _rag()
    repository = AsyncMock(spec=RatingRepository)
    repository.message_role.return_value = "assistant"
    getattr(repository, stage).side_effect = RatingUnavailableError("private detail")
    with _client(monkeypatch, conversation, SubmitRating(repository)) as client:
        response = client.post(f"/messages/{UUID(int=1)}/rating", json={"stars": 4})
    assert response.status_code == 503
    assert "private detail" not in response.text
