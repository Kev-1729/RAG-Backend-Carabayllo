import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.application.answer.answer_query import ABSTENTION_MESSAGE, AnswerQuery
from src.domain.entities import Answer, ChatMessage, Generation, Query, RetrievedChunk
from src.domain.exceptions import LLMUnavailableError
from src.domain.ports import LLM, ChunkRetriever, Embedder


def setup_query(
    events: list[str | Generation | Exception], *, relevant: bool = True
) -> tuple[AnswerQuery, AsyncMock, AsyncMock, AsyncMock, list[bool]]:
    llm = AsyncMock(spec=LLM)
    embedder = AsyncMock(spec=Embedder)
    embedder.embed_query.return_value = (1.0,)
    retriever = AsyncMock(spec=ChunkRetriever)
    retriever.search_similar.return_value = (
        [
            RetrievedChunk(
                UUID(int=1), "A", "a.pdf", 2, "Texto", 0.2, chunk_id=UUID(int=2)
            )
        ]
        if relevant
        else []
    )
    closed: list[bool] = []

    async def stream(
        system: str, prompt: str
    ) -> AsyncGenerator[str | Generation, None]:
        try:
            for event in events:
                if isinstance(event, Exception):
                    raise event
                yield event
        finally:
            closed.append(True)

    llm.stream.side_effect = stream
    return AnswerQuery(llm, embedder, retriever, 0.5), llm, embedder, retriever, closed


async def test_stream_emits_text_before_final_answer_and_keeps_usage_and_references() -> (
    None
):
    generation = Generation("Uno dos", "actual-model", 30, 7)
    use_case, llm, _, _, closed = setup_query(["Uno ", "dos", generation])
    async with aclosing(use_case.stream(Query("q"))) as stream:
        assert await anext(stream) == "Uno "
        assert closed == []
        assert await anext(stream) == "dos"
        answer = await anext(stream)
        assert isinstance(answer, Answer)
        assert answer.text == "Uno dos"
        assert (answer.model, answer.input_tokens, answer.output_tokens) == (
            "actual-model",
            30,
            7,
        )
        assert [(s.document, s.page) for s in answer.sources] == [("A", 2)]
        assert [(r.chunk_id, r.rank, r.score) for r in answer.references] == [
            (UUID(int=2), 1, 0.8)
        ]
        assert closed == [True]
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
    llm.generate.assert_not_awaited()


async def test_stream_and_execute_use_identical_prompt_history_and_final_answer() -> (
    None
):
    generation = Generation("Respuesta [1].", "actual-model", 30, 7)
    use_case, llm, embedder, _, _ = setup_query([generation.text, generation])
    llm.generate.return_value = generation
    history = (
        ChatMessage(UUID(int=3), "user", "Anterior", datetime.now(timezone.utc)),
    )
    events = [event async for event in use_case.stream(Query("Actual"), history)]
    answer = await use_case.execute(Query("Actual"), history)
    assert events[-1] == answer
    assert llm.stream.call_args == llm.generate.call_args
    embedder.embed_query.assert_awaited_with("Anterior\nActual")
    payload = json.loads(llm.stream.call_args.kwargs["prompt"])
    assert payload["history"] == [{"role": "user", "content": "Anterior"}]


async def test_stream_abstains_without_calling_provider_when_context_is_missing() -> (
    None
):
    use_case, llm, _, _, _ = setup_query([], relevant=False)
    events = [event async for event in use_case.stream(Query("q"))]
    assert events == [
        ABSTENTION_MESSAGE,
        Answer(ABSTENTION_MESSAGE, input_tokens=0, output_tokens=0),
    ]
    llm.stream.assert_not_called()
    llm.generate.assert_not_awaited()


async def test_stream_model_abstention_keeps_usage_but_has_no_references() -> None:
    text = " " + ABSTENTION_MESSAGE + "\n"
    use_case, _, _, _, _ = setup_query(
        [text[:10], text[10:], Generation(text, "model", 20, 8)]
    )
    events = [event async for event in use_case.stream(Query("q"))]
    assert events[-1] == Answer(
        ABSTENTION_MESSAGE, model="model", input_tokens=20, output_tokens=8
    )


@pytest.mark.parametrize(
    "events",
    [
        [],
        ["Parcial"],
        [" ", Generation(" ")],
        ["Uno", Generation("Otro")],
        ["Uno", Generation("Uno"), "extra"],
        ["Uno", Generation("Uno"), Generation("Uno")],
        ["Uno", LLMUnavailableError()],
    ],
)
async def test_invalid_or_failed_stream_never_emits_final_answer(
    events: list[str | Generation | Exception],
) -> None:
    use_case, _, _, _, closed = setup_query(events)
    received: list[str | Answer] = []
    with pytest.raises(LLMUnavailableError):
        async for event in use_case.stream(Query("q")):
            received.append(event)
    assert not any(isinstance(event, Answer) for event in received)
    assert closed == [True]


async def test_early_close_closes_provider_without_completing_answer() -> None:
    use_case, _, _, _, closed = setup_query(["Uno", "Dos", Generation("UnoDos")])
    stream = use_case.stream(Query("q"))
    assert await anext(stream) == "Uno"
    await stream.aclose()
    assert closed == [True]


async def test_cancellation_while_waiting_for_text_closes_provider() -> None:
    use_case, llm, _, _, _ = setup_query([])
    waiting, closed = asyncio.Event(), asyncio.Event()

    async def blocked(
        system: str, prompt: str
    ) -> AsyncGenerator[str | Generation, None]:
        try:
            yield "Uno"
            waiting.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    llm.stream.side_effect = blocked
    stream = use_case.stream(Query("q"))
    assert await anext(stream) == "Uno"
    task = asyncio.create_task(anext(stream))
    await asyncio.wait_for(waiting.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.parametrize("stage", ["embedding", "retrieval"])
async def test_retrieval_failure_propagates_without_opening_provider(
    stage: str,
) -> None:
    from src.domain.exceptions import (
        EmbeddingUnavailableError,
        RetrievalUnavailableError,
    )

    use_case, llm, embedder, retriever, _ = setup_query([])
    error = (
        EmbeddingUnavailableError()
        if stage == "embedding"
        else RetrievalUnavailableError()
    )
    method = embedder.embed_query if stage == "embedding" else retriever.search_similar
    method.side_effect = error
    with pytest.raises(type(error)):
        _ = [event async for event in use_case.stream(Query("q"))]
    llm.stream.assert_not_called()
