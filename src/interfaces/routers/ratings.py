from uuid import UUID

from fastapi import APIRouter, Depends

from src.application.answer.submit_rating import SubmitRating
from src.interfaces.dependencies.answer import get_submit_rating
from src.interfaces.schemas.rating import RatingRequest, RatingResponse

router = APIRouter(prefix="/messages", tags=["ratings"])


@router.post("/{message_id}/rating", response_model=RatingResponse, status_code=201)
async def rate_answer(
    message_id: UUID,
    body: RatingRequest,
    use_case: SubmitRating = Depends(get_submit_rating),
) -> RatingResponse:
    await use_case.execute(message_id, body.stars)
    return RatingResponse(message_id=message_id, stars=body.stars)
