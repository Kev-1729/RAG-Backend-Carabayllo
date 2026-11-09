from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from src.domain.entities import Answer
from src.domain.exceptions import (
    ConversationNotFoundError,
    ConversationUnavailableError,
)
from src.infrastructure.db.conversation_repository import (
    SqlAlchemyConversationRepository,
)
from src.infrastructure.db.models import ConversationModel


def repository() -> tuple[SqlAlchemyConversationRepository, AsyncMock]:
    session = AsyncMock()
    session.__aenter__.return_value = session
    transaction = AsyncMock()
    session.begin = Mock(return_value=transaction)
    session.add = Mock()
    session.add_all = Mock()
    return SqlAlchemyConversationRepository(Mock(return_value=session)), session


async def test_history_is_scoped_limited_and_chronological() -> None:
    repo, session = repository()
    session.get.return_value = object()
    now = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(id=UUID(int=i), role=role, content=role, created_at=now)
        for i, role in [(2, "assistant"), (1, "user")]
    ]
    session.scalars.return_value = Mock(all=Mock(return_value=rows))
    result = await repo.history(UUID(int=3), 10)
    assert [m.role for m in result] == ["user", "assistant"]
    statement = session.scalars.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "WHERE messages.conversation_id" in str(statement)
    assert "ORDER BY messages.created_at DESC" in str(statement)
    assert 10 in statement.params.values()


@pytest.mark.parametrize("existing", [False, True])
async def test_exchange_is_saved_in_one_transaction_with_ordered_roles(
    existing: bool,
) -> None:
    repo, session = repository()
    session.get.return_value = object()
    original_id = UUID(int=5) if existing else None
    identifier, answer_id = await repo.save_exchange(
        original_id,
        "q",
        Answer(
            "a",
            model="actual-model",
            input_tokens=120,
            output_tokens=30,
            latency_ms=350,
        ),
    )
    if existing:
        assert identifier == original_id
        session.add.assert_not_called()
    else:
        assert isinstance(session.add.call_args.args[0], ConversationModel)
    messages = session.add_all.call_args.args[0]
    assert [m.role for m in messages] == ["user", "assistant"]
    assert all(m.conversation_id == identifier for m in messages)
    assert messages[1].id == answer_id
    assert messages[0].created_at < messages[1].created_at
    assert (
        messages[1].model,
        messages[1].input_tokens,
        messages[1].output_tokens,
        messages[1].latency_ms,
    ) == ("actual-model", 120, 30, 350)
    assert (
        messages[0].model,
        messages[0].input_tokens,
        messages[0].output_tokens,
        messages[0].latency_ms,
    ) == (None, None, None, None)
    session.begin.return_value.__aexit__.assert_awaited_once()


async def test_unknown_history_and_existing_exchange_do_not_create_conversation() -> (
    None
):
    repo, session = repository()
    session.get.return_value = None
    with pytest.raises(ConversationNotFoundError):
        await repo.history(UUID(int=1), 10)
    with pytest.raises(ConversationNotFoundError):
        await repo.save_exchange(UUID(int=1), "q", Answer("a"))
    session.add.assert_not_called()


async def test_storage_failure_is_translated() -> None:
    repo, session = repository()
    session.get.side_effect = ConnectionRefusedError()
    with pytest.raises(ConversationUnavailableError):
        await repo.history(UUID(int=1), 10)
    with pytest.raises(ConversationUnavailableError):
        await repo.save_exchange(UUID(int=1), "q", Answer("a"))


async def test_history_limit_must_be_positive() -> None:
    repo, _ = repository()
    with pytest.raises(ValueError):
        await repo.history(UUID(int=1), 0)
