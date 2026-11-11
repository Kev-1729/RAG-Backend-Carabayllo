import asyncio
import json
from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from fastapi import FastAPI
from starlette.types import Message, Scope

from src.container.security import get_conversation_tokens
from src.domain.entities import Generation
from src.domain.exceptions import (
    ConversationUnavailableError,
    EmbeddingUnavailableError,
    LLMUnavailableError,
)
from src.infrastructure.conversation_tokens import HmacConversationTokens
from src.interfaces.dependencies.security import enforce_request_limit
from src.interfaces.routers.query import router
from tests.test_query_endpoint import TEST_ACCESS_SECRET, _client, _rag, token_headers


def parse_events(body: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for frame in body.strip().split("\n\n"):
        event, data = frame.splitlines()
        assert event.startswith("event: ") and data.startswith("data: ")
        events.append(
            (event.removeprefix("event: "), json.loads(data.removeprefix("data: ")))
        )
    return events


def test_stream_returns_text_then_saved_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    use_case, llm, _, _, repository = _rag()
    first = "Presenta el formulario\nevent: ejemplo"
    second = " [1]."

    async def stream(
        system: str, prompt: str
    ) -> AsyncGenerator[str | Generation, None]:
        yield first
        repository.save_exchange.assert_not_awaited()
        yield second
        yield Generation(first + second, "test-model", 12, 5)

    llm.stream.side_effect = stream
    with _client(monkeypatch, use_case) as client:
        response = client.post("/query/stream", json={"question": "  Requisitos  "})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"
        events = parse_events(response.text)
        assert events[:2] == [("delta", {"text": first}), ("delta", {"text": second})]
        assert len(events) == 3
        name, final = events[2]
        assert name == "complete"
        assert final["answer"] == first + second
        assert final["sources"] == [{"document": "Licencias", "page": 2}]
        history = client.get(
            f"/conversations/{final['conversation_id']}",
            headers=token_headers(str(final["conversation_id"])),
        )
        assert history.status_code == 200
        messages = history.json()
        assert messages[0]["content"] == "Requisitos"
        assert messages[1]["id"] == final["message_id"]
        assert messages[1]["content"] == final["answer"]
        schema = client.get("/openapi.json").json()
        assert (
            "text/event-stream"
            in schema["paths"]["/query/stream"]["post"]["responses"]["200"]["content"]
        )
    repository.save_exchange.assert_awaited_once()
    llm.generate.assert_not_awaited()


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"question": "  "}, 422),
        ({"question": "q", "conversation_id": "invalid"}, 422),
        ({"question": "q", "conversation_id": str(UUID(int=1))}, 404),
        ({"question": "q"}, 503),
    ],
)
def test_stream_returns_http_errors_before_first_event(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, str], status: int
) -> None:
    use_case, llm, embedder, _, repository = _rag()
    embedder.embed_query.side_effect = EmbeddingUnavailableError("private detail")
    with _client(monkeypatch, use_case) as client:
        response = client.post("/query/stream", json=body)
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/json")
    assert "private detail" not in response.text
    llm.stream.assert_not_called()
    repository.save_exchange.assert_not_awaited()
    if status != 503:
        embedder.embed_query.assert_not_awaited()


@pytest.mark.parametrize("failure", ["generation", "storage", "unexpected"])
def test_error_after_text_uses_terminal_sse_event(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    use_case, llm, _, _, repository = _rag()

    async def stream(
        system: str, prompt: str
    ) -> AsyncGenerator[str | Generation, None]:
        yield "parcial"
        if failure == "generation":
            raise LLMUnavailableError("private detail")
        if failure == "unexpected":
            raise RuntimeError("private detail")
        yield Generation("parcial")

    llm.stream.side_effect = stream
    repository.save_exchange.side_effect = ConversationUnavailableError(
        "private detail"
    )
    with _client(monkeypatch, use_case) as client:
        response = client.post("/query/stream", json={"question": "q"})
    assert response.status_code == 200
    events = parse_events(response.text)
    assert [name for name, _ in events] == ["delta", "error"]
    expected = "internal_error" if failure == "unexpected" else "service_unavailable"
    assert events[-1][1]["code"] == expected
    assert "private detail" not in response.text
    if failure == "storage":
        repository.save_exchange.assert_awaited_once()
    else:
        repository.save_exchange.assert_not_awaited()


@pytest.mark.parametrize("mode", ["before_delta", "after_delta", "send_error"])
async def test_disconnection_releases_provider_without_saving(mode: str) -> None:
    use_case, llm, _, _, repository = _rag()
    waiting, closed = asyncio.Event(), asyncio.Event()

    async def stream(
        system: str, prompt: str
    ) -> AsyncGenerator[str | Generation, None]:
        try:
            if mode != "before_delta":
                yield "parcial"
            waiting.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            closed.set()

    llm.stream.side_effect = stream
    app = FastAPI()
    app.dependency_overrides[enforce_request_limit] = lambda: None
    app.dependency_overrides[get_conversation_tokens] = lambda: HmacConversationTokens(
        TEST_ACCESS_SECRET
    )
    app.include_router(router)
    app.state.conversation_query = use_case
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/query/stream",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
    }
    request_sent = False
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {
                "type": "http.request",
                "body": b'{"question":"q"}',
                "more_body": False,
            }
        await waiting.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if mode == "send_error" and message["type"] == "http.response.body":
            raise OSError("connection closed")
        sent.append(message)

    await asyncio.wait_for(app(scope, receive, send), timeout=5)
    assert closed.is_set()
    assert all(b"event: complete" not in message.get("body", b"") for message in sent)
    if mode == "before_delta":
        assert sent == []
    elif mode == "after_delta":
        assert any(b"event: delta" in message.get("body", b"") for message in sent)
    repository.save_exchange.assert_not_awaited()
