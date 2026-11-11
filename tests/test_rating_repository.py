from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from src.domain.exceptions import RatingAlreadyExistsError, RatingUnavailableError
from src.infrastructure.db.rating_repository import SqlAlchemyRatingRepository


def repository() -> tuple[SqlAlchemyRatingRepository, AsyncMock]:
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.begin = Mock(return_value=AsyncMock())
    return SqlAlchemyRatingRepository(Mock(return_value=session)), session


async def test_insert_never_updates_existing_rating() -> None:
    repo, session = repository()
    identifier = UUID(int=1)
    session.scalar.return_value = identifier
    await repo.save(identifier, 4)
    statement = session.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(statement)
    assert "ON CONFLICT (message_id) DO NOTHING" in sql
    assert "DO UPDATE" not in sql
    assert statement.params == {"message_id": identifier, "stars": 4}
    session.begin.return_value.__aexit__.assert_awaited_once()


async def test_conflict_is_reported_as_duplicate() -> None:
    repo, session = repository()
    session.scalar.return_value = None
    with pytest.raises(RatingAlreadyExistsError):
        await repo.save(UUID(int=1), 2)


@pytest.mark.parametrize("role", [None, "user", "assistant"])
async def test_message_lookup_is_scoped(role: str | None) -> None:
    repo, session = repository()
    session.scalar.return_value = role
    assert await repo.message_role(UUID(int=1)) == role
    statement = session.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "WHERE messages.id" in str(statement)
    assert UUID(int=1) in statement.params.values()


async def test_message_lookup_checks_authorized_conversation() -> None:
    repo, session = repository()
    session.scalar.return_value = None
    assert await repo.message_role(UUID(int=1), conversation_id=UUID(int=2)) is None
    statement = session.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "messages.conversation_id =" in str(statement)
    assert UUID(int=2) in statement.params.values()


@pytest.mark.parametrize("saving", [False, True])
async def test_connection_error_is_translated(saving: bool) -> None:
    repo, session = repository()
    session.scalar.side_effect = ConnectionRefusedError()
    with pytest.raises(RatingUnavailableError):
        if saving:
            await repo.save(UUID(int=1), 3)
        else:
            await repo.message_role(UUID(int=1))


async def test_unrelated_integrity_error_is_not_called_a_duplicate() -> None:
    repo, session = repository()
    session.scalar.side_effect = IntegrityError("INSERT", {}, Exception("constraint"))
    with pytest.raises(IntegrityError):
        await repo.save(UUID(int=1), 4)


async def test_unexpected_role_type_is_not_masked() -> None:
    repo, session = repository()
    session.scalar.return_value = 42
    with pytest.raises(TypeError, match="message role"):
        await repo.message_role(UUID(int=1))
