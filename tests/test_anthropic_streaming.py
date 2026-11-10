import asyncio
import json
from collections.abc import AsyncIterator
from unittest.mock import Mock

import anthropic
import httpx2 as httpx
import pytest

from src.domain.entities import Generation
from src.domain.exceptions import LLMUnavailableError
from src.infrastructure.llm.anthropic_llm import AnthropicLLM


def events(
    *, stop_reason: str = "end_turn", initial_text: str = ""
) -> list[dict[str, object]]:
    return [
        {
            "type": "message_start",
            "message": {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "actual-model",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 30, "output_tokens": 0},
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": initial_text},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Uno "},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "dos"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 7},
        },
        {"type": "message_stop"},
    ]


class Body(httpx.AsyncByteStream):
    def __init__(self, data: list[dict[str, object]], *, block: bool = False) -> None:
        self.data = data
        self.closed = False
        self.read = 0
        self.block = block
        self.waiting = asyncio.Event()
        self.error: Exception | None = None

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for item in self.data:
            self.read += 1
            yield f"event: {item['type']}\ndata: {json.dumps(item)}\n\n".encode()
        if self.block:
            self.waiting.set()
            await asyncio.Event().wait()
        if self.error is not None:
            raise self.error

    async def aclose(self) -> None:
        self.closed = True


def adapter(
    monkeypatch: pytest.MonkeyPatch,
    data: list[dict[str, object]],
    *,
    block: bool = False,
) -> tuple[AnthropicLLM, Body, list[httpx.Request]]:
    body = Body(data, block=block)
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=body
        )

    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    monkeypatch.setattr(anthropic, "AsyncAnthropic", Mock(return_value=client))
    return AnthropicLLM("test-key", "configured-model"), body, requests


async def test_sdk_stream_is_incremental_and_reports_final_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, body, requests = adapter(monkeypatch, events())
    try:
        stream = llm.stream("system", "question")
        assert await anext(stream) == "Uno "
        assert body.read < len(body.data)
        assert not body.closed
        assert [event async for event in stream] == [
            "dos",
            Generation("Uno dos", "actual-model", 30, 7),
        ]
        assert body.closed
        payload = json.loads(requests[0].content)
        assert payload["stream"] is True
        assert payload["model"] == "configured-model"
        assert payload["system"] == "system"
        assert payload["messages"] == [{"role": "user", "content": "question"}]
    finally:
        await llm.aclose()


async def test_initial_block_text_is_streamed_without_normalizing_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix = "  Inicio:\n"
    llm, _, _ = adapter(monkeypatch, events(initial_text=prefix))
    try:
        assert [event async for event in llm.stream("system", "question")] == [
            prefix,
            "Uno ",
            "dos",
            Generation(prefix + "Uno dos", "actual-model", 30, 7),
        ]
    finally:
        await llm.aclose()


@pytest.mark.parametrize("mode", ["truncated", "max_tokens", "provider_error"])
async def test_failed_or_truncated_sdk_stream_has_no_final_generation(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    data = events(stop_reason="max_tokens" if mode == "max_tokens" else "end_turn")
    if mode == "truncated":
        data = data[:-1]
    elif mode == "provider_error":
        data = [
            *data[:3],
            {
                "type": "error",
                "error": {"type": "overloaded_error", "message": "private detail"},
            },
        ]
    llm, body, _ = adapter(monkeypatch, data)
    received: list[str | Generation] = []
    try:
        with pytest.raises(LLMUnavailableError):
            async for event in llm.stream("system", "question"):
                received.append(event)
        assert not any(isinstance(event, Generation) for event in received)
        assert body.closed
    finally:
        await llm.aclose()


@pytest.mark.parametrize("status", [401, 429, 500])
async def test_http_errors_are_translated_before_any_generation(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "type": "error",
                "error": {"type": "api_error", "message": "private detail"},
            },
        )

    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    monkeypatch.setattr(anthropic, "AsyncAnthropic", Mock(return_value=client))
    llm = AnthropicLLM("test-key", "model")
    try:
        with pytest.raises(LLMUnavailableError):
            _ = [event async for event in llm.stream("system", "question")]
    finally:
        await llm.aclose()


async def test_closing_generator_releases_sdk_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, body, _ = adapter(monkeypatch, events())
    try:
        stream = llm.stream("system", "question")
        assert await anext(stream) == "Uno "
        await stream.aclose()
        assert body.closed
    finally:
        await llm.aclose()


async def test_network_failure_during_read_closes_response_without_final_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, body, _ = adapter(monkeypatch, events()[:3])
    body.error = httpx.ReadError("connection interrupted")
    try:
        stream = llm.stream("system", "question")
        assert await anext(stream) == "Uno "
        with pytest.raises(LLMUnavailableError):
            await anext(stream)
        assert body.closed
    finally:
        await llm.aclose()


async def test_cancelling_read_closes_sdk_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, body, _ = adapter(monkeypatch, events()[:3], block=True)
    try:
        stream = llm.stream("system", "question")
        assert await anext(stream) == "Uno "
        task = asyncio.create_task(anext(stream))
        await asyncio.wait_for(body.waiting.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert body.closed
    finally:
        await llm.aclose()
