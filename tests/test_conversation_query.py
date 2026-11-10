import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.application.answer.answer_query import ABSTENTION_MESSAGE, AnswerQuery
from src.application.answer.conversation_query import Answerer, ConversationQuery
from src.domain.entities import (
    Answer,
    AnswerReference,
    AnswerSource,
    ChatMessage,
    Generation,
    Query,
    RetrievedChunk,
)
from src.domain.exceptions import (
    ConversationNotFoundError,
    ConversationUnavailableError,
    LLMUnavailableError,
)
from src.domain.ports import LLM, ChunkRetriever, ConversationRepository, Embedder


async def test_new_conversation_saves_original_question_and_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([10.0, 10.125])
    monkeypatch.setattr(
        "src.application.answer.conversation_query.perf_counter", lambda: next(times)
    )
    answerer = AsyncMock(spec=Answerer)
    answerer.execute.return_value = Answer(
        "respuesta", model="model", input_tokens=100, output_tokens=20
    )
    repository = AsyncMock(spec=ConversationRepository)
    repository.save_exchange.return_value = (UUID(int=1), UUID(int=2))
    answer = await ConversationQuery(answerer, repository).execute(Query("pregunta"))
    assert answer.conversation_id == UUID(int=1)
    assert answer.message_id == UUID(int=2)
    repository.history.assert_not_awaited()
    repository.save_exchange.assert_awaited_once_with(
        None,
        "pregunta",
        Answer(
            "respuesta",
            model="model",
            input_tokens=100,
            output_tokens=20,
            latency_ms=125,
        ),
    )
    assert answer.latency_ms == 125


async def test_continuation_loads_only_selected_conversation() -> None:
    identifier = UUID(int=1)
    history = (
        ChatMessage(
            UUID(int=2), "user", "licencia de bodega", datetime.now(timezone.utc)
        ),
    )
    answerer = AsyncMock(spec=Answerer)
    answerer.execute.return_value = Answer("costo")
    repository = AsyncMock(spec=ConversationRepository)
    repository.history.return_value = history
    repository.save_exchange.return_value = (identifier, UUID(int=3))
    query = Query("¿y cuánto cuesta?", identifier)
    await ConversationQuery(answerer, repository).execute(query)
    repository.history.assert_awaited_once_with(identifier, limit=10)
    answerer.execute.assert_awaited_once_with(query, history=history)


async def test_unknown_conversation_does_not_call_providers() -> None:
    answerer = AsyncMock(spec=Answerer)
    repository = AsyncMock(spec=ConversationRepository)
    repository.history.side_effect = ConversationNotFoundError()
    with pytest.raises(ConversationNotFoundError):
        await ConversationQuery(answerer, repository).execute(Query("q", UUID(int=1)))
    answerer.execute.assert_not_awaited()
    repository.save_exchange.assert_not_awaited()


async def test_failed_answer_does_not_save_partial_turn() -> None:
    answerer = AsyncMock(spec=Answerer)
    answerer.execute.side_effect = LLMUnavailableError()
    repository = AsyncMock(spec=ConversationRepository)
    with pytest.raises(LLMUnavailableError):
        await ConversationQuery(answerer, repository).execute(Query("q"))
    repository.save_exchange.assert_not_awaited()


async def test_history_influences_retrieval_and_is_not_a_document_source() -> None:
    llm = AsyncMock(spec=LLM)
    llm.generate.return_value = Generation("El costo es el indicado [1].")
    embedder = AsyncMock(spec=Embedder)
    retriever = AsyncMock(spec=ChunkRetriever)
    retriever.search_similar.return_value = [
        RetrievedChunk(
            UUID(int=1), "Licencias", "a.pdf", 1, "Costo", 0.1, chunk_id=UUID(int=99)
        )
    ]
    history = (
        ChatMessage(
            UUID(int=3), "user", "Licencia de bodega", datetime.now(timezone.utc)
        ),
    )
    result = await AnswerQuery(llm, embedder, retriever, 0.5).execute(
        Query("¿y cuánto cuesta?"), history
    )
    embedder.embed_query.assert_awaited_once_with(
        "Licencia de bodega\n¿y cuánto cuesta?"
    )
    payload = json.loads(llm.generate.await_args.kwargs["prompt"])
    assert payload["history"] == [{"role": "user", "content": "Licencia de bodega"}]
    assert payload["question"] == "¿y cuánto cuesta?"
    assert len(result.sources) == 1


async def test_empty_generation_is_not_persisted() -> None:
    llm = AsyncMock(spec=LLM)
    llm.generate.return_value = Generation("  ")
    retriever = AsyncMock(spec=ChunkRetriever)
    retriever.search_similar.return_value = [
        RetrievedChunk(UUID(int=1), "A", "a.pdf", 1, "text", 0.1, chunk_id=UUID(int=99))
    ]
    answerer = AnswerQuery(llm, AsyncMock(spec=Embedder), retriever, 0.5)
    repository = AsyncMock(spec=ConversationRepository)
    with pytest.raises(LLMUnavailableError):
        await ConversationQuery(answerer, repository).execute(Query("q"))
    repository.save_exchange.assert_not_awaited()


async def test_stream_saves_completed_turn_with_history_references_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([10.0, 10.125])
    monkeypatch.setattr(
        "src.application.answer.conversation_query.perf_counter", lambda: next(times)
    )
    conversation_id, message_id = UUID(int=1), UUID(int=2)
    query = Query("pregunta", conversation_id)
    history = (
        ChatMessage(UUID(int=3), "user", "anterior", datetime.now(timezone.utc)),
    )
    final = Answer(
        "respuesta [1]",
        sources=(AnswerSource(UUID(int=4), "Licencias", 2),),
        references=(AnswerReference(UUID(int=5), 1, 0.8),),
        model="model",
        input_tokens=30,
        output_tokens=7,
    )
    answerer = AsyncMock(spec=Answerer)
    repository = AsyncMock(spec=ConversationRepository)
    repository.history.return_value = history
    repository.save_exchange.return_value = (conversation_id, message_id)

    async def events() -> AsyncGenerator[str | Answer, None]:
        yield final.text
        yield final
        repository.save_exchange.assert_not_awaited()

    answerer.stream.return_value = events()
    stream = ConversationQuery(answerer, repository).stream(query)
    assert await anext(stream) == final.text
    repository.save_exchange.assert_not_awaited()
    saved = replace(final, latency_ms=125)
    assert await anext(stream) == replace(
        saved, conversation_id=conversation_id, message_id=message_id
    )
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    repository.history.assert_awaited_once_with(conversation_id, limit=10)
    answerer.stream.assert_called_once_with(query, history=history)
    repository.save_exchange.assert_awaited_once_with(
        conversation_id, query.text, saved
    )


@pytest.mark.parametrize(
    "tail", [[], ["extra"], [Answer("duplicada")], [LLMUnavailableError()]]
)
async def test_invalid_stream_never_saves_turn(
    tail: list[str | Answer | Exception],
) -> None:
    answerer = AsyncMock(spec=Answerer)
    repository = AsyncMock(spec=ConversationRepository)

    async def events() -> AsyncGenerator[str | Answer, None]:
        yield "texto"
        if tail:
            yield Answer("texto")
        for event in tail:
            if isinstance(event, Exception):
                raise event
            yield event

    answerer.stream.return_value = events()
    stream = ConversationQuery(answerer, repository).stream(Query("q"))
    assert await anext(stream) == "texto"
    with pytest.raises(LLMUnavailableError):
        await anext(stream)
    repository.save_exchange.assert_not_awaited()


@pytest.mark.parametrize("cancel", [False, True])
async def test_interrupted_stream_closes_generation_without_saving(
    cancel: bool,
) -> None:
    answerer = AsyncMock(spec=Answerer)
    repository = AsyncMock(spec=ConversationRepository)
    waiting, closed = asyncio.Event(), asyncio.Event()

    async def events() -> AsyncGenerator[str | Answer, None]:
        try:
            yield "parcial"
            waiting.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    answerer.stream.return_value = events()
    stream = ConversationQuery(answerer, repository).stream(Query("q"))
    assert await anext(stream) == "parcial"
    if cancel:
        task = asyncio.create_task(anext(stream))
        await asyncio.wait_for(waiting.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await stream.aclose()
    assert closed.is_set()
    repository.save_exchange.assert_not_awaited()


async def test_stream_save_failure_propagates_without_emitting_final_answer() -> None:
    answerer = AsyncMock(spec=Answerer)
    repository = AsyncMock(spec=ConversationRepository)
    repository.save_exchange.side_effect = ConversationUnavailableError()

    async def events() -> AsyncGenerator[str | Answer, None]:
        yield "respuesta"
        yield Answer("respuesta")

    answerer.stream.return_value = events()
    stream = ConversationQuery(answerer, repository).stream(Query("q"))
    assert await anext(stream) == "respuesta"
    with pytest.raises(ConversationUnavailableError):
        await anext(stream)
    repository.history.assert_not_awaited()
    repository.save_exchange.assert_awaited_once()


async def test_stream_saves_abstention_in_new_conversation_without_llm_call() -> None:
    llm = AsyncMock(spec=LLM)
    retriever = AsyncMock(spec=ChunkRetriever)
    retriever.search_similar.return_value = []
    answerer = AnswerQuery(llm, AsyncMock(spec=Embedder), retriever, 0.5)
    repository = AsyncMock(spec=ConversationRepository)
    conversation_id, message_id = UUID(int=1), UUID(int=2)
    repository.save_exchange.return_value = (conversation_id, message_id)
    events = [
        event
        async for event in ConversationQuery(answerer, repository).stream(Query("q"))
    ]
    final = events[-1]
    assert isinstance(final, Answer)
    assert final.latency_ms is not None
    saved = Answer(
        ABSTENTION_MESSAGE, input_tokens=0, output_tokens=0, latency_ms=final.latency_ms
    )
    assert events == [
        ABSTENTION_MESSAGE,
        replace(saved, conversation_id=conversation_id, message_id=message_id),
    ]
    repository.save_exchange.assert_awaited_once_with(None, "q", saved)
    repository.history.assert_not_awaited()
    llm.stream.assert_not_called()
