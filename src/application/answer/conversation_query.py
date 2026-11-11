from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import replace
from time import perf_counter
from typing import Protocol
from uuid import UUID

from src.domain.entities import Answer, ChatMessage, Query
from src.domain.exceptions import LLMUnavailableError
from src.domain.ports import ConversationRepository


class Answerer(Protocol):
    async def execute(
        self, query: Query, history: tuple[ChatMessage, ...] = ()
    ) -> Answer: ...

    def stream(
        self, query: Query, history: tuple[ChatMessage, ...] = ()
    ) -> AsyncGenerator[str | Answer, None]: ...


class ConversationQuery:
    def __init__(
        self, answer_query: Answerer, repository: ConversationRepository
    ) -> None:
        self._answer_query = answer_query
        self._repository = repository

    async def execute(self, query: Query) -> Answer:
        started = perf_counter()
        history = await self._query_history(query)
        answer = await self._answer_query.execute(query, history=history)
        return await self._save_answer(query, answer, started)

    async def stream(self, query: Query) -> AsyncGenerator[str | Answer, None]:
        """Emite texto y devuelve la respuesta final una vez guardado el turno."""
        started = perf_counter()
        history = await self._query_history(query)
        answer = None
        async with aclosing(
            self._answer_query.stream(query, history=history)
        ) as stream:
            async for event in stream:
                if answer is not None:
                    raise LLMUnavailableError()
                if isinstance(event, str):
                    yield event
                else:
                    answer = event
        if answer is None:
            raise LLMUnavailableError()
        yield await self._save_answer(query, answer, started)

    async def _query_history(self, query: Query) -> tuple[ChatMessage, ...]:
        return (
            await self._repository.history(query.conversation_id, limit=10)
            if query.conversation_id
            else ()
        )

    async def _save_answer(
        self, query: Query, answer: Answer, started: float
    ) -> Answer:
        answer = replace(
            answer, latency_ms=max(0, round((perf_counter() - started) * 1000))
        )
        conversation_id, message_id = await self._repository.save_exchange(
            query.conversation_id, query.text, answer
        )
        return replace(answer, conversation_id=conversation_id, message_id=message_id)

    async def history(
        self, conversation_id: UUID, limit: int
    ) -> tuple[ChatMessage, ...]:
        return await self._repository.history(conversation_id, limit)
