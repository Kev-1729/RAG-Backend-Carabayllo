from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import (
    InterfaceError,
    OperationalError,
    TimeoutError as SqlAlchemyTimeoutError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.entities import Answer, ChatMessage
from src.domain.exceptions import (
    ConversationNotFoundError,
    ConversationUnavailableError,
)
from src.infrastructure.db.models import ConversationModel, MessageModel

_UNAVAILABLE = (
    OperationalError,
    InterfaceError,
    SqlAlchemyTimeoutError,
    OSError,
    TimeoutError,
)


class SqlAlchemyConversationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def history(
        self, conversation_id: UUID, limit: int
    ) -> tuple[ChatMessage, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        try:
            async with self._session_factory() as session:
                if await session.get(ConversationModel, conversation_id) is None:
                    raise ConversationNotFoundError()
                messages = (
                    await session.scalars(
                        select(MessageModel)
                        .where(MessageModel.conversation_id == conversation_id)
                        .order_by(
                            MessageModel.created_at.desc(), MessageModel.id.desc()
                        )
                        .limit(limit)
                    )
                ).all()
                return tuple(
                    ChatMessage(m.id, m.role, m.content, m.created_at)
                    for m in reversed(messages)
                )
        except _UNAVAILABLE as error:
            raise ConversationUnavailableError() from error

    async def save_exchange(
        self, conversation_id: UUID | None, question: str, answer: Answer
    ) -> tuple[UUID, UUID]:
        try:
            async with self._session_factory() as session, session.begin():
                if conversation_id is None:
                    conversation_id = uuid4()
                    session.add(ConversationModel(id=conversation_id))
                    await session.flush()
                elif await session.get(ConversationModel, conversation_id) is None:
                    raise ConversationNotFoundError()
                now = datetime.now(timezone.utc)
                answer_id = uuid4()
                session.add_all(
                    [
                        MessageModel(
                            id=uuid4(),
                            conversation_id=conversation_id,
                            role="user",
                            content=question,
                            created_at=now,
                        ),
                        MessageModel(
                            id=answer_id,
                            conversation_id=conversation_id,
                            role="assistant",
                            content=answer.text,
                            model=answer.model,
                            input_tokens=answer.input_tokens,
                            output_tokens=answer.output_tokens,
                            latency_ms=answer.latency_ms,
                            created_at=now + timedelta(microseconds=1),
                        ),
                    ]
                )
            return conversation_id, answer_id
        except _UNAVAILABLE as error:
            raise ConversationUnavailableError() from error
