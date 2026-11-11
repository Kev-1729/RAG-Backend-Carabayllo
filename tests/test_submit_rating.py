from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.application.answer.submit_rating import SubmitRating
from src.domain.exceptions import (
    InvalidRatingError,
    MessageNotFoundError,
    RatingAlreadyExistsError,
)
from src.domain.ports import RatingRepository


@pytest.mark.parametrize("stars", [1, 3, 5])
async def test_rates_assistant_message(stars: int) -> None:
    repository = AsyncMock(spec=RatingRepository)
    repository.message_role.return_value = "assistant"
    await SubmitRating(repository).execute(UUID(int=1), stars)
    repository.save.assert_awaited_once_with(UUID(int=1), stars)


async def test_rating_uses_conversation_scope_and_rejects_foreign_message() -> None:
    repository = AsyncMock(spec=RatingRepository)
    repository.message_role.return_value = None
    with pytest.raises(MessageNotFoundError):
        await SubmitRating(repository).execute(
            UUID(int=1), 4, conversation_id=UUID(int=2)
        )
    repository.message_role.assert_awaited_once_with(
        UUID(int=1), conversation_id=UUID(int=2)
    )
    repository.save.assert_not_awaited()


@pytest.mark.parametrize("stars", [0, 6, True])
async def test_invalid_stars_do_not_touch_storage(stars: int) -> None:
    repository = AsyncMock(spec=RatingRepository)
    with pytest.raises(InvalidRatingError):
        await SubmitRating(repository).execute(UUID(int=1), stars)
    repository.message_role.assert_not_awaited()
    repository.save.assert_not_awaited()


@pytest.mark.parametrize(
    "role,error", [(None, MessageNotFoundError), ("user", InvalidRatingError)]
)
async def test_unknown_message_or_user_message_is_not_rated(
    role: str | None, error: type[Exception]
) -> None:
    repository = AsyncMock(spec=RatingRepository)
    repository.message_role.return_value = role
    with pytest.raises(error):
        await SubmitRating(repository).execute(UUID(int=1), 4)
    repository.save.assert_not_awaited()


async def test_duplicate_is_propagated() -> None:
    repository = AsyncMock(spec=RatingRepository)
    repository.message_role.return_value = "assistant"
    repository.save.side_effect = RatingAlreadyExistsError()
    with pytest.raises(RatingAlreadyExistsError):
        await SubmitRating(repository).execute(UUID(int=1), 4)
