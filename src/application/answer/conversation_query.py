from dataclasses import replace
from typing import Protocol
from uuid import UUID

from src.domain.entities import Answer, ChatMessage, Query
from src.domain.ports import ConversationRepository


class Answerer(Protocol):
    async def execute(
        self, query: Query, history: tuple[ChatMessage, ...] = ()
    ) -> Answer: ...


class ConversationQuery:
    def __init__(
        self, answer_query: Answerer, repository: ConversationRepository
    ) -> None:
        self._answer_query = answer_query
        self._repository = repository

    async def execute(self, query: Query) -> Answer:
        history = (
            await self._repository.history(query.conversation_id, limit=10)
            if query.conversation_id
            else ()
        )
        answer = await self._answer_query.execute(query, history=history)
        conversation_id, message_id = await self._repository.save_exchange(
            query.conversation_id, query.text, answer.text
        )
        return replace(answer, conversation_id=conversation_id, message_id=message_id)

    async def history(
        self, conversation_id: UUID, limit: int
    ) -> tuple[ChatMessage, ...]:
        return await self._repository.history(conversation_id, limit)
