from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import (
    InterfaceError,
    OperationalError,
    TimeoutError as SqlAlchemyTimeoutError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.exceptions import RatingAlreadyExistsError, RatingUnavailableError
from src.infrastructure.db.models import MessageModel, RatingModel

_UNAVAILABLE = (
    OperationalError,
    InterfaceError,
    SqlAlchemyTimeoutError,
    OSError,
    TimeoutError,
)


class SqlAlchemyRatingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def message_role(
        self, message_id: UUID, *, conversation_id: UUID | None = None
    ) -> str | None:
        statement = select(MessageModel.role).where(MessageModel.id == message_id)
        if conversation_id is not None:
            statement = statement.where(MessageModel.conversation_id == conversation_id)
        try:
            async with self._session_factory() as session:
                role: object = await session.scalar(statement)
                if role is not None and not isinstance(role, str):
                    raise TypeError("Expected a string message role or None")
                return role
        except _UNAVAILABLE as error:
            raise RatingUnavailableError() from error

    async def save(self, message_id: UUID, stars: int) -> None:
        statement = (
            insert(RatingModel)
            .values(message_id=message_id, stars=stars)
            .on_conflict_do_nothing(index_elements=[RatingModel.message_id])
            .returning(RatingModel.message_id)
        )
        try:
            async with self._session_factory() as session, session.begin():
                if await session.scalar(statement) is None:
                    raise RatingAlreadyExistsError()
        except _UNAVAILABLE as error:
            raise RatingUnavailableError() from error
