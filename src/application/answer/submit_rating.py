from uuid import UUID

from src.domain.exceptions import InvalidRatingError, MessageNotFoundError
from src.domain.ports import RatingRepository


class SubmitRating:
    def __init__(self, repository: RatingRepository) -> None:
        self._repository = repository

    async def execute(
        self, message_id: UUID, stars: int, *, conversation_id: UUID | None = None
    ) -> None:
        if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= 5:
            raise InvalidRatingError()
        role = (
            await self._repository.message_role(
                message_id, conversation_id=conversation_id
            )
            if conversation_id is not None
            else await self._repository.message_role(message_id)
        )
        if role is None:
            raise MessageNotFoundError()
        if role != "assistant":
            raise InvalidRatingError()
        await self._repository.save(message_id, stars)
