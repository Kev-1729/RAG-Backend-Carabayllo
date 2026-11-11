import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql

from src.application.answer.submit_rating import SubmitRating
from src.domain.exceptions import (
    InvalidConversationTokenError,
    RequestLimitUnavailableError,
)
from src.domain.ports import RatingRepository
from src.infrastructure.conversation_tokens import HmacConversationTokens
from src.infrastructure.db.request_limiter import SqlAlchemyRequestLimiter
from src.interfaces.request_limits import RequestBodyLimit
from tests.test_query_endpoint import TEST_ACCESS_SECRET, _client, _rag, token_headers


@pytest.mark.parametrize(
    "value", ["", "invalid", "é", "x" * 102, str(UUID(int=1)) + ".bad"]
)
def test_invalid_access_tokens_are_rejected(value: str) -> None:
    with pytest.raises(InvalidConversationTokenError):
        HmacConversationTokens(TEST_ACCESS_SECRET).verify(value)


def test_tokens_bind_conversation_and_secret_and_separate_request_keys() -> None:
    tokens = HmacConversationTokens(TEST_ACCESS_SECRET)
    first = tokens.issue(UUID(int=1))
    assert tokens.verify(first) == UUID(int=1)
    assert first != tokens.issue(UUID(int=2))
    with pytest.raises(InvalidConversationTokenError):
        HmacConversationTokens("different-secret-with-32-characters").verify(first)
    with pytest.raises(InvalidConversationTokenError):
        tokens.verify(first.replace(str(UUID(int=1)), str(UUID(int=2))))
    assert tokens.request_key("client", "queries") != tokens.request_key(
        "client", "requests"
    )


def test_queries_and_history_require_matching_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, _, embedder, _, repository = _rag()
    with _client(monkeypatch, use_case) as client:
        result = client.post("/query", json={"question": "q"}).json()
        identifier = result["conversation_id"]
        assert HmacConversationTokens(TEST_ACCESS_SECRET).verify(
            result["conversation_token"]
        ) == UUID(identifier)
        embedder.embed_query.reset_mock()
        repository.history.reset_mock()
        for headers in [{"X-Conversation-Token": ""}, token_headers(UUID(int=99))]:
            for path in ["/query", "/query/stream"]:
                response = client.post(
                    path,
                    json={"question": "q", "conversation_id": identifier},
                    headers=headers,
                )
                assert response.status_code == 403
            assert (
                client.get(f"/conversations/{identifier}", headers=headers).status_code
                == 403
            )
        embedder.embed_query.assert_not_awaited()
        repository.history.assert_not_awaited()
        assert (
            client.get(
                f"/conversations/{identifier}",
                headers={"X-Conversation-Token": result["conversation_token"]},
            ).status_code
            == 200
        )


def test_rating_requires_token_before_message_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, _, _, _, _ = _rag()
    repository = AsyncMock(spec=RatingRepository)
    with _client(monkeypatch, use_case, SubmitRating(repository)) as client:
        assert (
            client.post(
                f"/messages/{UUID(int=1)}/rating",
                json={"stars": 4},
                headers={"X-Conversation-Token": ""},
            ).status_code
            == 403
        )
        repository.message_role.assert_not_awaited()


def test_rate_limit_rejects_before_providers_and_ignores_forwarded_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, _, embedder, _, _ = _rag()
    with _client(monkeypatch, use_case) as client:
        assert isinstance(client.app, FastAPI)
        limiter = client.app.state.request_limiter
        limiter.allow.return_value = False
        for address in ["192.0.2.1", "192.0.2.2"]:
            response = client.post(
                "/query", json={"question": "q"}, headers={"X-Forwarded-For": address}
            )
            assert response.status_code == 429
            assert response.headers["retry-after"] == "60"
        assert limiter.allow.await_args_list[0] == limiter.allow.await_args_list[1]
        assert len(limiter.allow.await_args.args[0]) == 64
    embedder.embed_query.assert_not_awaited()


def test_rate_storage_failure_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    use_case, _, embedder, _, _ = _rag()
    with _client(monkeypatch, use_case) as client:
        assert isinstance(client.app, FastAPI)
        client.app.state.request_limiter.allow.side_effect = (
            RequestLimitUnavailableError("private detail")
        )
        response = client.post("/query", json={"question": "q"})
    assert response.status_code == 503
    assert "private detail" not in response.text
    embedder.embed_query.assert_not_awaited()


def test_oversized_body_rejected_before_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, _, embedder, _, _ = _rag()
    with _client(monkeypatch, use_case) as client:
        assert isinstance(client.app, FastAPI)
        response = client.post(
            "/query", json={"question": "x" * 20000}, headers={"Content-Length": "1"}
        )
        assert response.status_code == 413
        client.app.state.request_limiter.allow.assert_not_awaited()
    embedder.embed_query.assert_not_awaited()


async def test_slow_body_times_out_before_app() -> None:
    app = AsyncMock()
    middleware = RequestBodyLimit(app, max_bytes=100, timeout=0.01)
    receive = AsyncMock(side_effect=asyncio.Event().wait)
    send = AsyncMock()
    await middleware({"type": "http", "method": "POST"}, receive, send)
    assert send.await_args_list[0].args[0]["status"] == 408
    app.assert_not_awaited()


@pytest.mark.parametrize("allowed", [True, False])
async def test_limiter_uses_atomic_postgres_upsert(allowed: bool) -> None:
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.begin = Mock(return_value=AsyncMock())
    session.scalar.return_value = 1 if allowed else None
    limiter = SqlAlchemyRequestLimiter(Mock(return_value=session))
    assert await limiter.allow("a" * 64, 10) is allowed
    sql = str(session.scalar.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in sql and "WHERE" in sql and "RETURNING" in sql
    assert "request_limits.count <" in sql
    session.begin.return_value.__aexit__.assert_awaited_once_with(None, None, None)
