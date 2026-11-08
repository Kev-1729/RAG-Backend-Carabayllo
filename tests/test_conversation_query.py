import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.application.answer.answer_query import AnswerQuery
from src.application.answer.conversation_query import Answerer, ConversationQuery
from src.domain.entities import Answer, ChatMessage, Query, RetrievedChunk
from src.domain.exceptions import ConversationNotFoundError, LLMUnavailableError
from src.domain.ports import LLM, ChunkRetriever, ConversationRepository, Embedder


async def test_new_conversation_saves_original_question_and_answer() -> None:
    answerer = AsyncMock(spec=Answerer)
    answerer.execute.return_value = Answer("respuesta")
    repository = AsyncMock(spec=ConversationRepository)
    repository.save_exchange.return_value = (UUID(int=1), UUID(int=2))
    answer = await ConversationQuery(answerer, repository).execute(Query("pregunta"))
    assert answer.conversation_id == UUID(int=1)
    assert answer.message_id == UUID(int=2)
    repository.history.assert_not_awaited()
    repository.save_exchange.assert_awaited_once_with(None, "pregunta", "respuesta")


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
    llm.generate.return_value = "El costo es el indicado [1]."
    embedder = AsyncMock(spec=Embedder)
    retriever = AsyncMock(spec=ChunkRetriever)
    retriever.search_similar.return_value = [
        RetrievedChunk(UUID(int=1), "Licencias", "a.pdf", 1, "Costo", 0.1)
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
    llm.generate.return_value = "  "
    retriever = AsyncMock(spec=ChunkRetriever)
    retriever.search_similar.return_value = [
        RetrievedChunk(UUID(int=1), "A", "a.pdf", 1, "text", 0.1)
    ]
    answerer = AnswerQuery(llm, AsyncMock(spec=Embedder), retriever, 0.5)
    repository = AsyncMock(spec=ConversationRepository)
    with pytest.raises(LLMUnavailableError):
        await ConversationQuery(answerer, repository).execute(Query("q"))
    repository.save_exchange.assert_not_awaited()
