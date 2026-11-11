from time import time

from sqlalchemy import and_, case, delete, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import (
    InterfaceError,
    OperationalError,
    TimeoutError as SqlAlchemyTimeoutError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.exceptions import RequestLimitUnavailableError
from src.infrastructure.db.models import RequestLimitModel


class SqlAlchemyRequestLimiter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def allow(self, key: str, limit: int) -> bool:
        if limit <= 0:
            raise ValueError("limit must be positive")
        window = int(time()) // 60
        model = RequestLimitModel
        statement = (
            insert(model)
            .values(key=key, window_start=window, count=1)
            .on_conflict_do_update(
                index_elements=[model.key],
                set_={
                    "window_start": window,
                    "count": case(
                        (model.window_start == window, model.count + 1), else_=1
                    ),
                },
                where=or_(
                    model.window_start < window,
                    and_(model.window_start == window, model.count < limit),
                ),
            )
            .returning(model.count)
        )
        try:
            async with self._session_factory() as session, session.begin():
                await session.execute(
                    delete(model).where(model.window_start < window - 60)
                )
                count = await session.scalar(statement)
                return count is not None
        except (
            InterfaceError,
            OperationalError,
            SqlAlchemyTimeoutError,
            OSError,
            TimeoutError,
        ) as error:
            raise RequestLimitUnavailableError() from error
