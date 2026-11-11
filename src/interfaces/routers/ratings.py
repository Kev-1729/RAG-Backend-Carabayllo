from uuid import UUID

from fastapi import APIRouter, Depends, Header

from src.application.answer.submit_rating import SubmitRating
from src.container.security import get_conversation_tokens
from src.domain.ports import ConversationTokens
from src.interfaces.dependencies.answer import get_submit_rating
from src.interfaces.dependencies.security import (
    authorize_conversation,
    enforce_request_limit,
)
from src.interfaces.schemas.rating import RatingRequest, RatingResponse

router = APIRouter(
    prefix="/messages", tags=["ratings"], dependencies=[Depends(enforce_request_limit)]
)


@router.post("/{message_id}/rating", response_model=RatingResponse, status_code=201)
async def rate_answer(
    message_id: UUID,
    body: RatingRequest,
    use_case: SubmitRating = Depends(get_submit_rating),
    tokens: ConversationTokens = Depends(get_conversation_tokens),
    access_token: str | None = Header(
        default=None, alias="X-Conversation-Token", max_length=101
    ),
) -> RatingResponse:
    conversation_id = authorize_conversation(tokens, access_token)
    await use_case.execute(message_id, body.stars, conversation_id=conversation_id)
    return RatingResponse(message_id=message_id, stars=body.stars)
